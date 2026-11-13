from collections.abc import AsyncIterator, Sequence

import pytest

from dhanz_ai import (
    Capability,
    ChatMessage,
    CostTier,
    GenerationParams,
    ModelInfo,
    NoModelAvailableError,
    Orchestrator,
    Provider,
    ProviderError,
    RoutingPolicy,
    RoutingRequest,
    StreamChunk,
    TaskType,
    build_system_prompt,
    classify_task,
)


class ScriptedProvider(Provider):
    """Test double that replays a fixed script of chunks or raises."""

    def __init__(self, name, models, *, chunks=("ok",), error: ProviderError | None = None, error_after=0):
        super().__init__()
        self.name = name
        self._models = models
        self._chunks = chunks
        self._error = error
        self._error_after = error_after
        self.calls = 0

    def is_configured(self) -> bool:
        return True

    def models(self) -> list[ModelInfo]:
        return self._models

    async def stream(
        self, model: str, messages: Sequence[ChatMessage], params: GenerationParams
    ) -> AsyncIterator[StreamChunk]:
        self.calls += 1
        for i, text in enumerate(self._chunks):
            if self._error and i == self._error_after:
                raise self._error
            yield StreamChunk(text=text)
        if self._error and self._error_after >= len(self._chunks):
            raise self._error
        yield StreamChunk(done=True)


def info(provider, model, tier, *caps):
    return ModelInfo(provider, model, model, frozenset({Capability.CHAT, *caps}), tier)


CHEAP = info("a", "cheap", CostTier.LOW)
MID = info("b", "mid", CostTier.MEDIUM, Capability.CODE, Capability.REASONING)
TOP = info("c", "top", CostTier.HIGH, Capability.CODE, Capability.REASONING)
LOCAL = info("ollama", "local", CostTier.FREE, Capability.LOCAL, Capability.CODE)


def orch(**overrides):
    providers = {
        "a": ScriptedProvider("a", [CHEAP]),
        "b": ScriptedProvider("b", [MID]),
        "c": ScriptedProvider("c", [TOP]),
        "ollama": ScriptedProvider("ollama", [LOCAL]),
    }
    providers.update(overrides)
    return Orchestrator(list(providers.values())), providers


def test_classify_task():
    assert classify_task("Fix this Python function") == TaskType.CODE
    assert classify_task("Solve x^2 = 4 step by step") == TaskType.REASONING
    assert classify_task("Tell me a story about a cat") == TaskType.GENERAL


@pytest.mark.parametrize(
    "policy,first",
    [
        (RoutingPolicy.CHEAPEST, LOCAL),
        (RoutingPolicy.BEST, TOP),
        (RoutingPolicy.LOCAL_FIRST, LOCAL),
        (RoutingPolicy.BALANCED, MID),
    ],
)
def test_policy_ordering(policy, first):
    o, _ = orch()
    assert o.candidates(RoutingRequest(policy=policy), TaskType.GENERAL)[0] == first


def test_explicit_and_preferred_model_win():
    o, _ = orch()
    req = RoutingRequest(explicit_provider="a", explicit_model="cheap", policy=RoutingPolicy.BEST)
    assert o.candidates(req, TaskType.CODE)[0] == CHEAP
    req = RoutingRequest(preferred_model_key="c:top", policy=RoutingPolicy.CHEAPEST)
    assert o.candidates(req, TaskType.GENERAL)[0] == TOP
    # Stale preference is ignored rather than failing.
    req = RoutingRequest(preferred_model_key="zzz:gone")
    assert o.candidates(req, TaskType.GENERAL)[0] == MID


def test_unknown_explicit_model_raises():
    o, _ = orch()
    with pytest.raises(NoModelAvailableError):
        o.candidates(RoutingRequest(explicit_provider="a", explicit_model="nope"), TaskType.GENERAL)


def test_no_providers():
    with pytest.raises(NoModelAvailableError):
        Orchestrator([]).candidates(RoutingRequest(), TaskType.GENERAL)


async def test_fallback_before_output():
    failing = ScriptedProvider("b", [MID], error=ProviderError("b", "down", status_code=503))
    o, providers = orch(b=failing)
    out = [rc async for rc in o.stream_chat([ChatMessage("user", "hello")])]
    assert failing.calls == 1
    assert "".join(rc.chunk.text for rc in out) == "ok"
    assert out[0].model != MID


