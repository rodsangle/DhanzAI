"""Account-private, transactional adaptation of the uploaded Boss starter."""

import contextlib
import hashlib
import json
import sqlite3
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

READS = {
    "status",
    "task_list",
    "event_list",
    "event_reminders",
    "agent_list",
    "decide_task",
    "decide_next",
    "note_list",
}
FIELDS = {
    "status": set(),
    "task_add": {"title", "description", "priority", "deadline", "timezone"},
    "task_list": {"status", "limit", "offset"},
    "task_update": {"task_id", "title", "description", "priority", "deadline", "timezone"},
    "task_complete": {"task_id"},
    "event_add": {"title", "deadline", "reminder", "timezone", "notes"},
    "event_list": {"limit", "offset"},
    "event_reminders": {"limit", "offset"},
    "event_ack": {"event_id"},
    "agent_add": {"agent", "role"},
    "agent_list": {"limit", "offset"},
    "agent_status": {"agent", "status"},
    "delegate": {"agent", "task_id"},
    "decide_task": {"task_id"},
    "decide_next": set(),
    "note_add": {"content"},
    "note_list": {"limit", "offset"},
}


def text(value, label, maximum=4000, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise ValueError(f"Provide {label} as text, at most {maximum} characters.")
    return value.strip()


def stamp(value, timezone=None):
    if value is None:
        return None
    raw = text(value, "an ISO-8601 date/time", 100)
    try:
        result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Use an ISO-8601 date/time with UTC offset, or supply an IANA timezone.") from None
    if result.tzinfo is None:
        if not timezone:
            raise ValueError("A timezone is required for a date/time without a UTC offset.")
        try:
            zone = ZoneInfo(text(timezone, "an IANA timezone", 100))
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Use a valid IANA timezone, such as America/New_York.") from None
        local = result.replace(tzinfo=zone)
        if local.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != result:
            raise ValueError("That local time does not exist because of daylight saving time. Choose another time.")
        if local.utcoffset() != local.replace(fold=1).utcoffset():
            raise ValueError("That local time occurs twice. Supply an explicit UTC offset.")
        result = local
    try:
        return result.astimezone(UTC).isoformat(timespec="seconds")
    except OverflowError:
        raise ValueError("This date/time is outside the supported range.") from None


def folder(storage_dir, owner):
    return Path(storage_dir) / "boss-agent" / str(uuid.UUID(str(owner)))


def execute(storage_dir, owner, args, request_key=None, now=None):
    if not isinstance(args, dict) or args.get("operation") not in FIELDS:
        raise ValueError("Choose a supported Boss operation.")
    operation = args["operation"]
    if set(args) - FIELDS[operation] - {"operation"}:
        raise ValueError("The request includes fields not used by this Boss operation.")
    write = operation not in READS
    if write and (
        not isinstance(request_key, str)
        or len(request_key) != 64
        or any(c not in "0123456789abcdef" for c in request_key)
    ):
        raise ValueError("A valid action key is required before saving Boss records.")
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("The current time must include its timezone.")
    instant = instant.astimezone(UTC)
    when = instant.isoformat(timespec="seconds")
    root = folder(storage_dir, owner)
    root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.parent.chmod(0o700)
    root.mkdir(exist_ok=True, mode=0o700)
    root.chmod(0o700)
    database = root / "boss.sqlite3"
    fingerprint = hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()
    with contextlib.closing(sqlite3.connect(database, timeout=10)) as db:
        database.chmod(0o600)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,kind TEXT NOT NULL,body TEXT NOT NULL)")
        db.execute(
            "CREATE TABLE IF NOT EXISTS receipts(key TEXT PRIMARY KEY,fingerprint TEXT,result TEXT,created INTEGER)"
        )
        with db:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if write:
                previous = db.execute("SELECT fingerprint,result FROM receipts WHERE key=?", (request_key,)).fetchone()
                if previous:
                    if previous[0] != fingerprint:
                        raise ValueError("This action key was already used for different instructions.")
                    return {**json.loads(previous[1]), "deduplicated": True}

            def records(kind):
                return [json.loads(row[0]) for row in db.execute("SELECT body FROM records WHERE kind=?", (kind,))]

            def get(kind, identifier):
                value = str(uuid.UUID(str(identifier)))
                row = db.execute("SELECT body FROM records WHERE kind=? AND id=?", (kind, value)).fetchone()
                if not row:
                    raise ValueError("Boss record not found in this account.")
                return json.loads(row[0])

            def save(kind, value, new=False):
                if new and db.execute("SELECT count(*) FROM records").fetchone()[0] >= 5000:
                    raise ValueError("This Boss account has reached its 5,000-record limit.")
                db.execute(
                    "INSERT INTO records VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                    (value["id"], kind, json.dumps(value)),
                )
                return value

            def add(kind, value):
                return save(kind, {"id": str(uuid.uuid4()), "created_at": when, **value}, True)

            def agent(name):
                name = text(name, "an agent name", 80)
                matches = [a for a in records("agent") if a["name"].casefold() == name.casefold()]
                if not matches:
                    raise ValueError("Register this agent name in Boss first.")
                return matches[0]

            def assignments(name):
                return [t["id"] for t in records("task") if t["status"] == "open" and t["assignee"] == name]

            def sync(name):
                if name:
                    value = agent(name)
                    if value["status"] != "offline":
                        value["status"] = "busy" if assignments(value["name"]) else "idle"
                        save("agent", value)

            def priority(value):
                if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
                    raise ValueError("Priority must be an integer from 1 to 5 (5 is highest).")
                return value

            def listed(rows):
                limit, offset = args.get("limit", 30), args.get("offset", 0)
                if type(limit) is not int or not 1 <= limit <= 50 or type(offset) is not int or not 0 <= offset <= 5000:
                    raise ValueError("Use a limit of 1–50 and an offset of 0–5000.")
                rows.sort(key=lambda r: (r["created_at"], r["id"]), reverse=True)
                return {
                    "items": rows[offset : offset + limit],
                    "total": len(rows),
                    "next_offset": offset + limit if offset + limit < len(rows) else None,
                }

            if operation == "status":
                tasks = records("task")
                result = {
                    "open_tasks": sum(t["status"] == "open" for t in tasks),
                    "completed_tasks": sum(t["status"] == "completed" for t in tasks),
                    "events": len(records("event")),
                    "agents": len(records("agent")),
                    "notes": len(records("note")),
                }
            elif operation == "task_add":
                result = {
                    "task": add(
                        "task",
                        {
                            "title": text(args.get("title"), "a title", 200),
                            "description": text(args.get("description", ""), "a description", empty=True),
                            "priority": priority(args.get("priority", 3)),
                            "deadline": stamp(args.get("deadline"), args.get("timezone")),
                            "status": "open",
                            "assignee": None,
                            "completed_at": None,
                        },
                    )
                }
            elif operation == "task_list":
                state = args.get("status", "open")
                if state not in ("open", "completed", "all"):
                    raise ValueError("Choose open, completed or all tasks.")
                result = listed([t for t in records("task") if state == "all" or t["status"] == state])
            elif operation in ("task_update", "task_complete"):
                value = get("task", args.get("task_id"))
                if operation == "task_complete":
                    value.update(status="completed", completed_at=value["completed_at"] or when)
                else:
                    if not set(args).intersection({"title", "description", "priority", "deadline"}):
                        raise ValueError("Specify a task field to update.")
                    for key in ("title", "description"):
                        if key in args:
                            value[key] = text(args[key], key, 200 if key == "title" else 4000, key == "description")
                    if "priority" in args:
                        value["priority"] = priority(args["priority"])
                    if "deadline" in args:
                        value["deadline"] = stamp(args["deadline"], args.get("timezone"))
                save("task", value)
                if operation == "task_complete":
                    sync(value["assignee"])
                result = {"task": value}
            elif operation == "event_add":
                deadline = stamp(args.get("deadline"), args.get("timezone"))
                reminder = stamp(args.get("reminder"), args.get("timezone"))
                if not deadline or (reminder and reminder > deadline):
                    raise ValueError("Provide an event deadline and a reminder no later than that deadline.")
                result = {
                    "event": add(
                        "event",
                        {
                            "title": text(args.get("title"), "an event title", 200),
                            "deadline": deadline,
                            "reminder": reminder,
                            "acknowledged_at": None,
                            "notes": text(args.get("notes", ""), "event notes", empty=True),
                        },
                    )
                }
            elif operation in ("event_list", "event_reminders"):
                events = records("event")
                if operation == "event_reminders":
                    events = [e for e in events if e["reminder"] and e["reminder"] <= when and not e["acknowledged_at"]]
                result = listed(events)
            elif operation == "event_ack":
                value = get("event", args.get("event_id"))
                value["acknowledged_at"] = value["acknowledged_at"] or when
                result = {"event": save("event", value)}
            elif operation == "agent_add":
                name = text(args.get("agent"), "an agent name", 80)
                if any(a["name"].casefold() == name.casefold() for a in records("agent")):
                    raise ValueError("That agent name is already registered in this Boss account.")
                result = {
                    "agent": add(
                        "agent",
                        {"name": name, "role": text(args.get("role", ""), "a role", 300, True), "status": "idle"},
                    )
                }
            elif operation == "agent_list":
                assigned = {}
                for task in records("task"):
                    if task["status"] == "open" and task["assignee"]:
                        assigned.setdefault(task["assignee"], []).append(task["id"])
                result = listed([{**a, "assigned_tasks": assigned.get(a["name"], [])} for a in records("agent")])
            elif operation == "agent_status":
                value = agent(args.get("agent"))
                if args.get("status") not in ("idle", "busy", "offline"):
                    raise ValueError("Choose idle, busy or offline for the recorded agent status.")
                value["status"] = args["status"]
                result = {"agent": save("agent", value)}
            elif operation == "delegate":
                task, target = get("task", args.get("task_id")), agent(args.get("agent"))
                if task["status"] != "open" or target["status"] == "offline":
                    raise ValueError("Assign an open task to a registered agent that is not marked offline.")
                previous = task["assignee"]
                task["assignee"] = target["name"]
                save("task", task)
                sync(previous)
                sync(target["name"])
                result = {"task": task, "assignment_recorded": True, "execution_started": False}
            elif operation in ("decide_task", "decide_next"):
                if operation == "decide_task":
                    task = get("task", args.get("task_id"))
                else:
                    tasks = [t for t in records("task") if t["status"] == "open"]
                    task = min(
                        tasks,
                        key=lambda t: (
                            0 if t["deadline"] and t["deadline"] < when else 1,
                            t["deadline"] or "9999",
                            -t["priority"],
                            t["created_at"],
                            t["id"],
                        ),
                        default=None,
                    )
                advice = (
                    "No open tasks."
                    if task is None
                    else "Already completed."
                    if task["status"] == "completed"
                    else "Overdue: prioritize this task."
                    if task["deadline"] and task["deadline"] < when
                    else "High priority: schedule soon."
                    if task["priority"] >= 4
                    else "Schedule in the normal queue."
                )
                result = {"task": task, "advice": advice, "execution_started": False}
            elif operation == "note_add":
                result = {
                    "note": add("note", {"content": text(args.get("content"), "a note")}),
                    "delivery": "Saved privately in Boss; not sent to another person or service.",
                }
            else:
                result = listed(records("note"))
            result.update(
                operation=operation,
                timezone="UTC",
                capabilities_note="Reminders are checked on request. Agent assignments are records; "
                "Boss does not launch workers, run server commands, publish code or send messages.",
            )
            if write:
                db.execute(
                    "INSERT INTO receipts VALUES(?,?,?,?)",
                    (request_key, fingerprint, json.dumps(result), time.time_ns()),
                )
                db.execute(
                    "DELETE FROM receipts WHERE key IN "
                    "(SELECT key FROM receipts ORDER BY created DESC LIMIT -1 OFFSET 10000)"
                )
            return result
