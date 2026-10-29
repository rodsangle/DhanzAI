"""The user's reminders (set in chat by Dhanz or added by hand)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbDep, parse_uuid
from app.db.base import utcnow
from app.models import Reminder, User
from app.schemas import ReminderCreate, ReminderOut, ReminderUpdate
from app.services.assistant_tools import MAX_ACTIVE_REMINDERS
from app.services.reminders import reminder_ics

router = APIRouter(prefix="/reminders", tags=["reminders"])


async def _owned(db, user: User, reminder_id: str) -> Reminder:
    reminder = await db.get(Reminder, parse_uuid(reminder_id))
    if reminder is None or reminder.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reminder not found")
    return reminder


@router.get("", response_model=list[ReminderOut])
async def list_reminders(user: CurrentUser, db: DbDep, include_done: bool = Query(default=False)) -> list[Reminder]:
    stmt = select(Reminder).where(Reminder.user_id == user.id)
    if not include_done:
        stmt = stmt.where(Reminder.done_at.is_(None))
    return list(await db.scalars(stmt.order_by(Reminder.due_at).limit(500)))


@router.post("", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
async def create_reminder(body: ReminderCreate, user: CurrentUser, db: DbDep) -> Reminder:
    active = await db.scalar(
        select(func.count(Reminder.id)).where(Reminder.user_id == user.id, Reminder.done_at.is_(None))
    )
    if (active or 0) >= MAX_ACTIVE_REMINDERS:
        raise HTTPException(status.HTTP_409_CONFLICT, "Too many open reminders. Complete or delete some first.")
    reminder = Reminder(
        user_id=user.id,
        text=body.text.strip(),
        due_at=body.due_at,
        duration_minutes=body.duration_minutes,
        location=body.location,
    )
    db.add(reminder)
    await db.commit()
    return reminder


@router.patch("/{reminder_id}", response_model=ReminderOut)
async def update_reminder(reminder_id: str, body: ReminderUpdate, user: CurrentUser, db: DbDep) -> Reminder:
    reminder = await _owned(db, user, reminder_id)
    if body.text is not None:
        reminder.text = body.text.strip()
    if body.due_at is not None:
        reminder.due_at = body.due_at
        reminder.notified_at = None  # moved: announce it again at the new time
    if body.done is not None:
        reminder.done_at = utcnow() if body.done else None
    await db.commit()
    return reminder


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(reminder_id: str, user: CurrentUser, db: DbDep) -> Response:
    await db.delete(await _owned(db, user, reminder_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{reminder_id}/calendar.ics")
async def reminder_calendar_file(reminder_id: str, user: CurrentUser, db: DbDep) -> Response:
    """Download as an .ics file to add it to any calendar app."""
    reminder = await _owned(db, user, reminder_id)
    return Response(
        reminder_ics(reminder),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="dhanz-reminder.ics"'},
    )
