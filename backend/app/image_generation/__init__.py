"""Image generation for the OpenAI Images API and xAI's Imagine API.

The wire format follows the base URL host. https://api.x.ai uses aspect_ratio and
response_format=b64_json. OpenAI-only fields (size, output_format, moderation, background,
safety_identifier) are not sent there. quality is sent only for grok-imagine-image-2.0,
the one model whose docs accept it. Other hosts keep the OpenAI Images request.
"""

from __future__ import annotations

import base64
import hashlib
import io

import httpx
from PIL import Image

from app.content_moderation import image_api_style

SIZES = {"1:1": "1024x1024", "3:2": "1536x1024", "2:3": "1024x1536"}
_FORMATS = {"png": "PNG", "jpeg": "JPEG", "webp": "WEBP"}


def xai_quality_supported(model: str) -> bool:
    # Documented only for grok-imagine-image-2.0. grok-imagine-image rejects or ignores it.
    return model == "grok-imagine-image-2.0"


class ImageProvider:
    def __init__(self, key, base_url, model, *, transport=None, edits=True, transparency=True):
        self.model = model
        self.style = image_api_style(base_url)
        # xAI edits are a different JSON API and do not accept background=transparent.
        self.edits = edits and self.style != "xai"
        self.transparency = transparency and self.edits
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=240, headers={"Authorization": f"Bearer {key}"}, transport=transport
        )

    def capabilities(self):
        operations = ["generate"]
        if self.edits:
            operations += ["edit", "replace_background", "remove_object", "replace_object", "enhance"]
            if self.transparency:
                operations.append("remove_background")
        if self.style == "xai" and xai_quality_supported(self.model):
            qualities = ["low", "medium"]
        elif self.style == "xai":
            qualities = ["medium"]
        else:
            qualities = ["low", "medium", "high"]
        return {
            "kind": "image",
            "provider": "xai" if self.style == "xai" else "openai-compatible",
            "model": self.model,
            "ratios": list(SIZES),
            "qualities": qualities,
            "formats": ["png", "jpeg", "webp"],
            "reference": self.edits,
            "operations": operations,
            "durations": [],
            "resolutions": [],
            "audio": False,
        }

    def _body(self, job):
        options = job.options
        if self.style == "xai":
            body = {
                "model": job.model,
                "prompt": job.prompt,
                "n": 1,
                "aspect_ratio": options["ratio"],
                "response_format": "b64_json",
            }
            if xai_quality_supported(job.model):
                quality = "medium" if options["quality"] == "high" else options["quality"]
                if quality in ("low", "medium", "auto"):
                    body["quality"] = quality
            return body
        body = {
            "model": job.model,
            "prompt": job.prompt,
            "size": SIZES[options["ratio"]],
            "quality": options["quality"],
            "output_format": options["format"],
            "n": 1,
            "moderation": "auto",
            "safety_identifier": hashlib.sha256(str(job.user_id).encode()).hexdigest(),
        }
        if options["operation"] == "remove_background":
            body["prompt"] = (
                "Remove the background. Keep the subject unchanged on a transparent background. " + job.prompt
            )
            body["background"] = "transparent"
        elif options["operation"] != "generate":
            body["prompt"] = options["operation"].replace("_", " ") + ": " + job.prompt
        return body

    async def generate(self, job, reference=None):
        if self.style == "xai" and (reference is not None or job.options["operation"] != "generate"):
            raise ValueError("This image provider does not support reference edits")
        body = self._body(job)
        if reference is not None:
            response = await self.client.post(
                "/images/edits",
                data={k: str(v) for k, v in body.items()},
                files={"image[]": ("reference", reference, job.reference_mime)},
            )
        else:
            response = await self.client.post("/images/generations", json=body)
        response.raise_for_status()
        # Only base64 is accepted. Never fetch an arbitrary provider-returned image URL.
        payload = response.json()
        rows = payload.get("data") if isinstance(payload, dict) else None
        encoded = rows[0].get("b64_json") if rows and isinstance(rows[0], dict) else None
        if not isinstance(encoded, str):
            raise ValueError("Image provider did not return base64 image data")
        if len(encoded) > 24_000_000:
            raise ValueError("Generated image exceeds size limit")
        data = base64.b64decode(encoded, validate=True)
        if self.style == "xai":
            data = _match_format(data, job.options["format"])
        return data

    async def aclose(self):
        await self.client.aclose()


def _match_format(data: bytes, wanted: str) -> bytes:
    """xAI does not accept output_format. Re-encode so the app still receives the requested type."""
    fmt = _FORMATS[wanted]
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if image.format == fmt:
                return data
            frame = image.convert("RGB") if fmt == "JPEG" else image
            output = io.BytesIO()
            frame.save(output, format=fmt)
            return output.getvalue()
    except (OSError, ValueError, KeyError):
        raise ValueError("Image provider returned data that is not a PNG, JPEG or WebP") from None
