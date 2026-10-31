"""Creative Studio API, transactional credits, durable jobs and provider wire contracts."""

import base64
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
import pytest
from PIL import Image
from sqlalchemy import select, update

from app.content_moderation import LlmModerator, ModerationRejected, Moderator, parse_decision
from app.core.config import Settings
from app.db.base import utcnow
from app.generation_jobs import CreativeRuntime, cleanup, process_one
from app.image_generation import ImageProvider
from app.media_storage import validate_image
from app.models import GenerationJob
from app.services.storage import FileStorage
from app.video_generation import VideoProvider
from tests.test_phase3 import register, upload


def png():
    stream = io.BytesIO()
    Image.new("RGB", (32, 32), "navy").save(stream, format="PNG")
    return stream.getvalue()


def image_bytes(format):
    stream = io.BytesIO()
    Image.new("RGB", (32, 32), "navy").save(stream, format=format.upper())
    return stream.getvalue()


@pytest.fixture
def studio(client, settings, tmp_path):
    state = {
        "image_calls": [],
        "video_calls": [],
        "fail": False,
        "blocked": False,
        "video_status": "RUNNING",
        "cancels": 0,
    }

    def images(request):
        state["image_calls"].append(request)
        if state["fail"]:
            return httpx.Response(429, json={"error": "Provider credentials and internal details must not leak"})
        data = image_bytes(state.get("output_format", "png"))
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(data).decode()}]})

    def moderation(request):
        if state.get("moderation_down"):
            return httpx.Response(503)
        return httpx.Response(200, json={"results": [{"flagged": state["blocked"]}]})

    def videos(request):
        if request.method == "POST":
            state["video_calls"].append(json.loads(request.content))
            return httpx.Response(200, json={"id": "task-123"})
        if request.method == "DELETE":
            state["cancels"] += 1
            return httpx.Response(204)
        return httpx.Response(
            200, json={"status": state["video_status"], "output": ["https://output.cloudfront.net/result.mp4"]}
        )

    runtime = client.app.state.creative
    runtime.storage = FileStorage(tmp_path / "creative")
    runtime.image = ImageProvider(
        "image-key", "https://images.example/v1", "test-image", transport=httpx.MockTransport(images)
    )
    runtime.video = VideoProvider("video-key", transport=httpx.MockTransport(videos))
    runtime.moderator = Moderator("moderation-key", transport=httpx.MockTransport(moderation))

    async def download(url, limit):
        return b"\x00\x00\x00\x18ftypmp42" + b"video-test-data"

    runtime.video.download = download
    return state


def body(key="request-0001", kind="image", **extra):
    return {
        "request_key": key,
        "kind": kind,
        "model": "test-image" if kind == "image" else "gen4.5",
        "prompt": "A calm mountain landscape",
        "ratio": "1:1" if kind == "image" else "16:9",
        "format": "png" if kind == "image" else "mp4",
        "rights_confirmed": True,
        **extra,
    }


def generate(client, auth, **extra):
    response = client.post("/api/v1/creative/jobs", headers=auth["headers"], json=body(**extra))
    assert response.status_code == 201, response.text
    return response.json()


def credits(client, auth):
    return client.get("/api/v1/creative/credits", headers=auth["headers"]).json()


def work(client):
    return client.portal.call(process_one, client.app.state.sessionmaker, client.app.state.creative)


def job(client, auth, job_id):
    return client.get(f"/api/v1/creative/jobs/{job_id}", headers=auth["headers"]).json()


def ready_to_poll(client, job_id):
    async def update_job():
        async with client.app.state.sessionmaker() as db:
            from uuid import UUID

            await db.execute(
                update(GenerationJob)
                .where(GenerationJob.id == UUID(job_id))
                .values(next_poll_at=utcnow() - timedelta(seconds=1))
            )
            await db.commit()

    client.portal.call(update_job)


def test_disabled_provider_and_consent_validation(client, auth):
    assert client.get("/api/v1/creative/capabilities", headers=auth["headers"]).json()["models"] == []
    response = client.post("/api/v1/creative/jobs", headers=auth["headers"], json=body())
    assert response.status_code == 503
    assert (
        client.post("/api/v1/creative/jobs", headers=auth["headers"], json=body(rights_confirmed=False)).status_code
        == 422
    )


