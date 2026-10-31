"""Tools Dhanz can call while answering: calculator, unit conversion, time and dates, reminders,
email drafts, and Office files (Word, PDF, Excel, CSV, PowerPoint).

Every tool is deterministic server code. Nothing here acts outside DHANZ AI: reminders are stored
for the user (and announced by push notification), email drafts are handed to the user's own email
app to review and send, and documents are saved into the user's private library for download.
Inputs come from the model, so each tool validates them and reports problems back to the model as
an error result instead of failing the reply.
"""

from __future__ import annotations

import ast
import asyncio
import json
import math
import operator
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.base import utcnow
from app.models import Reminder
from app.services.files_service import FilesRuntime
from app.services.office_files import (
    DocumentBuildError,
    build_csv,
    build_docx,
    build_pdf,
    build_pptx,
    build_xlsx,
    filename_for,
    parse_sections,
    parse_sheets,
    parse_slides,
)
from dhanz_ai import ToolCall, ToolResult, ToolSpec
from dhanz_knowledge import Embedder

MAX_ACTIVE_REMINDERS = 200


class ToolInputError(Exception):
    """The model passed something the tool cannot use; the message is shown to the model."""


@dataclass
class ToolOutcome:
    data: dict  # returned to the model as JSON
    summary: str  # one line for the user ("12 × 7 = 84")
    action: dict | None = None  # something the app can offer (open email draft, add to calendar)


@dataclass
class ToolContext:
    maker: async_sessionmaker[AsyncSession]
    user_id: uuid.UUID
    conversation_id: uuid.UUID | None
    # The user's UTC offset from their device clock, for times given without one.
    local_offset: timedelta | None = None
    files: FilesRuntime | None = None
    embedder: Embedder | None = None
    settings: Settings | None = None


ToolFn = Callable[[ToolContext, dict], Awaitable[ToolOutcome]]


@dataclass(frozen=True)
class Tool:
    spec: ToolSpec
    label: str  # shown while the tool runs ("Calculating")
    run: ToolFn


# ---------------------------------------------------------------------------------- calculator

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCTIONS: dict[str, Callable[..., float]] = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "exp": math.exp,
    "ln": math.log,
    "log": lambda x, base=10: math.log(x, base),
    "log2": math.log2,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "radians": math.radians,
    "degrees": math.degrees,
    "factorial": lambda n: math.factorial(int(n)) if n == int(n) and 0 <= n <= 170 else _too_big(),
    "min": min,
    "max": max,
}
_CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _too_big():
    raise ToolInputError("Number too large to compute.")


