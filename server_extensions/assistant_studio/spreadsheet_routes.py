"""Authenticated workbook ribbon reads and copy-on-save edits."""

import asyncio
import hashlib
import json
import uuid

from fastapi import APIRouter, HTTPException, Request, Response
from openpyxl.utils import get_column_letter
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.models import KnowledgeDocument
from app.services.files_service import build_files_runtime, store_upload

from . import spreadsheet_engine as engine

router = APIRouter(prefix="/spreadsheets", tags=["spreadsheets"])


async def owned(db, user, identifier):
    document = await db.get(KnowledgeDocument, identifier)
    if document is None or document.user_id != user.id or document.file_type != "xlsx" or not document.storage_key:
        raise HTTPException(404, "Workbook not found.")
    return document


def page(data, sheet, area):
    book = engine.load(data)
    sheet = sheet or book.sheetnames[0]
    if sheet not in book.sheetnames:
        raise ValueError("Worksheet not found.")
    a, b, c, d = engine.rectangle(area)
    if (c - a + 1) * (d - b + 1) > 2500:
        raise ValueError("View at most 2500 cells at once.")
    selected = book[sheet]
    row_count, column_count = selected.max_row, selected.max_column
    cells = []
    for row in selected.iter_rows(min_row=b, max_row=d, min_col=a, max_col=c):
        for cell in row:
            value = cell.value
            if cell.data_type == "f" and not isinstance(value, str):
                value = getattr(value, "text", None)

            def color(value):
                return (
                    value.rgb[-6:] if value is not None and value.type == "rgb" and isinstance(value.rgb, str) else None
                )

            cells.append(
                {
                    "cell": cell.coordinate,
                    "value": value if isinstance(value, (int, float, bool, str)) or value is None else str(value),
                    "formula": cell.data_type == "f",
                    "format": {
                        "bold": bool(cell.font.bold),
                        "italic": bool(cell.font.italic),
                        "underline": bool(cell.font.underline),
                        "font_size": cell.font.sz,
                        "font_color": color(cell.font.color),
                        "fill_color": color(cell.fill.fgColor) if cell.fill.patternType == "solid" else None,
                        "wrap_text": bool(cell.alignment.wrap_text),
                        "horizontal": cell.alignment.horizontal,
                        "number_format": cell.number_format,
                        "border": bool(cell.border.bottom.style),
                    },
                }
            )
    widths = {}
    for column in range(a, c + 1):
        dimension = next(
            (
                value
                for value in selected.column_dimensions.values()
                if value.min and value.max and value.min <= column <= value.max
            ),
            None,
        )
        widths[get_column_letter(column)] = (
            dimension.width if dimension is not None else (selected.sheet_format.defaultColWidth or 13)
        )
    heights = {
        str(row): selected.row_dimensions[row].height or selected.sheet_format.defaultRowHeight or 15
        for row in range(b, d + 1)
    }
    return {
        "widths": widths,
        "heights": heights,
        "sheet": sheet,
        "sheets": book.sheetnames,
        "rows": row_count,
        "columns": column_count,
        "range": area,
        "cells": cells,
        "note": "Formulas are saved without server calculation. Excel recalculates on opening.",
    }


@router.get("/{document_id}")
async def read(
    document_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    request: Request,
    response: Response,
    sheet: str | None = None,
    area: str = "A1:AN50",
):
    document = await owned(db, user, document_id)
    files = getattr(request.app.state, "files", None) or build_files_runtime(settings)
    try:
        result = await asyncio.to_thread(page, await files.storage.get(document.storage_key), sheet, area)
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(422, str(exc)) from None
    response.headers["Cache-Control"] = "private, no-store"
    return {"document_id": str(document.id), "filename": document.title, **result}


class Edit(BaseModel):
    request_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,64}$")
    filename: str = Field(min_length=6, max_length=150)
    actions: list[dict] = Field(min_length=1, max_length=40)


@router.post("/{document_id}/edits")
async def save(
    document_id: uuid.UUID, body: Edit, user: CurrentUser, db: DbDep, settings: SettingsDep, request: Request
):
    document = await owned(db, user, document_id)
    if "/" in body.filename or "\\" in body.filename or not body.filename.lower().endswith(".xlsx"):
        raise HTTPException(422, "Use a plain .xlsx filename without a directory.")
    identity = hashlib.sha256(f"{user.id}:{document_id}:{body.request_key}".encode()).hexdigest()
    fingerprint = hashlib.sha256(
        json.dumps([body.filename, body.actions], sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    prefix = "spreadsheet-edit:" + identity + ":"
    # A transaction lock deduplicates concurrent retries across PostgreSQL API workers.
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(text("SET LOCAL lock_timeout = '5s'"))
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": int.from_bytes(bytes.fromhex(identity[:16]), "big", signed=True)},
        )
    previous = await db.scalar(
        select(KnowledgeDocument).where(KnowledgeDocument.user_id == user.id, KnowledgeDocument.url.startswith(prefix))
    )
    if previous:
        if previous.url != prefix + fingerprint:
            raise HTTPException(409, "This save key was already used for different changes.")
        return {"id": str(previous.id), "filename": previous.title, "file_type": "xlsx", "original_preserved": True}
    files = getattr(request.app.state, "files", None) or build_files_runtime(settings)
    try:
        output = await asyncio.to_thread(engine.edit, await files.storage.get(document.storage_key), body.actions)
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(422, str(exc)) from None
    result = await store_upload(
        db, settings, files, None, user_id=user.id, filename=body.filename, data=output, project_id=document.project_id
    )
    result.url = prefix + fingerprint
    await db.commit()
    return {"id": str(result.id), "filename": result.title, "file_type": "xlsx", "original_preserved": True}


def install(app):
    if not getattr(app.state, "_spreadsheet_routes_installed", False):
        app.include_router(router, prefix=app.state.settings.api_prefix)
        app.state._spreadsheet_routes_installed = True