def test_image_generation_credit_settlement_and_download(client, auth, studio):
    queued = generate(client, auth)
    assert queued["status"] == "queued" and credits(client, auth)["reserved"] == 5
    assert work(client)
    finished = job(client, auth, queued["id"])
    assert finished["status"] == "completed" and finished["has_media"]
    assert finished["provenance"]["ai_generated"] is True
    balance = credits(client, auth)
    assert (balance["balance"], balance["reserved"], balance["consumed"]) == (95, 0, 5)
    response = client.get(f"/api/v1/creative/jobs/{queued['id']}/download", headers=auth["headers"])
    assert response.content == png() and response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "private, no-store"
    request = studio["image_calls"][0]
    payload = json.loads(request.content)
    assert str(request.url) == "https://images.example/v1/images/generations"
    assert payload["moderation"] == "auto" and payload["size"] == "1024x1024"
    assert not work(client)


def test_duplicate_requests_and_key_payload_conflicts(client, auth, studio):
    first = generate(client, auth)
    assert generate(client, auth)["id"] == first["id"]
    assert credits(client, auth)["reserved"] == 5
    response = client.post("/api/v1/creative/jobs", headers=auth["headers"], json=body(prompt="Different image"))
    assert response.status_code == 409
    work(client)
    assert generate(client, auth)["id"] == first["id"]
    assert len(studio["image_calls"]) == 1


@pytest.mark.parametrize("format", ["jpeg", "webp"])
def test_generated_image_formats_are_validated_and_downloaded(client, auth, studio, format):
    studio["output_format"] = format
    creation = generate(client, auth, format=format)
    work(client)
    assert job(client, auth, creation["id"])["status"] == "completed"
    response = client.get(f"/api/v1/creative/jobs/{creation['id']}/download", headers=auth["headers"])
    assert response.headers["content-type"] == f"image/{format}"
    assert response.content == image_bytes(format)


@pytest.mark.parametrize("failure", ["fail", "blocked", "moderation_down"])
def test_provider_errors_and_safety_fail_closed_refund(client, auth, studio, failure):
    studio[failure] = True
    queued = generate(client, auth)
    work(client)
    failed = job(client, auth, queued["id"])
    assert failed["status"] == "failed"
    assert credits(client, auth)["balance"] == 100 and credits(client, auth)["reserved"] == 0
    assert "credentials" not in failed["error"]
    if failure != "fail":
        assert not studio["image_calls"]


def test_cancel_is_idempotent_and_does_not_generate(client, auth, studio):
    queued = generate(client, auth)
    for _ in range(2):
        assert client.post(f"/api/v1/creative/jobs/{queued['id']}/cancel", headers=auth["headers"]).status_code == 200
    assert credits(client, auth)["balance"] == 100 and credits(client, auth)["reserved"] == 0
    assert not work(client) and not studio["image_calls"]


def test_cancel_during_image_generation_discards_late_output(client, auth, studio):
    queued = generate(client, auth)
    runtime = client.app.state.creative
    from app.generation_jobs import finish

    async def canceled_image(generation, reference):
        await finish(client.app.state.sessionmaker, runtime, generation.id, "canceled")
        return png()

    runtime.image.generate = canceled_image
    work(client)
    assert job(client, auth, queued["id"])["status"] == "canceled"
    assert credits(client, auth)["balance"] == 100
    assert not [p for p in runtime.storage.base.rglob("*") if p.is_file()]


def test_video_persists_between_polls_and_cannot_double_charge(client, auth, studio):
    queued = generate(client, auth, kind="video")
    assert credits(client, auth)["reserved"] == 50
    work(client)
    assert job(client, auth, queued["id"])["status"] == "processing"
    assert len(studio["video_calls"]) == 1
    ready_to_poll(client, queued["id"])
    studio["video_status"] = "SUCCEEDED"
    work(client)
    assert job(client, auth, queued["id"])["status"] == "completed"
    assert credits(client, auth)["consumed"] == 50
    assert credits(client, auth)["reserved"] == 0
    assert len(studio["video_calls"]) == 1


def test_video_failed_and_canceled_remote_jobs_refund(client, auth, studio):
    first = generate(client, auth, kind="video")
    studio["video_status"] = "FAILED"
    work(client)
    assert job(client, auth, first["id"])["status"] == "failed" and credits(client, auth)["balance"] == 100
    studio["video_status"] = "RUNNING"
    second = generate(client, auth, key="request-0002", kind="video")
    work(client)
    client.post(f"/api/v1/creative/jobs/{second['id']}/cancel", headers=auth["headers"])
    client.portal.call(cleanup, client.app.state.sessionmaker, client.app.state.creative)
    # Both the failed task and the canceled task receive a best-effort remote cancellation.
    assert studio["cancels"] == 2 and credits(client, auth)["balance"] == 100
    client.portal.call(cleanup, client.app.state.sessionmaker, client.app.state.creative)
    assert studio["cancels"] == 2


