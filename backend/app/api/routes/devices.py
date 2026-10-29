"""Register phones/tablets for push notifications."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import delete, select

from app.api.deps import CurrentUser, DbDep
from app.db.base import utcnow
from app.models import Device
from app.schemas import DeviceRegister, DeviceUnregister

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def register_device(body: DeviceRegister, user: CurrentUser, db: DbDep) -> Response:
    """Upsert by token. A token moves to the signed-in account (e.g. after switching accounts)."""
    device = await db.scalar(select(Device).where(Device.token == body.token))
    if device is None:
        device = Device(token=body.token, platform=body.platform, user_id=user.id)
        db.add(device)
    device.user_id = user.id
    device.platform = body.platform
    device.app_version = body.app_version
    device.last_seen_at = utcnow()
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/unregister", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_device(body: DeviceUnregister, user: CurrentUser, db: DbDep) -> Response:
    """Stop notifications to this device (called on sign-out or when notifications are turned off)."""
    await db.execute(delete(Device).where(Device.token == body.token, Device.user_id == user.id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