_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def evaluate(expression: str) -> float | int:
    """Evaluate arithmetic safely (no names, attributes or calls other than the math functions above)."""
    # 1,234,567 -> 1234567 (thousands separators only; commas between function arguments stay).
    text = _THOUSANDS.sub("", expression).replace("×", "*").replace("÷", "/").replace("^", "**")
    if len(text) > 300:
        raise ToolInputError("Expression too long.")
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError:
        raise ToolInputError(f"Not a valid arithmetic expression: {expression!r}") from None

    def ev(node: ast.AST) -> float | int:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.Name) and node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](ev(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and (abs(right) > 1000 or abs(left) > 1e100):
                _too_big()
            return _BINOPS[type(node.op)](left, right)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _FUNCTIONS
            and not node.keywords
            and len(node.args) <= 3
        ):
            return _FUNCTIONS[node.func.id](*(ev(a) for a in node.args))
        raise ToolInputError("Only numbers, + - * / // % ^, parentheses and common math functions are allowed.")

    try:
        value = ev(tree)
    except ZeroDivisionError:
        raise ToolInputError("Division by zero.") from None
    except (OverflowError, ValueError) as exc:
        raise ToolInputError(f"Cannot compute this: {exc}.") from None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ToolInputError("The result is not a finite number.")
        if value.is_integer() and abs(value) < 1e15:
            return int(value)
        return float(f"{value:.12g}")
    return value


async def _calculate(ctx: ToolContext, args: dict) -> ToolOutcome:
    expression = str(args.get("expression", ""))
    result = evaluate(expression)
    return ToolOutcome({"expression": expression, "result": result}, f"{expression} = {result}")


# ---------------------------------------------------------------------------------- units

# Factor to the base unit of each dimension.
_UNITS: dict[str, tuple[str, float]] = {}


def _add(dimension: str, factor: float, *names: str) -> None:
    for n in names:
        _UNITS[n] = (dimension, factor)


_add("length", 1, "m", "meter", "meters", "metre", "metres")
_add("length", 1e-3, "mm", "millimeter", "millimeters", "millimetre", "millimetres")
_add("length", 1e-2, "cm", "centimeter", "centimeters", "centimetre", "centimetres")
_add("length", 1e3, "km", "kilometer", "kilometers", "kilometre", "kilometres")
_add("length", 0.0254, "in", "inch", "inches")
_add("length", 0.3048, "ft", "foot", "feet")
_add("length", 0.9144, "yd", "yard", "yards")
_add("length", 1609.344, "mi", "mile", "miles")
_add("length", 1852, "nmi", "nautical mile", "nautical miles")
_add("mass", 1, "kg", "kilogram", "kilograms")
_add("mass", 1e-3, "g", "gram", "grams")
_add("mass", 1e-6, "mg", "milligram", "milligrams")
_add("mass", 1000, "t", "tonne", "tonnes", "metric ton", "metric tons")
_add("mass", 0.45359237, "lb", "lbs", "pound", "pounds")
_add("mass", 0.028349523125, "oz", "ounce", "ounces")
_add("mass", 6.35029318, "st", "stone", "stones")
_add("volume", 1, "l", "liter", "liters", "litre", "litres")
_add("volume", 1e-3, "ml", "milliliter", "milliliters", "millilitre", "millilitres")
_add("volume", 1000, "m3", "cubic meter", "cubic meters")
_add("volume", 3.785411784, "gal", "gallon", "gallons", "us gallon", "us gallons")
_add("volume", 4.54609, "imperial gallon", "imperial gallons", "uk gallon", "uk gallons")
_add("volume", 0.946352946, "qt", "quart", "quarts")
_add("volume", 0.473176473, "pt", "pint", "pints", "us pint", "us pints")
_add("volume", 0.2365882365, "cup", "cups")
_add("volume", 0.0295735295625, "fl oz", "fluid ounce", "fluid ounces")
_add("volume", 0.01478676478125, "tbsp", "tablespoon", "tablespoons")
_add("volume", 0.00492892159375, "tsp", "teaspoon", "teaspoons")
_add("area", 1, "m2", "square meter", "square meters", "sq m")
_add("area", 1e6, "km2", "square kilometer", "square kilometers", "sq km")
_add("area", 0.09290304, "ft2", "square foot", "square feet", "sq ft")
_add("area", 4046.8564224, "acre", "acres")
_add("area", 1e4, "ha", "hectare", "hectares")
_add("speed", 1, "m/s", "meters per second")
_add("speed", 1 / 3.6, "km/h", "kph", "kilometers per hour")
_add("speed", 0.44704, "mph", "miles per hour")
_add("speed", 0.514444, "knot", "knots", "kn")
_add("time", 1, "s", "sec", "second", "seconds")
_add("time", 60, "min", "minute", "minutes")
_add("time", 3600, "h", "hr", "hour", "hours")
_add("time", 86400, "day", "days")
_add("time", 604800, "week", "weeks")
_add("data", 1, "b", "byte", "bytes")
_add("data", 1e3, "kb", "kilobyte", "kilobytes")
_add("data", 1e6, "mb", "megabyte", "megabytes")
_add("data", 1e9, "gb", "gigabyte", "gigabytes")
_add("data", 1e12, "tb", "terabyte", "terabytes")
_add("data", 1024, "kib", "kibibyte", "kibibytes")
_add("data", 1024**2, "mib", "mebibyte", "mebibytes")
_add("data", 1024**3, "gib", "gibibyte", "gibibytes")
_add("energy", 1, "j", "joule", "joules")
_add("energy", 1e3, "kj", "kilojoule", "kilojoules")
_add("energy", 4.184, "cal", "calorie", "calories")
_add("energy", 4184, "kcal", "kilocalorie", "kilocalories")
_add("energy", 3.6e6, "kwh", "kilowatt hour", "kilowatt hours")
_add("pressure", 1, "pa", "pascal", "pascals")
_add("pressure", 1e3, "kpa", "kilopascal", "kilopascals")
_add("pressure", 1e5, "bar", "bars")
_add("pressure", 6894.757293168, "psi")
_add("pressure", 101325, "atm", "atmosphere", "atmospheres")
_add("power", 1, "w", "watt", "watts")
_add("power", 1e3, "kw", "kilowatt", "kilowatts")
_add("power", 745.69987158227, "hp", "horsepower")

_TEMPERATURES = {
    "c": "C", "°c": "C", "celsius": "C",
    "f": "F", "°f": "F", "fahrenheit": "F",
    "k": "K", "kelvin": "K",
}  # fmt: skip


def convert(value: float, from_unit: str, to_unit: str) -> float:
    f, t = from_unit.strip().lower(), to_unit.strip().lower()
    if f in _TEMPERATURES and t in _TEMPERATURES:
        celsius = {"C": value, "F": (value - 32) * 5 / 9, "K": value - 273.15}[_TEMPERATURES[f]]
        return {"C": celsius, "F": celsius * 9 / 5 + 32, "K": celsius + 273.15}[_TEMPERATURES[t]]
    if f not in _UNITS:
        raise ToolInputError(f"Unknown unit {from_unit!r}.")
    if t not in _UNITS:
        raise ToolInputError(f"Unknown unit {to_unit!r}.")
    (dim_f, factor_f), (dim_t, factor_t) = _UNITS[f], _UNITS[t]
    if dim_f != dim_t:
        raise ToolInputError(f"Cannot convert {dim_f} ({from_unit}) to {dim_t} ({to_unit}).")
    return value * factor_f / factor_t


async def _convert_units(ctx: ToolContext, args: dict) -> ToolOutcome:
    try:
        value = float(args.get("value"))
    except (TypeError, ValueError):
        raise ToolInputError("value must be a number.") from None
    from_unit, to_unit = str(args.get("from_unit", "")), str(args.get("to_unit", ""))
    result = float(f"{convert(value, from_unit, to_unit):.10g}")
    return ToolOutcome(
        {"value": value, "from_unit": from_unit, "to_unit": to_unit, "result": result},
        f"{value:g} {from_unit} = {result:g} {to_unit}",
    )


# ---------------------------------------------------------------------------------- time & dates


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name.strip())
    except (ZoneInfoNotFoundError, ValueError):
        raise ToolInputError(
            f"Unknown time zone {name!r}. Use an IANA name such as 'Asia/Tokyo' or 'America/New_York'."
        ) from None


