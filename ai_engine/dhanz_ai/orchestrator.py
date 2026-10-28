"""Model routing and fallback.

The orchestrator picks a model for each request based on (in priority order):
1. an explicit provider/model chosen by the user for this message,
2. the user's saved preferred model,
3. the detected task type (code, reasoning, general) and the routing policy
   (balanced, cheapest, best, local_first),
and falls back to the next candidate if a provider fails *before* producing output.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Sequence
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
)

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


@dataclass(frozen=True)
class RoutedChunk:
    model: ModelInfo
    chunk: StreamChunk


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

        if request.explicit_provider and request.explicit_model:
            explicit = self.find_model(request.explicit_provider, request.explicit_model)
            if explicit is None:
                raise NoModelAvailableError(
                    f"Model {request.explicit_provider}:{request.explicit_model} is not available."
                )
            ordered.append(explicit)
            if not request.allow_fallback:
                return ordered
        elif request.preferred_model_key:
            provider, _, model = request.preferred_model_key.partition(":")
            preferred = self.find_model(provider, model)
            if preferred:  # a stale preference silently falls through to automatic routing
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
    ) -> AsyncIterator[RoutedChunk]:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        task = classify_task(last_user)
        candidates = self.candidates(request, task)
        if not request.allow_fallback:
            candidates = candidates[:1]

        errors: list[str] = []
        for info in candidates:
            provider = self._providers[info.provider]
            produced_output = False
            try:
                async for chunk in provider.stream(info.model, messages, params):
                    if chunk.text:
                        produced_output = True
                    yield RoutedChunk(info, chunk)
                return
            except ProviderError as exc:
                log.warning("Provider %s failed (model %s): %s", info.provider, info.model, exc)
                # Once text has been streamed to the user we cannot transparently switch models.
                if produced_output or not exc.retryable:
                    raise
                errors.append(str(exc))
        raise ProviderError("orchestrator", "All candidate models failed: " + " | ".join(errors), retryable=False)
