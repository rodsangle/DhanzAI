"""Core data types shared by every provider and the orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class ImagePart:
    """An image attached to a user message (base64-encoded bytes)."""

    mime_type: str
    data_b64: str


@dataclass(frozen=True)
class ToolSpec:
    """A function the model may call. `parameters` is a JSON Schema object (keep it simple: Gemini
    accepts only an OpenAPI subset — no `additionalProperties`, `$ref` or `oneOf`)."""

    name: str
    description: str
    parameters: dict


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict
    # Opaque provider data that must be sent back with the call (e.g. Gemini thought signatures).
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    name: str
    content: str  # usually JSON text
    is_error: bool = False


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str
    images: tuple[ImagePart, ...] = ()
    # Assistant messages: the tools the model asked to call in this turn.
    tool_calls: tuple[ToolCall, ...] = ()
    # Tool messages (role "tool"): which call this is the result of.
    tool_result: ToolResult | None = None

    @staticmethod
    def from_tool_result(result: ToolResult) -> ChatMessage:
        return ChatMessage("tool", result.content, tool_result=result)


class Capability(str, Enum):
    CHAT = "chat"
    CODE = "code"
    VISION = "vision"
    LONG_CONTEXT = "long_context"
    REASONING = "reasoning"
    LOCAL = "local"
    TOOLS = "tools"  # native function calling


class CostTier(int, Enum):
    """Relative cost, used by the orchestrator. Lower is cheaper."""

    FREE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass(frozen=True)
class ModelInfo:
    provider: str
    model: str
    display_name: str
    capabilities: frozenset[Capability] = field(default_factory=lambda: frozenset({Capability.CHAT}))
    cost_tier: CostTier = CostTier.MEDIUM
    context_window: int = 128_000

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass(frozen=True)
class GenerationParams:
    temperature: float = 0.7
    max_tokens: int = 2048


@dataclass(frozen=True)
class StreamChunk:
    """A piece of streamed output. `text` is a delta, never the full text."""

    text: str = ""
    done: bool = False
    # Set on the final chunk of a round in which the model asked for tool calls.
    tool_calls: tuple[ToolCall, ...] = ()
    input_tokens: int | None = None
    output_tokens: int | None = None


class ProviderError(Exception):
    """Raised when a provider call fails. `retryable` hints whether falling back makes sense."""

    def __init__(self, provider: str, message: str, *, status_code: int | None = None, retryable: bool = True):
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable
