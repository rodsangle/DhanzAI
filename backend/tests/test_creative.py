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

from app.content_moderation import Moderator
from app.db.base import utcnow
from app.generation_jobs import cleanup, process_one
from app.image_generation import ImageProvider
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