def test_concurrent_identical_requests_reserve_once(client, auth, studio):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda _: client.post("/api/v1/creative/jobs", headers=auth["headers"], json=body()), range(4))
        )
    assert all(response.status_code == 201 for response in results), [response.text for response in results]
    assert len({response.json()["id"] for response in results}) == 1
    assert credits(client, auth)["reserved"] == 5


def test_multiple_workers_cannot_submit_same_image_job(client, auth, studio):
    import asyncio

    creation = generate(client, auth)

    async def workers():
        return await asyncio.gather(
            *(process_one(client.app.state.sessionmaker, client.app.state.creative) for _ in range(3))
        )

    client.portal.call(workers)
    assert job(client, auth, creation["id"])["status"] == "completed"
    assert len(studio["image_calls"]) == 1
    assert credits(client, auth)["consumed"] == 5


def test_concurrent_different_requests_cannot_overspend(client, auth, studio, settings):
    settings.creative_max_active_jobs = 10
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(
            pool.map(
                lambda i: client.post(
                    "/api/v1/creative/jobs", headers=auth["headers"], json=body(key=f"request-{i:04}", kind="video")
                ),
                range(3),
            )
        )
    assert sorted(response.status_code for response in results) == [201, 201, 402]
    balance = credits(client, auth)
    assert balance["balance"] == 0 and balance["reserved"] == 100


def test_account_isolation_signed_media_expiry_and_ranges(client, auth, studio):
    queued = generate(client, auth)
    work(client)
    other = register(client, "studio-other@example.com")
    for suffix in ("", "/download"):
        assert client.get(f"/api/v1/creative/jobs/{queued['id']}{suffix}", headers=other["headers"]).status_code == 404
    for suffix in ("/cancel", "/media-link"):
        assert client.post(f"/api/v1/creative/jobs/{queued['id']}{suffix}", headers=other["headers"]).status_code == 404
    assert client.get("/api/v1/creative/jobs", headers=other["headers"]).json() == []
    link = client.post(f"/api/v1/creative/jobs/{queued['id']}/media-link", headers=auth["headers"]).json()["path"]
    assert client.get("/api/v1" + link).content == png()
    assert client.get("/api/v1" + link + "x").status_code == 403
    assert client.get(f"/api/v1/creative/media/{queued['id']}?expires=1&signature=bad").status_code == 403
    partial = client.get("/api/v1" + link, headers={"Range": "bytes=0-3"})
    assert partial.status_code == 206 and partial.content == png()[:4]
    assert client.get("/api/v1" + link, headers={"Range": "bytes=9999999-"}).status_code == 416
    client.delete(f"/api/v1/creative/jobs/{queued['id']}", headers=auth["headers"])
    assert client.get("/api/v1" + link).status_code == 404
    client.portal.call(cleanup, client.app.state.sessionmaker, client.app.state.creative)
    assert not [p for p in client.app.state.creative.storage.base.rglob("*") if p.is_file()]


def test_reference_image_validation_and_edit_wire_format(client, auth, studio):
    doc = upload(client, auth, "ref.png", png()).json()
    first = generate(client, auth, reference_id=doc["id"], operation="edit")
    work(client)
    request = studio["image_calls"][0]
    assert str(request.url).endswith("/images/edits")
    assert b'name="image[]"' in request.content and png() in request.content
    assert job(client, auth, first["id"])["status"] == "completed"
    fake = upload(client, auth, "bad.png", b"\x89PNG\r\n\x1a\ninvalid").json()
    assert (
        client.post(
            "/api/v1/creative/jobs", headers=auth["headers"], json=body(key="request-bad1", reference_id=fake["id"])
        ).status_code
        == 422
    )
    other = register(client, "reference-other@example.com")
    assert (
        client.post("/api/v1/creative/jobs", headers=other["headers"], json=body(reference_id=doc["id"])).status_code
        == 404
    )


