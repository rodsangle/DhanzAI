"""Account-owned Excel tools and chat guidance for existing connected commands."""

import asyncio
import functools
import hashlib
import json
import sys
import uuid

from sqlalchemy import select

from . import spreadsheet_engine as engine


def install():
    from app.services import assistant_tools as tools
    from dhanz_ai import ToolSpec

    async def run(ctx, args):
        from fastapi import HTTPException

        from app.models import KnowledgeDocument, User
        from app.services.files_service import build_files_runtime, store_upload

        try:
            operation = args.get("operation")
            if operation not in ("inspect", "edit", "create"):
                raise ValueError("Choose inspect, edit or create.")
            if ctx.settings is None:
                raise ValueError("File storage is unavailable.")
            files = ctx.files or build_files_runtime(ctx.settings)
            async with ctx.maker() as db:
                user = await db.get(User, ctx.user_id)
                if user is None or not user.is_active:
                    raise ValueError("Account is unavailable.")
                identifier = args.get("document_id")
                document = None
                if operation != "create":
                    if identifier:
                        document = await db.get(KnowledgeDocument, uuid.UUID(str(identifier)))
                        if document is None or document.user_id != ctx.user_id:
                            raise ValueError("Workbook is unavailable to this account.")
                    else:
                        attached = []
                        for value in getattr(ctx, "attachment_ids", []) or []:
                            doc = await db.get(KnowledgeDocument, uuid.UUID(str(value)))
                            if doc is not None and doc.user_id == ctx.user_id and doc.file_type == "xlsx":
                                attached.append(doc)
                        if len(attached) == 1:
                            document = attached[0]
                        else:
                            recent = list(
                                await db.scalars(
                                    select(KnowledgeDocument)
                                    .where(
                                        KnowledgeDocument.user_id == ctx.user_id,
                                        KnowledgeDocument.file_type == "xlsx",
                                    )
                                    .limit(10)
                                )
                            )
                            return tools.ToolOutcome(
                                {
                                    "needs_selection": True,
                                    "workbooks": [
                                        {"document_id": str(d.id), "filename": d.title} for d in (attached or recent)
                                    ],
                                },
                                "Select the workbook to inspect or edit",
                            )
                    if document.file_type != "xlsx" or not document.storage_key:
                        raise ValueError(
                            "Select a stored .xlsx workbook; macros and legacy .xls files are unsupported."
                        )
                data = await files.storage.get(document.storage_key) if document else None
                if operation == "inspect":
                    result = await asyncio.to_thread(engine.inspect, data, args.get("sheet"), args.get("range"))
                    result.update(document_id=str(document.id), filename=document.title)
                    return tools.ToolOutcome(result, "Inspected Excel workbook")
                filename = args.get("filename", "Edited_workbook.xlsx")
                if (
                    not isinstance(filename, str)
                    or not 1 <= len(filename) <= 150
                    or "/" in filename
                    or "\\" in filename
                    or not filename.lower().endswith(".xlsx")
                ):
                    raise ValueError("Use a plain .xlsx output filename, without a directory.")
                # Repeated identical calls within this reply reuse the already committed artifact.
                signature = hashlib.sha256(
                    json.dumps([str(document.id) if document else None, args], sort_keys=True).encode()
                ).hexdigest()
                cache = getattr(ctx, "_spreadsheet_results", {})
                if signature in cache:
                    return cache[signature]
                if len(cache) >= 4:
                    raise ValueError("Create at most four edited workbooks per reply.")
                output = await asyncio.to_thread(engine.edit, data, args.get("actions"))
                project_id = document.project_id if document else None
                new = await store_upload(
                    db,
                    ctx.settings,
                    files,
                    None,
                    user_id=ctx.user_id,
                    filename=filename,
                    data=output,
                    project_id=project_id,
                )
                await db.commit()
                result = tools.ToolOutcome(
                    {
                        "created": True,
                        "document_id": str(new.id),
                        "filename": new.title,
                        "original_preserved": True,
                        "note": "A real downloadable copy is attached. Formulas are saved, not calculated here; Excel recalculates when opened. Do not invent a URL or calculated values.",  # noqa: E501 - descriptive tool text
                    },
                    "Saved Excel workbook",
                    {"type": "download_file", "id": str(new.id), "filename": new.title, "file_type": "xlsx"},
                )
                cache[signature] = result
                ctx._spreadsheet_results = cache
                return result
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise tools.ToolInputError(str(exc)) from None
        except HTTPException as exc:
            raise tools.ToolInputError(str(exc.detail)) from None

    tools.TOOLS["excel_workbook"] = tools.Tool(
        ToolSpec(
            name="excel_workbook",
            description=(
                "Inspect, create or edit an account-owned uploaded XLSX workbook and attach a real downloadable copy. Inspect before editing existing files. Preserve source data. Use set_formula explicitly for formulas, never claim computed results. Server commands use connected_operations and run_connected_task, not this tool."  # noqa: E501 - descriptive tool text
            ),
            parameters={
                "type": "object",
                "required": ["operation"],
                "additionalProperties": False,
                "properties": {
                    "operation": {"type": "string", "enum": ["inspect", "edit", "create"]},
                    "document_id": {
                        "type": "string",
                        "description": "Owned uploaded XLSX UUID. Omit only when exactly one XLSX is attached, or to list choices.",  # noqa: E501 - descriptive tool text
                    },
                    "filename": {"type": "string"},
                    "sheet": {"type": "string", "description": "For targeted inspection: exact worksheet name."},
                    "range": {
                        "type": "string",
                        "description": "For targeted inspection: A1 range, max 500 cells, e.g. A32:AI32. Returns actual occupied cell addresses; do not ask user to inspect rows manually.",  # noqa: E501 - tool schema and guidance text
                    },  # noqa: E501
                    "actions": {
                        "type": "array",
                        "maxItems": 40,
                        "items": {
                            "type": "object",
                            "required": ["type", "sheet"],
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "add_sheet",
                                        "set_cells",
                                        "set_formula",
                                        "format_range",
                                        "freeze_panes",
                                        "auto_filter",
                                    ],
                                },
                                "sheet": {
                                    "type": "string",
                                    "description": "Existing name, or new name for add_sheet. New workbooks start with Sheet.",  # noqa: E501 - descriptive tool text
                                },
                                "range": {
                                    "type": "string",
                                    "description": "Bounded A1 rectangle, e.g. A1:F20. For formula fill, relative references translate from the top-left cell.",  # noqa: E501 - descriptive tool text
                                },
                                "values": {
                                    "type": "array",
                                    "items": {
                                        "type": "array",
                                        "items": {"type": ["string", "number", "boolean", "null"]},
                                    },
                                },
                                "formula": {
                                    "type": "string",
                                    "description": "Formula beginning =. Saved for Excel recalculation, no external links.",  # noqa: E501 - descriptive tool text
                                },
                                "format": {
                                    "type": "object",
                                    "properties": {
                                        **{k: {"type": "boolean"} for k in ("bold", "italic", "wrap_text", "border")},
                                        **{
                                            k: {"type": "string"}
                                            for k in ("font_color", "fill_color", "number_format", "horizontal")
                                        },
                                        **{k: {"type": "number"} for k in ("column_width", "row_height")},
                                    },
                                    "additionalProperties": False,
                                },
                            },
                            "additionalProperties": False,
                        },
                    },
                },
            },
        ),
        "Working on Excel workbook",
        run,
    )
    chat = sys.modules.get("app.services.chat_service")
    original = getattr(chat, "build_system_prompt", None)
    if original and not getattr(original, "_spreadsheet_guidance", False):

        @functools.wraps(original)
        def prompt(*args, **kwargs):
            text = original(*args, **kwargs)
            if kwargs.get("tools"):
                text += (
                    "\nWhen available, use excel_workbook to inspect and edit uploaded XLSX files, apply formatting and save formulas. "  # noqa: E501 - descriptive tool text
                    "Only claim a download after the tool saves it. Preserve original data and ask about ambiguous edits. "  # noqa: E501 - descriptive tool text
                    "Formulas recalculate in Excel; do not invent calculated values. Inspect requested destination rows with "  # noqa: E501 - tool schema and guidance text
                    "excel_workbook operation=inspect, sheet and range before overwriting. If all_empty=true, proceed; "
                    "ask about actual occupied cells only, rather than asking the user to inspect the workbook manually. "  # noqa: E501 - tool schema and guidance text
                    "Do not propose deleting existing formulas to bypass a validation error. For connected AWS commands, "  # noqa: E501 - tool schema and guidance text
                    "inspect connected_operations and execute the appropriate existing authorized grant with run_connected_task. "  # noqa: E501 - descriptive tool text
                    "These are named fixed commands, not an unrestricted shell. Queued is not completed; inspect recent_tasks "  # noqa: E501 - descriptive tool text
                    "before reporting completion. Do not ask for AWS credentials or invent a blanket inability to use connected tools."  # noqa: E501 - descriptive tool text
                )
            return text

        prompt._spreadsheet_guidance = True
        chat.build_system_prompt = prompt
