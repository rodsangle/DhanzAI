"""Runway Gen-4.5 asynchronous task adapter. No retired Sora endpoints are exposed."""

from __future__ import annotations

import base64
import re
from urllib.parse import urlsplit

import httpx


class VideoProvider:
    def __init__(self, key, *, transport=None):
        self.client = httpx.AsyncClient(
            base_url="https://api.dev.runwayml.com/v1",
            timeout=60,
            headers={"Authorization": f"Bearer {key}", "X-Runway-Version": "2024-11-06"},
            transport=transport,
        )

    def capabilities(self):
        return {
            "kind": "video",
            "provider": "runway",
            "model": "gen4.5",
            "ratios": ["16:9", "9:16"],
            "qualities": [],
            "formats": ["mp4"],
            "reference": True,
            "operations": ["generate"],
            "durations": [5, 10],
            "resolutions": ["720p"],
            "audio": False,
        }

    @staticmethod
    def task_id(value):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,150}", value):
            raise ValueError("Invalid provider task identifier")
        return value

    async def submit(self, job, reference=None):
        body = {
            "model": job.model,
            "promptText": job.prompt,
            "ratio": "1280:720" if job.options["ratio"] == "16:9" else "720:1280",
            "duration": job.options["duration"],
        }
        if reference is not None:
            body["promptImage"] = f"data:{job.reference_mime};base64,{base64.b64encode(reference).decode()}"
        response = await self.client.post("/image_to_video" if reference is not None else "/text_to_video", json=body)
        response.raise_for_status()
        return self.task_id(response.json()["id"])

    async def poll(self, task_id):
        response = await self.client.get(f"/tasks/{self.task_id(task_id)}")
        response.raise_for_status()
        return response.json()

    async def cancel(self, task_id):
        response = await self.client.delete(f"/tasks/{self.task_id(task_id)}")
        if response.status_code != 404:
            response.raise_for_status()

    async def download(self, url, limit):
        # Runway outputs are presigned CDN URLs. Do not forward the API credential to them.
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError("Invalid video output URL")
        if not (host.endswith(".cloudfront.net") or host.endswith(".runwayml.com") or host.endswith(".runway.com")):
            raise ValueError("Video output host is not on the Runway CDN allowlist")
        async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > limit:
                        raise ValueError("Video exceeds the configured media size limit")
        if len(data) < 12 or data[4:8] != b"ftyp":
            raise ValueError("Provider did not return an MP4 video")
        return bytes(data)

    async def aclose(self):
        await self.client.aclose()