def test_admin_costs_grants_and_reports(client, auth, studio):
    response = client.put(
        "/api/v1/creative/admin/policy",
        headers=auth["headers"],
        json={"image_cost": 7, "video_cost_per_second": 11, "monthly_allowance": 25},
    )
    assert response.status_code == 200
    assert credits(client, auth)["balance"] == 25
    queued = generate(client, auth)
    assert queued["cost"] == 7
    assert (
        client.post(
            f"/api/v1/creative/jobs/{queued['id']}/report",
            headers=auth["headers"],
            json={"reason": "This output seems unsafe"},
        ).status_code
        == 201
    )
    assert len(client.get("/api/v1/creative/admin/reports", headers=auth["headers"]).json()) == 1
    other = register(client, "grant-user@example.com")
    user = client.get("/api/v1/users/me", headers=other["headers"]).json()
    for _ in range(2):
        assert (
            client.post(
                f"/api/v1/creative/admin/users/{user['id']}/credits",
                headers=auth["headers"],
                json={"amount": 20, "request_key": "purchase-12345"},
            ).status_code
            == 200
        )
    assert credits(client, other)["balance"] == 45
    assert (
        client.put(
            "/api/v1/creative/admin/policy",
            headers=other["headers"],
            json={"image_cost": 1, "video_cost_per_second": 1, "monthly_allowance": 999},
        ).status_code
        == 403
    )


def test_uncertain_submission_never_automatically_resubmits(client, auth, studio):
    queued = generate(client, auth)

    async def interrupted():
        async with client.app.state.sessionmaker() as db:
            current = await db.scalar(select(GenerationJob))
            current.submitted = True
            current.status = "processing"
            await db.commit()

    client.portal.call(interrupted)
    work(client)
    assert job(client, auth, queued["id"])["status"] == "failed"
    assert not studio["image_calls"] and credits(client, auth)["balance"] == 100


def test_export_and_account_deletion_remove_private_creations(client, auth, studio):
    queued = generate(client, auth)
    work(client)
    exported = client.get("/api/v1/users/me/export", headers=auth["headers"]).json()
    assert exported["creations"][0]["id"] == queued["id"]
    assert exported["creative_credits"]["consumed"] == 5
    assert len(exported["creative_credit_history"]) == 3
    # Test fixture's known password; no credentials are needed outside this isolated test DB.
    response = client.request(
        "DELETE", "/api/v1/users/me", headers=auth["headers"], json={"password": "correct-horse-9"}
    )
    assert response.status_code == 204, response.text
    client.portal.call(cleanup, client.app.state.sessionmaker, client.app.state.creative)
    assert not [p for p in client.app.state.creative.storage.base.rglob("*") if p.is_file()]


def test_per_user_subscription_allowance_and_monthly_idempotency(client, auth, studio, monkeypatch):
    from datetime import UTC, datetime

    other = register(client, "plan-user@example.com")
    target = client.get("/api/v1/users/me", headers=other["headers"]).json()["id"]
    response = client.put(
        f"/api/v1/creative/admin/users/{target}/allowance", headers=auth["headers"], json={"monthly_allowance": 250}
    )
    assert response.status_code == 200
    assert credits(client, other)["monthly_allowance"] == 250
    assert credits(client, other)["balance"] == 100
    monkeypatch.setattr("app.credit_billing.utcnow", lambda: datetime(2030, 1, 2, tzinfo=UTC))
    assert credits(client, other)["balance"] == 350
    assert credits(client, other)["balance"] == 350
    assert credits(client, other)["allowance_month"] == "2030-01"


def test_admin_takedown_revokes_existing_media_links(client, auth, studio):
    queued = generate(client, auth)
    work(client)
    path = client.post(f"/api/v1/creative/jobs/{queued['id']}/media-link", headers=auth["headers"]).json()["path"]
    response = client.delete(f"/api/v1/creative/admin/jobs/{queued['id']}", headers=auth["headers"])
    assert response.status_code == 204
    assert client.get("/api/v1" + path).status_code == 404
    assert credits(client, auth)["consumed"] == 5


@pytest.mark.parametrize(
    "changes",
    [
        {"ratio": "100:1"},
        {"quality": "ultra"},
        {"operation": "upscale"},
        {"format": "mp4"},
        {"operation": "edit"},
        {"operation": "remove_background", "format": "jpeg"},
    ],
)
def test_unsupported_capabilities_are_rejected_without_reserving(client, auth, studio, changes):
    assert client.post("/api/v1/creative/jobs", headers=auth["headers"], json=body(**changes)).status_code == 422
    assert credits(client, auth)["balance"] == 100 and credits(client, auth)["reserved"] == 0


