import io
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image
from pydantic import ValidationError

from app.core.config import Settings
from app.media_storage import S3Storage, validate_image
from app.video_generation import VideoProvider


@pytest.mark.parametrize("format,mime", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")])
def test_real_image_validation(format, mime):
    output = io.BytesIO()
    Image.new("RGB", (20, 20)).save(output, format=format)
    assert validate_image(output.getvalue()) == mime
    with pytest.raises(ValueError):
        validate_image(b"<svg onload=alert(1)>")
    with pytest.raises(ValueError):
        validate_image(b"x" * (8 * 1024 * 1024 + 1))


async def test_private_encrypted_s3_storage_contract(monkeypatch):
    calls = []

    class Client:
        def put_object(self, **kwargs):
            calls.append(kwargs)

        def get_object(self, **kwargs):
            calls.append(kwargs)
            return {"Body": io.BytesIO(b"private bytes")}

        def delete_object(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: Client())
    storage = S3Storage(
        SimpleNamespace(
            creative_s3_bucket="private-media",
            creative_s3_region="us-east-1",
            creative_s3_endpoint="https://s3.example",
        )
    )
    key = await storage.put(b"private bytes")
    assert calls[0]["ServerSideEncryption"] == "AES256"
    assert "ACL" not in calls[0]
    assert calls[0]["Key"] == f"creative/{key}"
    assert await storage.get(key) == b"private bytes"
    await storage.delete(key)
    with pytest.raises(ValueError):
        await storage.get("../../another-user")


def test_production_requires_cloud_storage_and_tls():
    with pytest.raises(ValidationError, match="private S3"):
        Settings(
            app_env="production",
            creative_enabled=True,
            jwt_secret="x" * 40,
            database_url="postgresql+asyncpg://db/dhanz",
        )
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            app_env="production",
            creative_storage="s3",
            creative_s3_endpoint="http://s3.example",
            jwt_secret="x" * 40,
            database_url="postgresql+asyncpg://db/dhanz",
        )
    with pytest.raises(ValidationError, match="moderation"):
        Settings(
            app_env="production",
            creative_enabled=True,
            creative_storage="s3",
            creative_moderation_base_url="http://moderation.example",
            jwt_secret="x" * 40,
            database_url="postgresql+asyncpg://db/dhanz",
        )


async def test_video_download_no_credentials_redirects_or_oversized_files(monkeypatch):
    provider = VideoProvider("never-forward-this-key")
    client_type = httpx.AsyncClient
    response_bytes = b"\x00\x00\x00\x18ftypmp42test-video"
    status = 200

    def respond(request):
        assert "authorization" not in request.headers
        return httpx.Response(status, content=response_bytes, headers={"Location": "http://127.0.0.1/secret"})

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client_type(**kwargs, transport=httpx.MockTransport(respond))
    )
    try:
        url = "https://video.cloudfront.net/output.mp4"
        assert await provider.download(url, 1000) == response_bytes
        with pytest.raises(ValueError, match="size limit"):
            await provider.download(url, 10)
        response_bytes = b"not mp4"
        with pytest.raises(ValueError, match="MP4"):
            await provider.download(url, 1000)
        status = 302
        with pytest.raises(httpx.HTTPStatusError):
            await provider.download(url, 1000)
    finally:
        await provider.aclose()
