"""Private file storage for uploads (local filesystem; keys are random, never user-supplied)."""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path


class FileStorage:
    def __init__(self, base_dir: str | Path):
        self.base = Path(base_dir).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not key.isalnum():
            raise ValueError("invalid storage key")
        return self.base / key[:2] / key

    async def put(self, data: bytes) -> str:
        key = secrets.token_hex(24)
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(write)
        return key

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, True)
