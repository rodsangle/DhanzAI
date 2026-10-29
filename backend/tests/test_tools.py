"""Assistant tools: calculator, units, dates, reminders (API, delivery, calendar export), email drafts, chat flow."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.db.base import utcnow
from app.db.session import make_engine, make_sessionmaker
from app.main import create_app
from app.services.assistant_tools import ToolBox, ToolContext, ToolInputError, convert, evaluate
from app.services.push import PushService
from app.services.reminders import deliver_due_reminders, reminder_ics
from dhanz_ai import (
    Capability,
    ChatMessage,
    CostTier,
    GenerationParams,
    ModelInfo,
    Orchestrator,
    Provider,
    StreamChunk,
    ToolCall,
)
from tests.conftest import parse_sse

# ------------------------------------------------------------------------------- pure tools


@pytest.mark.parametrize(
    ("expression", "result"),
    [
        ("2+3*4", 14),
        ("(1250*0.18)/12", 18.75),
        ("2^10", 1024),
        ("sqrt(144) + abs(-3)", 15),
        ("1,234 * 2", 2468),
        ("12 × 7 ÷ 4", 21),
        ("round(pi, 4)", 3.1416),
        ("log(1000)", 3),
        ("0.1 + 0.2", 0.3),
        ("factorial(10)", 3628800),
    ],
)
def test_calculator(expression, result):
    assert evaluate(expression) == result


@pytest.mark.parametrize(
    "expression",
    ["__import__('os')", "().__class__", "x + 1", "9**9**9", "1/0", "open('f')", "a" * 400, "sqrt(-1)"],
)
def test_calculator_rejects_unsafe_or_invalid(expression):
    with pytest.raises(ToolInputError):
        evaluate(expression)


def test_unit_conversion():
    assert round(convert(10, "km", "mi"), 4) == 6.2137
    assert convert(212, "°F", "C") == pytest.approx(100)
    assert convert(0, "c", "kelvin") == pytest.approx(273.15)
    assert convert(2, "cups", "ml") == pytest.approx(473.176473)
    assert convert(1, "GiB", "MB") == pytest.approx(1073.741824)
    with pytest.raises(ToolInputError, match="Cannot convert"):
        convert(1, "kg", "km")
    with pytest.raises(ToolInputError, match="Unknown unit"):
        convert(1, "parsec-ish", "km")


def box(maker=None, user_id=None, offset=None) -> ToolBox:
    return ToolBox(ToolContext(maker, user_id or uuid.uuid4(), None, local_offset=offset))


async def call(toolbox: ToolBox, name: str, **args):
    result = await toolbox.run(ToolCall("c1", name, args))
    return json.loads(result.content), result.is_error


async def test_date_tools():
    tb = box()
    data, err = await call(tb, "date_add", date="2026-01-31", months=1)
    assert not err and data == {"date": "2026-02-28", "weekday": "Saturday"}
    data, _ = await call(tb, "date_add", date="2026-10-29", days=-29, years=1)
    assert data["date"] == "2027-09-30"
    data, _ = await call(tb, "date_difference", start_date="2026-10-26", end_date="2026-11-09")
    assert data == {"days": 14, "weeks": 2.0, "weekdays_mon_to_fri": 10}
    data, _ = await call(tb, "world_time", timezone="Asia/Tokyo")
    assert data["timezone"] == "Asia/Tokyo" and data["utc_offset"] == "+09:00"
    data, err = await call(tb, "world_time", timezone="Mars/Olympus")
    assert err and "Unknown time zone" in data["error"]
    data, err = await call(tb, "no_such_tool")
    assert err and tb.activity[-1]["error"] is True


async def test_email_draft_is_a_mailto_action():
    tb = box()
    data, err = await call(tb, "draft_email", to="bob@example.com", subject="Lunch & plans", body="Hi Bob,\nNoon?")
    assert not err and data["draft_ready"] is True
    action = tb.activity[-1]["action"]
    assert action["mailto"] == "mailto:bob@example.com?subject=Lunch%20%26%20plans&body=Hi%20Bob%2C%0ANoon%3F"
    _, err = await call(tb, "draft_email", to="bob@example.com>, eve@x.y", subject="x", body="y")
    assert err


# ------------------------------------------------------------------------------- reminders


def make_client(settings, knowledge, provider=None, push=None) -> TestClient:
    limiter.reset()
    settings.reminder_check_seconds = 3600  # tests deliver reminders explicitly
    from tests.conftest import EchoProvider

    return TestClient(create_app(settings, Orchestrator([provider or EchoProvider()]), knowledge, push=push))


def signup(client, email="ada@example.com"):
    r = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correct-horse-9", "display_name": "Ada"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]["id"]


async def test_reminder_tools(settings):
    engine = make_engine(settings.database_url)
    maker = make_sessionmaker(engine)
    with make_client(settings, None) as client:
        _, uid = signup(client)
    tb = box(maker, uuid.UUID(uid), offset=timedelta(hours=2))
    soon = (utcnow() + timedelta(hours=3)).replace(microsecond=0)
    local = soon.astimezone(UTC).replace(tzinfo=None) + timedelta(hours=2)  # naive local time
    data, err = await call(tb, "create_reminder", text="Call mum", due_at=local.isoformat(), duration_minutes=30)
    assert not err and data["created"]
    assert datetime.fromisoformat(data["reminder"]["due_at"]) == soon  # interpreted in the user's offset
    assert tb.activity[-1]["action"]["type"] == "reminder"

    data, err = await call(tb, "create_reminder", text="Too late", due_at="2020-01-01T09:00:00+00:00")
    assert err and "already passed" in data["error"]
    data, _ = await call(tb, "list_reminders")
    assert [r["text"] for r in data["reminders"]] == ["Call mum"]

    other = box(maker, uuid.uuid4())
    data, err = await call(other, "cancel_reminder", reminder_id=data["reminders"][0]["id"])
    assert err and data["error"] == "No such reminder."
    rid = (await call(tb, "list_reminders"))[0]["reminders"][0]["id"]
    data, err = await call(tb, "cancel_reminder", reminder_id=rid)
    assert not err and (await call(tb, "list_reminders"))[0]["reminders"] == []
    await engine.dispose()


class RecordingPush(PushService):
    def __init__(self):
        super().__init__([])
        self.sent = []

    @property
    def enabled(self):
        return True

    async def notify_user(self, maker, user_id, notification):
        self.sent.append((user_id, notification))
        return 1


def test_reminders_api_delivery_and_calendar_export(settings, knowledge):
    push = RecordingPush()
    with make_client(settings, knowledge, push=push) as client:
        h, _ = signup(client)
        bob, _ = signup(client, "bob@example.com")
        due = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        r = client.post(
            "/api/v1/reminders",
            json={"text": "Dentist; bring card, ID", "due_at": due, "duration_minutes": 45, "location": "Main St"},
            headers=h,
        )
        assert r.status_code == 201, r.text
        rid = r.json()["id"]
        assert (
            client.post("/api/v1/reminders", json={"text": "x", "due_at": "2026-12-01T09:00:00"}, headers=h).status_code
            == 422
        )
        assert client.get(f"/api/v1/reminders/{rid}", headers=bob).status_code in (404, 405)
        assert client.patch(f"/api/v1/reminders/{rid}", json={"done": True}, headers=bob).status_code == 404

        ics = client.get(f"/api/v1/reminders/{rid}/calendar.ics", headers=h)
        assert ics.headers["content-type"].startswith("text/calendar")
        assert "SUMMARY:Dentist\\; bring card\\, ID" in ics.text and "LOCATION:Main St" in ics.text
        assert ics.text.count("BEGIN:VEVENT") == 1 and "\r\n" in ics.text

        # Not due yet: nothing is sent.
        maker = client.app.state.sessionmaker
        assert client.portal.call(deliver_due_reminders, maker, push) == 0
        past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        client.patch(f"/api/v1/reminders/{rid}", json={"due_at": past}, headers=h)
        assert client.portal.call(deliver_due_reminders, maker, push) == 1
        assert client.portal.call(deliver_due_reminders, maker, push) == 0  # announced once
        assert push.sent[0][1].title == "Reminder" and push.sent[0][1].data == {"reminder_id": rid}
        assert client.get("/api/v1/reminders", headers=h).json()[0]["notified_at"] is not None

        # Moving it re-arms the notification; completing hides it from the default list.
        client.patch(f"/api/v1/reminders/{rid}", json={"due_at": past}, headers=h)
        assert client.portal.call(deliver_due_reminders, maker, push) == 1
        client.patch(f"/api/v1/reminders/{rid}", json={"done": True}, headers=h)
        assert client.get("/api/v1/reminders", headers=h).json() == []
        assert len(client.get("/api/v1/reminders", params={"include_done": True}, headers=h).json()) == 1
        assert client.delete(f"/api/v1/reminders/{rid}", headers=h).status_code == 204


def test_ics_folds_long_lines():
    from app.models import Reminder

    r = Reminder(id=uuid.uuid4(), text="é" * 100, due_at=datetime(2026, 11, 2, 8, tzinfo=UTC))
    for line in reminder_ics(r).split("\r\n"):
        assert len(line.encode()) <= 75


# ------------------------------------------------------------------------------- chat with tools


class ToolCallingProvider(Provider):
    """Asks for the given tool calls first, then answers with whatever the tool results said."""

    name = "toolbot"

    def __init__(self, calls: list[ToolCall]):
        super().__init__()
        self.calls = calls
        self.requests: list[list[ChatMessage]] = []

    def is_configured(self) -> bool:
        return True

    def models(self) -> list[ModelInfo]:
        caps = frozenset({Capability.CHAT, Capability.TOOLS})
        return [ModelInfo(self.name, "tb-1", "ToolBot", caps, CostTier.LOW)]

    async def stream(
        self, model: str, messages: Sequence[ChatMessage], params: GenerationParams, tools=()
    ) -> AsyncIterator[StreamChunk]:
        self.requests.append(list(messages))
        if messages[-1].role != "tool":
            yield StreamChunk(text="One moment. ")
            yield StreamChunk(tool_calls=tuple(self.calls))
            yield StreamChunk(done=True, input_tokens=20, output_tokens=5)
            return
        results = [m.tool_result.content for m in messages if m.role == "tool"]
        yield StreamChunk(text="Results: " + " | ".join(results))
        yield StreamChunk(done=True, input_tokens=30, output_tokens=8)


def test_chat_uses_tools_and_saves_activity(settings, knowledge):
    due = (datetime.now(UTC) + timedelta(days=1)).replace(microsecond=0).isoformat()
    provider = ToolCallingProvider(
        [
            ToolCall("t1", "calculate", {"expression": "12*7"}),
            ToolCall("t2", "create_reminder", {"text": "Submit report", "due_at": due}),
        ]
    )
    with make_client(settings, knowledge, provider=provider) as client:
        h, _ = signup(client)
        cid = client.post("/api/v1/conversations", json={}, headers=h).json()["id"]
        client_time = datetime.now(UTC).astimezone(UTC).isoformat()
        r = client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={"content": "What is 12*7? Also remind me to submit the report tomorrow.", "client_time": client_time},
            headers=h,
        )
        events = parse_sse(r.text)
        tool_events = [e for e in events if e["type"] == "tool"]
        assert tool_events[0] == {"type": "tool", "stage": "running", "labels": ["Calculating", "Setting a reminder"]}
        assert [a["summary"] for a in tool_events[1]["activity"]] == ["12*7 = 84", "Reminder set: Submit report"]
        done = events[-1]["message"]
        assert done["content"].startswith("One moment. Results: ")
        assert '"result": 84' in done["content"]
        assert done["input_tokens"] == 50 and done["output_tokens"] == 13
        assert done["tool_activity"][1]["action"]["type"] == "reminder"

        # Saved with the message, and the reminder exists for the user.
        saved = client.get(f"/api/v1/conversations/{cid}", headers=h).json()["messages"][-1]
        assert saved["tool_activity"] == done["tool_activity"]
        reminders = client.get("/api/v1/reminders", headers=h).json()
        assert reminders[0]["text"] == "Submit report" and reminders[0]["conversation_id"] == cid

        # The model was told the user's local time and the tool rules.
        system = provider.requests[0][0].content
        assert "user's local date and time" in system and "Use the calculator" in system


def test_tools_can_be_disabled(settings, knowledge):
    settings.assistant_tools_enabled = False
    provider = ToolCallingProvider([ToolCall("t1", "calculate", {"expression": "1+1"})])
    with make_client(settings, knowledge, provider=provider) as client:
        h, _ = signup(client)
        cid = client.post("/api/v1/conversations", json={}, headers=h).json()["id"]
        r = client.post(f"/api/v1/conversations/{cid}/messages", json={"content": "1+1"}, headers=h)
        assert not [e for e in parse_sse(r.text) if e["type"] == "tool"]
        assert "Use the calculator" not in provider.requests[0][0].content


def test_client_time_is_validated():
    from app.services.chat_service import parse_client_time

    assert parse_client_time("2026-10-29T10:00:00") is None  # no offset
    assert parse_client_time("not a time") is None
    assert parse_client_time("1999-01-01T00:00:00+00:00") is None  # implausible
    now = datetime.now(UTC).astimezone().isoformat()
    assert parse_client_time(now) is not None


async def test_reminder_delivery_survives_concurrent_workers(settings):
    """Two workers delivering at once announce each reminder exactly once."""
    with make_client(settings, None) as client:
        h, _ = signup(client)
        past = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
        for i in range(3):
            client.post("/api/v1/reminders", json={"text": f"r{i}", "due_at": past}, headers=h)
    engine = make_engine(settings.database_url)
    maker = make_sessionmaker(engine)
    push = RecordingPush()
    counts = await asyncio.gather(deliver_due_reminders(maker, push), deliver_due_reminders(maker, push))
    assert sum(counts) == 3 and len(push.sent) == 3
    await engine.dispose()