async def _world_time(ctx: ToolContext, args: dict) -> ToolOutcome:
    zone = _zone(str(args.get("timezone", "UTC")))
    now = datetime.now(zone)
    offset = now.strftime("%z")
    data = {
        "timezone": zone.key,
        "local_time": now.isoformat(timespec="minutes"),
        "weekday": now.strftime("%A"),
        "utc_offset": f"{offset[:3]}:{offset[3:]}",
    }
    return ToolOutcome(data, f"{zone.key}: {now.strftime('%A %H:%M')} (UTC{data['utc_offset']})")


def _parse_date(value: str, name: str) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ToolInputError(f"{name} must be a date like 2026-12-31.") from None


async def _date_difference(ctx: ToolContext, args: dict) -> ToolOutcome:
    start = _parse_date(args.get("start_date", ""), "start_date")
    end = _parse_date(args.get("end_date", ""), "end_date")
    days = (end - start).days
    weekdays = sum(1 for i in range(abs(days)) if (min(start, end) + timedelta(days=i)).weekday() < 5)
    data = {"days": days, "weeks": round(days / 7, 2), "weekdays_mon_to_fri": weekdays}
    return ToolOutcome(data, f"{start} → {end}: {days} days")


async def _date_add(ctx: ToolContext, args: dict) -> ToolOutcome:
    start = _parse_date(args.get("date", ""), "date")
    try:
        days, weeks = int(args.get("days", 0) or 0), int(args.get("weeks", 0) or 0)
        months, years = int(args.get("months", 0) or 0), int(args.get("years", 0) or 0)
    except (TypeError, ValueError):
        raise ToolInputError("days, weeks, months and years must be whole numbers.") from None
    month_index = start.month - 1 + months + 12 * years
    year, month = start.year + month_index // 12, month_index % 12 + 1
    if not 1 <= year <= 9999:
        raise ToolInputError("Resulting year is out of range.")
    last_day = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day
    shifted = date(year, month, min(start.day, last_day)) + timedelta(days=days + 7 * weeks)
    data = {"date": shifted.isoformat(), "weekday": shifted.strftime("%A")}
    return ToolOutcome(data, f"{shifted.isoformat()} ({data['weekday']})")


