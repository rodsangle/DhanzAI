"""ClamAV (clamd) malware scanning over TCP using the INSTREAM command."""

from __future__ import annotations

import asyncio
import struct


class ScanError(Exception):
    """The scanner could not give a verdict."""


class MalwareFound(Exception):
    def __init__(self, signature: str):
        super().__init__(signature)
        self.signature = signature


class ClamAVScanner:
    def __init__(self, host: str, port: int = 3310, timeout: float = 30.0, chunk: int = 64 * 1024):
        self.host, self.port, self.timeout, self.chunk = host, port, timeout, chunk

    async def scan(self, data: bytes) -> None:
        """Return normally if clean; raise MalwareFound or ScanError otherwise."""
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), self.timeout)
        except (OSError, TimeoutError) as exc:
            raise ScanError(f"cannot reach clamd at {self.host}:{self.port}") from exc
        try:
            writer.write(b"zINSTREAM\0")
            for i in range(0, len(data), self.chunk):
                part = data[i : i + self.chunk]
                writer.write(struct.pack("!L", len(part)) + part)
            writer.write(struct.pack("!L", 0))
            await writer.drain()
            reply = (await asyncio.wait_for(reader.read(4096), self.timeout)).decode(errors="replace").strip("\0\n ")
        except (OSError, TimeoutError) as exc:
            raise ScanError("scan failed") from exc
        finally:
            writer.close()
        if reply.endswith("OK"):
            return
        if reply.endswith("FOUND"):
            raise MalwareFound(reply.split(":", 1)[-1].removesuffix("FOUND").strip())
        raise ScanError(f"unexpected clamd reply: {reply[:120]}")