async def test_runway_submission_contract_and_download_security():
    from types import SimpleNamespace

    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "abc-123"})

    provider = VideoProvider("secret", transport=httpx.MockTransport(respond))
    try:
        job = SimpleNamespace(
            model="gen4.5", prompt="Moving clouds", options={"ratio": "16:9", "duration": 5}, reference_mime="image/png"
        )
        assert await provider.submit(job) == "abc-123"
        assert requests[0].url.path == "/v1/text_to_video"
        assert requests[0].headers["X-Runway-Version"] == "2024-11-06"
        await provider.submit(job, png())
        assert requests[1].url.path == "/v1/image_to_video"
        assert json.loads(requests[1].content)["promptImage"].startswith("data:image/png;base64,")
        for url in ["http://127.0.0.1/test", "https://evil.example/out.mp4", "https://user@output.cloudfront.net/out"]:
            with pytest.raises(ValueError):
                await provider.download(url, 1000)
    finally:
        await provider.aclose()


class _ImageJob:
    def __init__(self, model="grok-imagine-image", **options):
        self.model = model
        self.prompt = "A calm mountain landscape"
        self.user_id = "user-1"
        self.reference_mime = "image/png"
        self.options = {"ratio": "3:2", "quality": "high", "format": "png", "operation": "generate", **options}


def _b64_image(format):
    return base64.b64encode(image_bytes(format)).decode()


async def test_xai_image_request_uses_imagine_fields_and_reencodes():
    seen = {}

    def images(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"b64_json": _b64_image("jpeg")}]})

    provider = ImageProvider(
        "xai-test",
        "https://api.x.ai/v1",
        "grok-imagine-image",
        edits=True,
        transparency=True,
        transport=httpx.MockTransport(images),
    )
    try:
        caps = provider.capabilities()
        assert provider.style == "xai" and caps["provider"] == "xai"
        assert caps["operations"] == ["generate"] and caps["qualities"] == ["medium"]
        data = await provider.generate(_ImageJob())
        assert validate_image(data) == "image/png"
        body = seen["body"]
        assert seen["url"] == "https://api.x.ai/v1/images/generations"
        assert body == {
            "model": "grok-imagine-image",
            "prompt": "A calm mountain landscape",
            "n": 1,
            "aspect_ratio": "3:2",
            "response_format": "b64_json",
        }
        with pytest.raises(ValueError, match="reference edits"):
            await provider.generate(_ImageJob(operation="edit"), png())
    finally:
        await provider.aclose()


async def test_xai_image_2_0_sends_quality_but_not_openai_fields():
    seen = {}

    def images(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"b64_json": _b64_image("jpeg")}]})

    provider = ImageProvider(
        "xai-test",
        "https://api.x.ai/v1/",
        "grok-imagine-image-2.0",
        edits=False,
        transport=httpx.MockTransport(images),
    )
    try:
        assert provider.capabilities()["qualities"] == ["low", "medium"]
        await provider.generate(_ImageJob(model="grok-imagine-image-2.0", quality="high", format="jpeg"))
        body = seen["body"]
        assert body["quality"] == "medium" and body["aspect_ratio"] == "3:2"
        assert body["response_format"] == "b64_json"
        for omitted in ("size", "output_format", "moderation", "background", "safety_identifier"):
            assert omitted not in body

        def url_only(request):
            return httpx.Response(200, json={"data": [{"url": "https://example.invalid/image.jpg"}]})

        await provider.aclose()
        provider = ImageProvider(
            "xai-test",
            "https://api.x.ai/v1",
            "grok-imagine-image-2.0",
            transport=httpx.MockTransport(url_only),
        )
        with pytest.raises(ValueError, match="base64"):
            await provider.generate(_ImageJob(model="grok-imagine-image-2.0", format="jpeg"))
    finally:
        await provider.aclose()


async def test_non_xai_host_keeps_openai_image_fields_even_for_a_grok_model_name():
    seen = {}

    def images(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"b64_json": _b64_image("png")}]})

    provider = ImageProvider(
        "image-key", "https://images.example/v1", "grok-imagine-image", transport=httpx.MockTransport(images)
    )
    try:
        await provider.generate(_ImageJob(quality="high"))
        assert seen["body"]["size"] == "1536x1024" and seen["body"]["moderation"] == "auto"
        assert seen["body"]["output_format"] == "png" and "aspect_ratio" not in seen["body"]
    finally:
        await provider.aclose()