# ---------------------------------------------------------------------------------- reminders


def _due(ctx: ToolContext, value: str) -> datetime:
    try:
        due = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ToolInputError("due_at must be an ISO 8601 date-time such as 2026-11-02T09:00:00+01:00.") from None
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone(ctx.local_offset or timedelta()))
    due = due.astimezone(UTC)
    now = utcnow()
    if due < now - timedelta(minutes=1):
        raise ToolInputError("That time has already passed. Ask the user for a future time.")
    if due > now + timedelta(days=5 * 366):
        raise ToolInputError("Reminders can be at most five years ahead.")
    return due


def reminder_dict(r: Reminder) -> dict:
    return {
        "id": str(r.id),
        "text": r.text,
        "due_at": r.due_at.isoformat(),
        "duration_minutes": r.duration_minutes,
        "location": r.location,
        "done": r.done_at is not None,
    }


async def _create_reminder(ctx: ToolContext, args: dict) -> ToolOutcome:
    text = str(args.get("text", "")).strip()
    if not text:
        raise ToolInputError("text is required.")
    due = _due(ctx, args.get("due_at", ""))
    duration = args.get("duration_minutes")
    try:
        duration = int(duration) if duration not in (None, "") else None
    except (TypeError, ValueError):
        raise ToolInputError("duration_minutes must be a whole number.") from None
    if duration is not None and not 1 <= duration <= 24 * 60 * 14:
        raise ToolInputError("duration_minutes must be between 1 minute and 14 days.")
    location = str(args.get("location") or "").strip()[:200] or None
    async with ctx.maker() as db:
        active = await db.scalar(
            select(func.count(Reminder.id)).where(Reminder.user_id == ctx.user_id, Reminder.done_at.is_(None))
        )
        if (active or 0) >= MAX_ACTIVE_REMINDERS:
            raise ToolInputError("The user has too many open reminders. Ask them to clear some first.")
        reminder = Reminder(
            user_id=ctx.user_id,
            text=text[:500],
            due_at=due,
            duration_minutes=duration,
            location=location,
            conversation_id=ctx.conversation_id,
        )
        db.add(reminder)
        await db.commit()
        data = reminder_dict(reminder)
    return ToolOutcome(
        {"created": True, "reminder": data},
        f"Reminder set: {text[:80]}",
        {"type": "reminder", **data},
    )


async def _list_reminders(ctx: ToolContext, args: dict) -> ToolOutcome:
    async with ctx.maker() as db:
        rows = await db.scalars(
            select(Reminder)
            .where(Reminder.user_id == ctx.user_id, Reminder.done_at.is_(None))
            .order_by(Reminder.due_at)
            .limit(50)
        )
        items = [reminder_dict(r) for r in rows]
    return ToolOutcome({"reminders": items}, f"{len(items)} open reminders")


async def _cancel_reminder(ctx: ToolContext, args: dict) -> ToolOutcome:
    try:
        rid = uuid.UUID(str(args.get("reminder_id", "")))
    except ValueError:
        raise ToolInputError("reminder_id must be an id returned by list_reminders.") from None
    async with ctx.maker() as db:
        reminder = await db.get(Reminder, rid)
        if reminder is None or reminder.user_id != ctx.user_id:
            raise ToolInputError("No such reminder.")
        await db.delete(reminder)
        await db.commit()
    return ToolOutcome({"cancelled": True, "id": str(rid)}, f"Reminder cancelled: {reminder.text[:80]}")


