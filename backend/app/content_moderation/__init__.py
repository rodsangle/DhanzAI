"""Fail-closed prompt/reference screening plus provider-side generation safeguards."""

from __future__ import annotations

import base64
import re

import httpx


class ModerationRejected(Exception):
    pass


class Moderator:
    def __init__(self, key, *, transport=None):
        self.client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            timeout=45,
            headers={"Authorization": f"Bearer {key}"},
            transport=transport,
        )

    async def check(self, prompt, image=None, mime=None):
        # Defense in depth: the classifier is not a complete consent or IP-rights detector.
        if re.search(r"\b(nonconsensual|non-consensual|nudify|undress|revenge porn|deepfake porn)\b", prompt, re.I):
            raise ModerationRejected("Requests involving nonconsensual intimate imagery are not allowed")
        if re.search(r"\b(impersonate|fake endorsement|deceptive deepfake)\b", prompt, re.I):
            raise ModerationRejected("Deceptive impersonation and false endorsements are not allowed")
        content = [{"type": "text", "text": prompt}]
        if image is not None:
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(image).decode()}"}}
            )
        response = await self.client.post("/moderations", json={"model": "omni-moderation-latest", "input": content})
        response.raise_for_status()
        results = response.json().get("results")
        if not results or any("flagged" not in result for result in results):
            raise ModerationRejected("Content screening did not return a decision")
        if any(result["flagged"] for result in results):
            raise ModerationRejected("This request or image was blocked by content safety screening")

    async def aclose(self):
        await self.client.aclose()
