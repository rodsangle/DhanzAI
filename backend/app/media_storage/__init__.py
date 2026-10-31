"""Private local development storage and private, encrypted S3-compatible production storage."""

from __future__ import annotations

import asyncio
import io
import warnings

from PIL import Image, UnidentifiedImageError

from app.services.storage import FileStorage

MAX_REFERENCE_BYTES = 8 * 1024 * 1024


def validate_image(data: bytes) -> str:
    if not data or len(data) > MAX_REFERENCE_BYTES:
        raise ValueError("Reference images must be between 1 byte and 8 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ("PNG", "JPEG", "WEBP") or image.width * image.height > 16_000_000:
                    raise ValueError("Use a PNG, JPEG or WebP image of at most 16 megapixels")
                mime = Image.MIME[image.format]
                image.verify()
                return mime
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError("The image is damaged or exceeds the pixel limit") from None


class S3Storage:
    def __init__(self, settings):
        import boto3

        if not settings.creative_s3_bucket:
            raise ValueError("CREATIVE_S3_BUCKET is required for S3 storage")
        self.bucket = settings.creative_s3_bucket
        self.client = boto3.client(
            "s3", region_name=settings.creative_s3_region, endpoint_url=settings.creative_s3_endpoint or None
        )

    @staticmethod
    def path(key):
        if not key.isalnum():
            raise ValueError("Invalid media key")
        return f"creative/{key}"

    async def put(self, data):
        import secrets

        key = secrets.token_hex(24)
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=self.path(key),
            Body=data,
            ServerSideEncryption="AES256",
            ContentType="application/octet-stream",
        )
        return key

    async def get(self, key):
        def read():
            response = self.client.get_object(Bucket=self.bucket, Key=self.path(key))
            try:
                return response["Body"].read()
            finally:
                response["Body"].close()

        return await asyncio.to_thread(read)

    async def delete(self, key):
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=self.path(key))


def build_storage(settings):
    return S3Storage(settings) if settings.creative_storage == "s3" else FileStorage(settings.creative_storage_dir)