def test_moderation_decision_parser_fails_closed():
    assert parse_decision("allow") is True
    assert parse_decision("Block.") is False
    assert parse_decision('{"allowed": true}') is True
    assert parse_decision("block\nThe image is unsafe") is False
    for text in ("sure, allow this", "allow please", '{"allowed": "true"}', "", "```\nmaybe\n```"):
        with pytest.raises(ModerationRejected):
            parse_decision(text)


async def test_llm_moderator_fail_closed_and_local_rules():
    calls = []

    def chat(request):
        calls.append(json.loads(request.content))
        reply = calls[-1]["messages"][1]["content"]
        if isinstance(reply, str) and reply == "down":
            return httpx.Response(503)
        if isinstance(reply, str) and reply == "garbage":
            content = "I can help with that"
        elif isinstance(reply, str) and reply == "blocked":
            content = "block"
        else:
            content = "allow"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    moderator = LlmModerator("xai-test", "https://api.x.ai/v1", "grok-4.7", transport=httpx.MockTransport(chat))
    try:
        with pytest.raises(ModerationRejected, match="nonconsensual"):
            await moderator.check("please nudify this photo")
        with pytest.raises(ModerationRejected, match="impersonation"):
            await moderator.check("impersonate a public figure")
        assert not calls
        await moderator.check("A calm mountain landscape")
        assert calls[0]["model"] == "grok-4.7" and calls[0]["messages"][0]["role"] == "system"
        with pytest.raises(ModerationRejected, match="blocked"):
            await moderator.check("blocked")
        with pytest.raises(ModerationRejected, match="unavailable"):
            await moderator.check("down")
        with pytest.raises(ModerationRejected, match="did not return a decision"):
            await moderator.check("garbage")
        await moderator.check("Screen generated image for safety", png(), "image/png")
        image_part = calls[-1]["messages"][1]["content"][1]["image_url"]["url"]
        assert image_part.startswith("data:image/png;base64,")
        await moderator.check("Screen generated image for safety", image_bytes("webp"), "image/webp")
        webp_part = calls[-1]["messages"][1]["content"][1]["image_url"]["url"]
        assert webp_part.startswith("data:image/png;base64,")
    finally:
        await moderator.aclose()


def test_llm_screening_runs_before_image_generation(client, auth, studio):
    calls = []

    def chat(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "block"}}]})

    runtime = client.app.state.creative
    old = runtime.moderator
    runtime.moderator = LlmModerator("xai-test", "https://api.x.ai/v1", "grok-4.7", transport=httpx.MockTransport(chat))
    client.portal.call(old.aclose)
    queued = generate(client, auth)
    work(client)
    failed = job(client, auth, queued["id"])
    assert failed["status"] == "failed" and "blocked" in failed["error"]
    assert not studio["image_calls"] and calls


async def test_xai_only_settings_enable_image_and_llm_moderation(tmp_path):
    shared = dict(
        _env_file=None,
        openai_api_key=None,
        creative_moderation_api_key=None,
        creative_enabled=True,
        creative_image_api_key="xai-test",
        creative_image_base_url="https://api.x.ai/v1",
        creative_image_model="grok-imagine-image",
        creative_image_edits=False,
        creative_image_transparency=False,
        creative_storage_dir=str(tmp_path),
    )
    openai_only = CreativeRuntime(Settings(**shared, creative_moderation_provider="openai"))
    assert openai_only.moderator is None and openai_only.image is None
    with_openai = {**shared, "openai_api_key": "sk-moderation", "creative_moderation_provider": "openai"}
    openai_key = CreativeRuntime(Settings(**with_openai))
    xai = CreativeRuntime(Settings(**shared, creative_moderation_provider="llm"))
    try:
        assert isinstance(xai.moderator, LlmModerator)
        assert xai.moderator.model == "grok-4.7"
        assert xai.moderator.client.headers["authorization"] == "Bearer xai-test"
        assert xai.image is not None and xai.image.style == "xai"
        assert xai.image.capabilities()["model"] == "grok-imagine-image"
        assert isinstance(openai_key.moderator, Moderator) and openai_key.image is not None
    finally:
        await openai_key.aclose()
        await xai.aclose()
