"""Core data types shared by every provider and the orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


class Capability(str, Enum):
    CHAT = "chat"
    CODE = "code"
    VISION = "vision"
    LONG_CONTEXT = "long_context"
    REASONING = "reasoning"
    LOCAL = "local"


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
    input_tokens: int | None = None
    output_tokens: int | None = None


class ProviderError(Exception):
    """Raised when a provider call fails. `retryable` hints whether falling back makes sense."""

    def __init__(self, provider: str, message: str, *, status_code: int | None = None, retryable: bool = True):
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable
