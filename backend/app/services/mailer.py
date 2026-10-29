"""Outgoing email (password reset codes) over SMTP."""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings

log = logging.getLogger(__name__)


class Mailer(Protocol):
    async def send(self, to: str, subject: str, body: str) -> None: ...


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self.s = settings

    def _send_sync(self, msg: EmailMessage) -> None:
        s = self.s
        context = ssl.create_default_context()
        if s.smtp_security == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=20, context=context)
        else:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20)
        with server:
            if s.smtp_security == "starttls":
                server.starttls(context=context)
            if s.smtp_username:
                server.login(s.smtp_username, s.smtp_password or "")
            server.send_message(msg)

    async def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self.s.smtp_from or self.s.smtp_username or "no-reply@localhost"
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        await asyncio.to_thread(self._send_sync, msg)


def build_mailer(settings: Settings) -> Mailer | None:
    return SmtpMailer(settings) if settings.smtp_host else None
