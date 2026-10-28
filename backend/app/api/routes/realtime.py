"""WebSocket chat endpoint.

Protocol (JSON text frames):
  -> {"type": "auth", "token": "<access token>"}          (must be the first frame, within 10 s)
  <- {"type": "ready", "user_id": "..."}
  -> {"type": "send", "request_id": "r1", "conversation_id": "...", "content": "...",
      "provider"?: "...", "model"?: "...", "edit_message_id"?: "..."}
  -> {"type": "regenerate", "request_id": "r2", "conversation_id": "...", "provider"?, "model"?}
  <- the same events as the SSE endpoints (meta, model, delta, done | error), each with request_id
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from app.api.deps import user_from_token
from app.core import rate_limit
from app.models import User
from app.schemas import RegenerateRequest, SendMessageRequest
from app.services import chat_service

router = APIRouter(tags=["realtime"])

AUTH_TIMEOUT_SECONDS = 10


@router.websocket("/ws/chat")
async def chat_socket(ws: WebSocket) -> None:
    app = ws.app
    settings, maker, orchestrator = app.state.settings, app.state.sessionmaker, app.state.orchestrator
    await ws.accept()
    try:
        first = await asyncio.wait_for(ws.receive_json(), timeout=AUTH_TIMEOUT_SECONDS)
        if not isinstance(first, dict) or first.get("type") != "auth" or not isinstance(first.get("token"), str):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED)
        async with maker() as db:
            user = await user_from_token(db, settings, first["token"])
            user_id = user.id
    except (TimeoutError, HTTPException, ValueError):
        await ws.close(code=4401, reason="Authentication required")
        return
    except WebSocketDisconnect:
        return

    await ws.send_json({"type": "ready", "user_id": str(user_id)})
    try:
        while True:
            frame = await ws.receive_json()
            request_id = frame.get("request_id") if isinstance(frame, dict) else None
            try:
                await _handle(ws, frame, user_id, request_id, settings, maker, orchestrator)
            except HTTPException as exc:
                await ws.send_json({"type": "error", "request_id": request_id, "detail": exc.detail})
            except ValidationError as exc:
                await ws.send_json({"type": "error", "request_id": request_id, "detail": exc.errors(include_url=False)})
    except (WebSocketDisconnect, ValueError):
        # ValueError: a non-JSON frame; drop the connection.
        return


async def _handle(ws: WebSocket, frame, user_id, request_id, settings, maker, orchestrator) -> None:
    if not isinstance(frame, dict) or frame.get("type") not in ("send", "regenerate"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown frame type")
    rate_limit.enforce(f"chat:{user_id}", settings.rate_limit_chat_per_minute)
    try:
        conversation_id = uuid.UUID(str(frame.get("conversation_id")))
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found") from None

    async with maker() as db:
        # Re-load the user per request so deactivation/deletion takes effect on open sockets.
        user = await db.get(User, user_id)
        if user is None or not user.is_active:
            await ws.close(code=4401, reason="Account unavailable")
            raise WebSocketDisconnect(code=4401)
        conv = await chat_service.get_owned_conversation(db, user, conversation_id)
        if frame["type"] == "send":
            body = SendMessageRequest.model_validate(frame)
            turn = await chat_service.prepare_send(db, settings, user, conv, body)
        else:
            body = RegenerateRequest.model_validate(frame)
            turn = await chat_service.prepare_regenerate(db, settings, user, conv, body)

    async for event in chat_service.run_turn(maker, orchestrator, settings, turn, ws.app.state.knowledge):
        await ws.send_json({**event, "request_id": request_id})