# ---------------------------------------------------------------------------------- office files


def _title(args: dict, fallback: str) -> str:
    title = str(args.get("title") or "").replace("\x00", "").strip()[:300]
    if not title:
        raise ToolInputError(f"{fallback} is required.")
    return title


async def _save_office_file(ctx: ToolContext, filename: str, data: bytes, summary: str) -> ToolOutcome:
    if ctx.files is None or ctx.settings is None:
        raise ToolInputError("Saving files is not available on this server.")
    from app.services.files_service import store_generated

    async with ctx.maker() as db:
        try:
            doc = await store_generated(
                db,
                ctx.settings,
                ctx.files,
                ctx.embedder,
                user_id=ctx.user_id,
                filename=filename,
                data=data,
            )
            await db.commit()
            saved = {
                "document_id": str(doc.id),
                "filename": doc.title,
                "file_type": doc.file_type,
                "size_bytes": doc.size_bytes,
            }
        except DocumentBuildError as exc:
            raise ToolInputError(str(exc)) from None
    return ToolOutcome(
        {**saved, "saved": True, "note": "Saved to the user's library. They can download it; nothing was emailed."},
        summary,
        {"type": "file", **saved},
    )


async def _create_word_document(ctx: ToolContext, args: dict) -> ToolOutcome:
    fmt = str(args.get("format") or "docx")
    if fmt not in ("docx", "pdf"):
        raise ToolInputError("format must be docx or pdf.")
    title = _title(args, "title")
    try:
        sections = parse_sections(args.get("sections"))
        name = filename_for(str(args.get("filename") or title), fmt)
        data = await asyncio.to_thread(build_pdf if fmt == "pdf" else build_docx, title, sections)
    except DocumentBuildError as exc:
        raise ToolInputError(str(exc)) from None
    label = "PDF" if fmt == "pdf" else "Word document"
    return await _save_office_file(ctx, name, data, f"{label}: {name}")


async def _create_spreadsheet(ctx: ToolContext, args: dict) -> ToolOutcome:
    fmt = str(args.get("format") or "xlsx")
    if fmt not in ("xlsx", "csv"):
        raise ToolInputError("format must be xlsx or csv.")
    title = str(args.get("filename") or args.get("title") or "Spreadsheet")
    try:
        sheets = parse_sheets(args.get("sheets"))
        if fmt == "csv" and len(sheets) != 1:
            raise DocumentBuildError("CSV is one sheet. Use format xlsx for several sheets.")
        name = filename_for(title, fmt)
        if fmt == "csv":
            data = await asyncio.to_thread(build_csv, sheets[0]["columns"], sheets[0]["rows"])
        else:
            data = await asyncio.to_thread(build_xlsx, sheets)
    except DocumentBuildError as exc:
        raise ToolInputError(str(exc)) from None
    label = "CSV" if fmt == "csv" else "Excel workbook"
    return await _save_office_file(ctx, name, data, f"{label}: {name}")


async def _create_presentation(ctx: ToolContext, args: dict) -> ToolOutcome:
    title = _title(args, "title")
    subtitle = str(args.get("subtitle") or "").replace("\x00", "").strip()[:300]
    try:
        slides = parse_slides(args.get("slides"))
        name = filename_for(str(args.get("filename") or title), "pptx")
        data = await asyncio.to_thread(build_pptx, title, subtitle, slides)
    except DocumentBuildError as exc:
        raise ToolInputError(str(exc)) from None
    return await _save_office_file(ctx, name, data, f"PowerPoint: {name}")


# ---------------------------------------------------------------------------------- email drafts


