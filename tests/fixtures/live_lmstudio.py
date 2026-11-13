# The live server's own providers/lmstudio.py (server-only, not in this package), kept as a
# fixture so tests prove the GPT-6 engine files still work with it.
"""Local LM Studio server using its OpenAI-compatible API."""

from dataclasses import replace

from dhanz_ai.providers.openai import OpenAIProvider
from dhanz_ai.types import Capability, CostTier, ModelInfo, ProviderError


class LMStudioProvider(OpenAIProvider):
    name = "lmstudio"

    async def stream(self, model, messages, params, tools=()):
        # Qwen3 supports disabling thinking with a suffix on the latest user turn.
        # Copy messages so cloud fallback receives the original conversation.
        messages = list(messages)
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].role == "user":
                messages[index] = replace(
                    messages[index],
                    content=messages[index].content + "\nBe concise unless I ask for more detail. /no_think",
                )
                break
        while True:
            emitted = False
            try:
                async for chunk in super().stream(model, messages, params, tools):
                    emitted = True
                    yield chunk
                return
            except ProviderError as exc:
                if emitted or not any(
                    marker in str(exc)
                    for marker in (
                        "exceed_context_size",
                        "exceeds the available context",
                    )
                ):
                    raise
                # Drop complete old conversation rounds, never a tool result alone.
                users = [i for i, message in enumerate(messages) if message.role == "user"]
                if len(users) < 2:
                    raise
                messages = [*messages[: users[0]], *messages[users[1] :]]

    def is_configured(self) -> bool:
        return bool(self.base_url) and bool(self._models)

    def models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                self.name,
                model,
                f"LM Studio · {model}",
                frozenset({Capability.CHAT, Capability.CODE, Capability.TOOLS, Capability.LOCAL}),
                CostTier.FREE,
                context_window=16384,
            )
            for model in self._models
        ]
