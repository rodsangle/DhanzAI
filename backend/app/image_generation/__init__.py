"""OpenAI Images API adapter; configurable base URL supports compatible commercial APIs."""

from __future__ import annotations

import base64
import hashlib

import httpx

SIZES = {"1:1": "1024x1024", "3:2": "1536x1024", "2:3": "1024x1536"}


class ImageProvider:
    def __init__(self, key, base_url, model, *, transport=None, edits=True, transparency=True):
        self.model = model
        self.edits, self.transparency = edits, transparency
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=240, headers={"Authorization": f"Bearer {key}"}, transport=transport
        )

    def capabilities(self):
        operations = ["generate"]
        if self.edits:
            operations += ["edit", "replace_background", "remove_object", "replace_object", "enhance"]
            if self.transparency:
                operations.append("remove_background")
        return {
            "kind": "image",
            "provider": "openai-compatible",
            "model": self.model,
            "ratios": list(SIZES),
            "qualities": ["low", "medium", "high"],
            "formats": ["png", "jpeg", "webp"],
            "reference": self.edits,
            "operations": operations,
            "durations": [],
            "resolutions": [],
            "audio": False,
        }

    async def generate(self, job, reference=None):
        options = job.options
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
        encoded = response.json()["data"][0]["b64_json"]
        if len(encoded) > 24_000_000:
            raise ValueError("Generated image exceeds size limit")
        return base64.b64decode(encoded, validate=True)

    async def aclose(self):
        await self.client.aclose()