async def _draft_email(ctx: ToolContext, args: dict) -> ToolOutcome:
    to = str(args.get("to") or "").strip()[:320]
    subject = str(args.get("subject") or "").strip()[:300]
    body = str(args.get("body") or "").strip()[:10_000]
    if not body:
        raise ToolInputError("body is required.")
    if to and ("@" not in to or any(c in to for c in " <>\r\n")):
        raise ToolInputError("to must be a plain email address (or leave it empty).")
    mailto = f"mailto:{quote(to, safe='@')}?subject={quote(subject)}&body={quote(body)}"
    action = {"type": "email", "to": to, "subject": subject, "body": body, "mailto": mailto}
    return ToolOutcome(
        {"draft_ready": True, "note": "The user can open it in their email app; nothing has been sent."},
        f"Email draft: {subject or '(no subject)'}",
        action,
    )


# ---------------------------------------------------------------------------------- registry


def _obj(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required}


_S = {"type": "string"}

TOOLS: dict[str, Tool] = {
    t.spec.name: t
    for t in [
        Tool(
            ToolSpec(
                "calculate",
                "Evaluate an arithmetic expression exactly. Supports + - * / // % ^ (power), parentheses, pi, e, "
                "sqrt, abs, round, floor, ceil, exp, ln, log(x, base), log2, sin/cos/tan (radians), radians, "
                "degrees, factorial, min, max. Express percentages as multiplication (15% of 80 -> 0.15*80) and write "
                "numbers without thousands separators.",
                _obj({"expression": {**_S, "description": "e.g. (1250*0.18)/12"}}, ["expression"]),
            ),
            "Calculating",
            _calculate,
        ),
        Tool(
            ToolSpec(
                "convert_units",
                "Convert a value between units of length, mass, volume, area, speed, time, data size, energy, "
                "pressure, power or temperature (C, F, K). Use unit symbols or names, e.g. km, mi, lb, kg, °F, cups.",
                _obj(
                    {"value": {"type": "number"}, "from_unit": _S, "to_unit": _S},
                    ["value", "from_unit", "to_unit"],
                ),
            ),
            "Converting units",
            _convert_units,
        ),
        Tool(
            ToolSpec(
                "world_time",
                "Current date and time in a time zone (IANA name, e.g. Asia/Tokyo, Europe/London).",
                _obj({"timezone": _S}, ["timezone"]),
            ),
            "Checking the time",
            _world_time,
        ),
        Tool(
            ToolSpec(
                "date_difference",
                "Number of days, weeks and Monday-Friday weekdays between two dates (YYYY-MM-DD).",
                _obj({"start_date": _S, "end_date": _S}, ["start_date", "end_date"]),
            ),
            "Counting days",
            _date_difference,
        ),
        Tool(
            ToolSpec(
                "date_add",
                "Add (or subtract, with negative numbers) days, weeks, months and years to a date (YYYY-MM-DD).",
                _obj(
                    {
                        "date": _S,
                        "days": {"type": "integer"},
                        "weeks": {"type": "integer"},
                        "months": {"type": "integer"},
                        "years": {"type": "integer"},
                    },
                    ["date"],
                ),
            ),
            "Working out the date",
            _date_add,
        ),
        Tool(
            ToolSpec(
                "create_reminder",
                "Set a reminder for the user. They get a notification at due_at and can add it to their calendar. "
                "Also use this for appointments/events (give duration_minutes and location when known).",
                _obj(
                    {
                        "text": {**_S, "description": "What to remind the user about"},
                        "due_at": {**_S, "description": "ISO 8601 date-time with UTC offset"},
                        "duration_minutes": {"type": "integer", "description": "For events: how long it lasts"},
                        "location": _S,
                    },
                    ["text", "due_at"],
                ),
            ),
            "Setting a reminder",
            _create_reminder,
        ),
        Tool(
            ToolSpec("list_reminders", "List the user's open reminders (soonest first).", _obj({}, [])),
            "Checking your reminders",
            _list_reminders,
        ),
        Tool(
            ToolSpec(
                "cancel_reminder",
                "Delete one of the user's reminders (ids come from list_reminders). Only when the user asks.",
                _obj({"reminder_id": _S}, ["reminder_id"]),
            ),
            "Cancelling a reminder",
            _cancel_reminder,
        ),
        Tool(
            ToolSpec(
                "draft_email",
                "Prepare an email for the user to review and send from their own email app. Nothing is sent.",
                _obj({"to": _S, "subject": _S, "body": _S}, ["subject", "body"]),
            ),
            "Drafting an email",
            _draft_email,
        ),
        Tool(
            ToolSpec(
                "create_word_document",
                "Create a real Word (.docx) or PDF file and save it to the user's library, with a download button. "
                "Use this when they ask for a document, report, letter or PDF. Put the actual content in sections "
                "(heading, paragraphs, bullets). No images, tables or tracked changes. Do not claim the file exists "
                "unless this tool succeeds.",
                _obj(
                    {
                        "title": _S,
                        "filename": {**_S, "description": "File name without a path. The extension is added."},
                        "format": {**_S, "enum": ["docx", "pdf"], "description": "Default docx"},
                        "sections": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "heading": _S,
                                    "paragraphs": {"type": "array", "items": _S},
                                    "bullets": {"type": "array", "items": _S},
                                },
                            },
                        },
                    },
                    ["title", "sections"],
                ),
            ),
            "Creating a document",
            _create_word_document,
        ),
        Tool(
            ToolSpec(
                "create_spreadsheet",
                "Create a real Excel workbook (.xlsx) or a CSV file and save it to the user's library. "
                "Use this for tables, budgets, lists and schedules. Each sheet has columns (header names) and rows "
                "(arrays of cell values in that order). Numbers should be numbers, not strings. "
                "Formulas are not supported and are stored as text. CSV allows one sheet. Several sheets need xlsx.",
                _obj(
                    {
                        "filename": _S,
                        "format": {**_S, "enum": ["xlsx", "csv"], "description": "Default xlsx"},
                        "sheets": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": _S,
                                    "columns": {"type": "array", "items": _S},
                                    "rows": {
                                        "type": "array",
                                        "items": {
                                            "type": "array",
                                            "items": {"type": ["string", "number", "boolean", "null"]},
                                        },
                                    },
                                },
                                "required": ["columns", "rows"],
                            },
                        },
                    },
                    ["filename", "sheets"],
                ),
            ),
            "Creating a spreadsheet",
            _create_spreadsheet,
        ),
        Tool(
            ToolSpec(
                "create_presentation",
                "Create a real PowerPoint (.pptx) and save it to the user's library. "
                "A title slide plus one slide per item (title and bullets, optional speaker notes). "
                "No images, charts or animations.",
                _obj(
                    {
                        "title": _S,
                        "filename": _S,
                        "subtitle": _S,
                        "slides": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": _S,
                                    "bullets": {"type": "array", "items": _S},
                                    "notes": _S,
                                },
                                "required": ["title"],
                            },
                        },
                    },
                    ["title", "slides"],
                ),
            ),
            "Creating a presentation",
            _create_presentation,
        ),
    ]
}


@dataclass
class ToolBox:
    """The tools for one reply, plus a log of what they did (shown in the app, saved with the message)."""

    ctx: ToolContext
    activity: list[dict] = field(default_factory=list)

    @property
    def specs(self) -> list[ToolSpec]:
        return [t.spec for t in TOOLS.values()]

    @staticmethod
    def label(name: str) -> str:
        tool = TOOLS.get(name)
        return tool.label if tool else name

    async def run(self, call: ToolCall) -> ToolResult:
        tool = TOOLS.get(call.name)
        try:
            if tool is None:
                raise ToolInputError(f"There is no tool called {call.name!r}.")
            if "_invalid_arguments" in call.arguments:
                raise ToolInputError("The tool arguments were not valid JSON.")
            outcome = await tool.run(self.ctx, call.arguments)
        except ToolInputError as exc:
            self.activity.append({"tool": call.name, "summary": str(exc), "error": True, "action": None})
            return ToolResult(call.id, call.name, json.dumps({"error": str(exc)}), is_error=True)
        self.activity.append({"tool": call.name, "summary": outcome.summary, "error": False, "action": outcome.action})
        return ToolResult(call.id, call.name, json.dumps(outcome.data, default=str))
