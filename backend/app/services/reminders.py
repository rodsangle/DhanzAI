"""Reminder delivery (push notification when due) and calendar export (.ics)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.models import Reminder
from app.services.push import Notification, PushService

log = logging.getLogger(__name__)


async def deliver_due_reminders(maker: async_sessionmaker[AsyncSession], push: PushService) -> int:
    """Notify about reminders that are due. Safe with several workers: each reminder is claimed
    with a conditional UPDATE, so it is announced once."""
    now = utcnow()
    async with maker() as db:
        due = list(
            await db.scalars(
                select(Reminder)
                .where(Reminder.due_at <= now, Reminder.notified_at.is_(None), Reminder.done_at.is_(None))
                .order_by(Reminder.due_at)
                .limit(100)
            )
        )
    sent = 0
    for reminder in due:
        async with maker() as db:
            claimed = await db.execute(
                update(Reminder)
                .where(Reminder.id == reminder.id, Reminder.notified_at.is_(None))
                .values(notified_at=now)
            )
            await db.commit()
        if not claimed.rowcount:
            continue  # another worker took it
        sent += 1
        if push.enabled:
            await push.notify_user(
                maker,
                reminder.user_id,
                Notification(title="Reminder", body=reminder.text, data={"reminder_id": str(reminder.id)}),
            )
    return sent


async def reminder_loop(maker: async_sessionmaker[AsyncSession], push: PushService, interval: int) -> None:
    while True:
        try:
            await deliver_due_reminders(maker, push)
        except Exception:  # noqa: BLE001 - try again next round
            log.exception("Reminder delivery failed")
        await asyncio.sleep(interval)


_ICS_ESCAPES = str.maketrans({"\\": "\\\\", ";": "\\;", ",": "\\,", "\n": "\\n"})


def _ics_text(value: str) -> str:
    """Escape text for an iCalendar property value (RFC 5545 section 3.3.11)."""
    return value.replace("\r\n", "\n").translate(_ICS_ESCAPES)


def _ics_time(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%SZ")


def _fold(line: str) -> str:
    """RFC 5545: lines longer than 75 octets continue on the next line after a space."""
    out, current = [], b""
    for ch in line:
        encoded = ch.encode()
        if len(current) + len(encoded) > (75 if not out else 74):
            out.append(current.decode())
            current = b""
        current += encoded
    out.append(current.decode())
    return "\r\n ".join(out)


def reminder_ics(reminder: Reminder) -> str:
    """An iCalendar event (with an alarm at the start) that calendar apps can import."""
    end = reminder.due_at + timedelta(minutes=reminder.duration_minutes or 15)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//DHANZ AI//Reminders//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{reminder.id}@dhanz-ai",
        f"DTSTAMP:{_ics_time(utcnow())}",
        f"DTSTART:{_ics_time(reminder.due_at)}",
        f"DTEND:{_ics_time(end)}",
        f"SUMMARY:{_ics_text(reminder.text)}",
        *([f"LOCATION:{_ics_text(reminder.location)}"] if reminder.location else []),
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_ics_text(reminder.text)}",
        "TRIGGER:PT0M",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