async def test_no_fallback_after_partial_output():
    failing = ScriptedProvider("b", [MID], chunks=("par", "tial"), error=ProviderError("b", "cut"), error_after=1)
    o, _ = orch(b=failing)
    with pytest.raises(ProviderError):
        [rc async for rc in o.stream_chat([ChatMessage("user", "hello")])]


async def test_non_retryable_error_is_not_masked():
    failing = ScriptedProvider("b", [MID], error=ProviderError("b", "bad key", status_code=401, retryable=False))
    o, _ = orch(b=failing)
    with pytest.raises(ProviderError, match="bad key"):
        [rc async for rc in o.stream_chat([ChatMessage("user", "hello")])]


async def test_model_refusing_the_request_falls_back_to_the_next_model():
    # e.g. "Function tools ... not supported for this model": HTTP 400 before any output.
    refused = ProviderError("b", "HTTP 400: tools not supported for mid", status_code=400, retryable=False)
    failing = ScriptedProvider("b", [MID], error=refused)
    o, _ = orch(b=failing)
    out = [rc async for rc in o.stream_chat([ChatMessage("user", "hello")])]
    assert failing.calls == 1
    assert "".join(rc.chunk.text for rc in out) == "ok"
    assert out[0].model != MID


async def test_every_model_refusing_keeps_the_status_for_the_user_message():
    def refusing(name, model):
        return ScriptedProvider(name, [model], error=ProviderError(name, "too long", status_code=400, retryable=False))

    o, _ = orch(a=refusing("a", CHEAP), b=refusing("b", MID), c=refusing("c", TOP), ollama=refusing("ollama", LOCAL))
    with pytest.raises(ProviderError, match="All candidate models failed") as caught:
        [rc async for rc in o.stream_chat([ChatMessage("user", "hello")])]
    assert caught.value.status_code == 400


async def test_local_only_routes_only_to_local_models():
    o, providers = orch()
    request = RoutingRequest(policy=RoutingPolicy.LOCAL_ONLY)
    assert [m.model for m in o.candidates(request, TaskType.GENERAL)] == ["local"]
    out = [rc async for rc in o.stream_chat([ChatMessage("user", "hello")], request)]
    assert out[0].model == LOCAL and providers["a"].calls == providers["b"].calls == providers["c"].calls == 0


def test_local_only_without_a_local_model_or_with_a_cloud_pick_is_refused():
    o = Orchestrator([ScriptedProvider("a", [CHEAP]), ScriptedProvider("b", [MID])])
    with pytest.raises(NoModelAvailableError, match="no configured local model"):
        o.candidates(RoutingRequest(policy=RoutingPolicy.LOCAL_ONLY), TaskType.GENERAL)
    o, _ = orch()
    cloud_pick = RoutingRequest(policy=RoutingPolicy.LOCAL_ONLY, explicit_provider="b", explicit_model="mid")
    with pytest.raises(NoModelAvailableError, match="local-only"):
        o.candidates(cloud_pick, TaskType.GENERAL)


def test_system_prompt_mentions_identity_and_honesty():
    p = build_system_prompt(user_preferences="Answer in French", project_instructions="Use metric units")
    assert "Dhanz" in p and "Never fabricate" in p and "Answer in French" in p and "Use metric units" in p
    assert "do not have live internet access" in p
    p = build_system_prompt(sources="[1] Title\nURL: https://a.com\ntext", research_notes="1 page was blocked")
    assert "<sources>" in p and "[1] Title" in p and "untrusted" in p and "1 page was blocked" in p
    assert "do not have live internet access" not in p


def test_required_capabilities_filter_candidates():
    o, _ = orch()
    req = RoutingRequest(required=frozenset({Capability.CODE}))
    assert all(Capability.CODE in m.capabilities for m in o.candidates(req, TaskType.GENERAL))
    with pytest.raises(NoModelAvailableError, match="vision"):
        o.candidates(RoutingRequest(required=frozenset({Capability.VISION})), TaskType.GENERAL)
    with pytest.raises(NoModelAvailableError, match="cannot handle"):
        o.candidates(
            RoutingRequest(explicit_provider="a", explicit_model="cheap", required=frozenset({Capability.CODE})),
            TaskType.GENERAL,
        )
