"""Model routing and fallback.

The orchestrator picks a model for each request based on (in priority order):
1. an explicit provider/model chosen by the user for this message,
2. the user's saved preferred model,
3. the detected task type (code, reasoning, general) and the routing policy
   (balanced, cheapest, best, local_first),
and falls back to the next candidate if a provider fails *before* producing output.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from dhanz_ai.providers.base import Provider
from dhanz_ai.types import (
    Capability,
    ChatMessage,
    GenerationParams,
    ModelInfo,
    ProviderError,
    StreamChunk,
    ToolCall,
    ToolResult,
    ToolSpec,
)

ToolRunner = Callable[[ToolCall], Awaitable[ToolResult]]
MAX_TOOL_ROUNDS = 5

log = logging.getLogger(__name__)


class RoutingPolicy(str, Enum):
    BALANCED = "balanced"
    CHEAPEST = "cheapest"
    BEST = "best"
    LOCAL_FIRST = "local_first"


class TaskType(str, Enum):
    GENERAL = "general"
    CODE = "code"
    REASONING = "reasoning"


_CODE_RE = re.compile(
    r"```|\b(code|function|class|bug|stack ?trace|compile|python|javascript|typescript|dart|flutter|java|"
    r"kotlin|swift|rust|golang|sql|regex|api|refactor|unit test|exception)\b",
    re.IGNORECASE,
)
_REASONING_RE = re.compile(
    r"\b(prove|derive|calculate|solve|step[- ]by[- ]step|analy[sz]e|compare|trade-?offs?|equation|"
    r"probability|optimi[sz]e|plan)\b",
    re.IGNORECASE,
)


def classify_task(text: str) -> TaskType:
    if _CODE_RE.search(text):
        return TaskType.CODE
    if _REASONING_RE.search(text):
        return TaskType.REASONING
    return TaskType.GENERAL


@dataclass(frozen=True)
class RoutingRequest:
    explicit_provider: str | None = None
    explicit_model: str | None = None
    preferred_model_key: str | None = None  # "provider:model"
    policy: RoutingPolicy = RoutingPolicy.BALANCED
    allow_fallback: bool = True
    # Capabilities every candidate must have (e.g. VISION when the message carries images).
    required: frozenset[Capability] = frozenset()


@dataclass(frozen=True)
class RoutedChunk:
    model: ModelInfo
    chunk: StreamChunk
    # Results of the tool calls announced by the previous chunk (after they ran).
    tool_results: tuple[ToolResult, ...] = ()


class NoModelAvailableError(Exception):
    pass


class Orchestrator:
    def __init__(self, providers: Sequence[Provider]):
        self._providers: dict[str, Provider] = {p.name: p for p in providers}

    @property
    def providers(self) -> dict[str, Provider]:
        return dict(self._providers)

    def available_models(self) -> list[ModelInfo]:
        return [m for p in self._providers.values() if p.is_configured() for m in p.models()]

    def find_model(self, provider: str, model: str) -> ModelInfo | None:
        p = self._providers.get(provider)
        if not p or not p.is_configured():
            return None
        for info in p.models():
            if info.model == model:
                return info
        return None

    def candidates(self, request: RoutingRequest, task: TaskType) -> list[ModelInfo]:
        available = self.available_models()
        if not available:
            raise NoModelAvailableError(
                "No AI provider is configured. Set at least one of OPENAI_API_KEY, ANTHROPIC_API_KEY, "
                "GEMINI_API_KEY or OLLAMA_BASE_URL on the backend."
            )

        ordered: list[ModelInfo] = []

        if request.required:
            available = [m for m in available if request.required <= m.capabilities]
            if not available:
                needs = ", ".join(sorted(c.value for c in request.required))
                raise NoModelAvailableError(f"No configured AI model supports what this message needs ({needs}).")

        if request.explicit_provider and request.explicit_model:
            explicit = self.find_model(request.explicit_provider, request.explicit_model)
            if explicit is None:
                raise NoModelAvailableError(
                    f"Model {request.explicit_provider}:{request.explicit_model} is not available."
                )
            if not request.required <= explicit.capabilities:
                raise NoModelAvailableError(
                    f"{explicit.display_name} cannot handle this message (it needs "
                    + ", ".join(sorted(c.value for c in request.required))
                    + "). Choose another model or Auto."
                )
            ordered.append(explicit)
            if not request.allow_fallback:
                return ordered
        elif request.preferred_model_key:
            provider, _, model = request.preferred_model_key.partition(":")
            preferred = self.find_model(provider, model)
            if (
                preferred and request.required <= preferred.capabilities
            ):  # a stale preference silently falls through to automatic routing
                ordered.append(preferred)

        for info in sorted(available, key=lambda m: self._score(m, task, request.policy), reverse=True):
            if info not in ordered:
                ordered.append(info)
        return ordered

    @staticmethod
    def _score(m: ModelInfo, task: TaskType, policy: RoutingPolicy) -> float:
        caps = m.capabilities
        score = 0.0
        if task == TaskType.CODE and Capability.CODE in caps:
            score += 2
        if task == TaskType.REASONING and Capability.REASONING in caps:
            score += 2
        cost = int(m.cost_tier)
        if policy == RoutingPolicy.CHEAPEST:
            score -= cost * 3
        elif policy == RoutingPolicy.BEST:
            score += cost * 1.5 + (1 if Capability.REASONING in caps else 0)
        elif policy == RoutingPolicy.LOCAL_FIRST:
            score += 10 if Capability.LOCAL in caps else 0
        else:  # balanced: prefer mid-tier, penalise the extremes slightly
            score -= abs(cost - 2) * 0.75
            if Capability.LOCAL in caps:
                score -= 1  # cloud models are usually stronger when available
        return score

    async def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        request: RoutingRequest = RoutingRequest(),
        params: GenerationParams = GenerationParams(),
        tools: Sequence[ToolSpec] = (),
        run_tool: ToolRunner | None = None,
    ) -> AsyncIterator[RoutedChunk]:
        """Stream a reply. With `tools` and `run_tool`, models that support function calling may call
        tools: each call is executed by `run_tool` and the result handed back to the model, for up to
        MAX_TOOL_ROUNDS rounds. Exactly one chunk with done=True ends the stream (tokens summed)."""
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        task = classify_task(last_user)
        candidates = self.candidates(request, task)
        if not request.allow_fallback:
            candidates = candidates[:1]

        errors: list[str] = []
        for info in candidates:
            provider = self._providers[info.provider]
            produced_output = False
            offer = tuple(tools) if run_tool is not None and Capability.TOOLS in info.capabilities else ()
            convo = list(messages)
            input_tokens: int | None = None
            output_tokens: int | None = None
            try:
                for round_no in range(MAX_TOOL_ROUNDS + 1):
                    texts: list[str] = []
                    calls: tuple[ToolCall, ...] = ()
                    stream = (
                        provider.stream(info.model, convo, params, tools=offer)
                        if offer
                        else provider.stream(info.model, convo, params)
                    )
                    async for chunk in stream:
                        if chunk.done:
                            input_tokens = _add(input_tokens, chunk.input_tokens)
                            output_tokens = _add(output_tokens, chunk.output_tokens)
                            continue
                        if chunk.text:
                            produced_output = True
                            texts.append(chunk.text)
                        if chunk.tool_calls:
                            if not offer:
                                continue  # tools were not offered: ignore stray calls
                            produced_output = True
                            calls = chunk.tool_calls
                        yield RoutedChunk(info, chunk)
                    if not calls:
                        break
                    if round_no == MAX_TOOL_ROUNDS:
                        note = "\n\n(I stopped after several tool steps. Ask me to continue if you need more.)"
                        yield RoutedChunk(info, StreamChunk(text=note))
                        break
                    results = tuple([await _run(run_tool, c) for c in calls])
                    yield RoutedChunk(info, StreamChunk(), tool_results=results)
                    convo.append(ChatMessage("assistant", "".join(texts), tool_calls=calls))
                    convo += [ChatMessage.from_tool_result(r) for r in results]
                yield RoutedChunk(info, StreamChunk(done=True, input_tokens=input_tokens, output_tokens=output_tokens))
                return
            except ProviderError as exc:
                log.warning("Provider %s failed (model %s): %s", info.provider, info.model, exc)
                # Once text has been streamed (or a tool has run) we cannot transparently switch models.
                if produced_output or not exc.retryable:
                    raise
                errors.append(str(exc))
        raise ProviderError("orchestrator", "All candidate models failed: " + " | ".join(errors), retryable=False)


def _add(total: int | None, value: int | None) -> int | None:
    if value is None:
        return total
    return (total or 0) + value


async def _run(run_tool: ToolRunner | None, call: ToolCall) -> ToolResult:
    if run_tool is None:  # pragma: no cover - tools are only offered with a runner
        return ToolResult(call.id, call.name, json.dumps({"error": "Tools are not available."}), is_error=True)
    try:
        return await run_tool(call)
    except Exception as exc:  # noqa: BLE001 - a failing tool is reported to the model, not to the user
        log.exception("Tool %s failed", call.name)
        return ToolResult(call.id, call.name, json.dumps({"error": f"The tool failed: {exc}"}), is_error=True)
