"""Run chat replies as background tasks that outlive the HTTP/WebSocket connection.

Mobile operating systems suspend apps and drop their connections when the screen locks or the
user switches away. Replies therefore keep generating on the server; when nobody is watching at
the moment a reply finishes, the user gets a push notification and the app loads the saved reply
when it is opened again. Stopping a reply is an explicit request (see `request_stop`).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

Finished = Callable[["TurnHandle"], Awaitable[None]]


@dataclass
class TurnHandle:
    message_id: uuid.UUID
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    events: list[dict] = field(default_factory=list)
    done: bool = False
    subscribers: int = 0
    task: asyncio.Task | None = None
    changed: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def final_event(self) -> dict | None:
        return self.events[-1] if self.done and self.events else None


class TurnManager:
    def __init__(self, on_unattended_finish: Finished | None = None):
        self._turns: dict[uuid.UUID, TurnHandle] = {}
        self._on_unattended_finish = on_unattended_finish

    def get(self, message_id: uuid.UUID) -> TurnHandle | None:
        return self._turns.get(message_id)

    def start(
        self, events: AsyncIterator[dict], *, message_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> TurnHandle:
        handle = TurnHandle(message_id, user_id, conversation_id)
        self._turns[message_id] = handle
        handle.task = asyncio.create_task(self._run(handle, events))
        return handle

    async def _run(self, handle: TurnHandle, events: AsyncIterator[dict]) -> None:
        try:
            async for event in events:
                handle.events.append(event)
                handle.changed.set()
        except asyncio.CancelledError:
            # run_turn has already saved the partial reply as "stopped".
            handle.events.append({"type": "stopped"})
        except Exception:  # noqa: BLE001 - must not kill the server loop
            log.exception("Reply %s crashed", handle.message_id)
            handle.events.append({"type": "error", "detail": "The reply failed unexpectedly.", "message": None})
        finally:
            handle.done = True
            handle.changed.set()
            self._turns.pop(handle.message_id, None)
        if handle.subscribers == 0 and self._on_unattended_finish is not None:
            try:
                await self._on_unattended_finish(handle)
            except Exception:  # noqa: BLE001 - notifications are best effort
                log.exception("Finish notification failed for %s", handle.message_id)

    async def subscribe(self, handle: TurnHandle) -> AsyncIterator[dict]:
        """Replay the reply's events so far, then follow it live. Leaving does not stop the reply."""
        handle.subscribers += 1
        sent = 0
        try:
            while True:
                while sent < len(handle.events):
                    yield handle.events[sent]
                    sent += 1
                if handle.done:
                    return
                handle.changed.clear()
                if sent < len(handle.events) or handle.done:
                    continue
                await handle.changed.wait()
        finally:
            handle.subscribers -= 1

    def cancel(self, message_id: uuid.UUID) -> bool:
        handle = self._turns.get(message_id)
        if handle is None or handle.task is None or handle.task.done():
            return False
        handle.task.cancel()
        return True

    async def shutdown(self) -> None:
        tasks = [h.task for h in self._turns.values() if h.task is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def wait_idle(self) -> None:
        """Wait for all running replies (tests)."""
        tasks = [h.task for h in list(self._turns.values()) if h.task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
