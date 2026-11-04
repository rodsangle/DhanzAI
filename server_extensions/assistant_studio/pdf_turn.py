"""A PDF conversion turn creates a real attachment or reports a real failure."""

import asyncio
import contextlib
import re
import threading

from .pdf_excel import ConversionError, extract_pdf, workbook


def requested(question):
    text = question[:20000]
    return bool(
        re.search(r"\bpdfs?\b", text, re.I)
        and re.search(r"\b(excel|xlsx|workbook|spreadsheet)\b", text, re.I)
        and re.search(r"\b(convert|create|combine|extract|save|make)\b", text, re.I)
    )


async def run(maker, settings, turn, files, finalize, stop_requested):
    from fastapi import HTTPException

    from app.models import KnowledgeDocument
    from app.services.files_service import build_files_runtime, store_upload

    files = files or build_files_runtime(settings)
    activity = []
    text = ""
    outcome = "error"
    error = None
    cancelled = threading.Event()

    async def watch():
        while True:
            await asyncio.sleep(2)
            if await stop_requested(maker, turn.assistant_message_id):
                cancelled.set()
                return

    monitor = asyncio.create_task(watch())
    try:
        yield {"type": "research", "stage": "reading_files", "count": len(turn.attachment_ids)}
        originals = []
        async with maker() as db:
            for identifier in turn.attachment_ids:
                doc = await db.get(KnowledgeDocument, identifier)
                if doc is None or doc.user_id != turn.user_id:
                    raise ConversionError("An attached file is unavailable or not owned by this account.")
                if doc.file_type == "pdf":
                    if not doc.storage_key:
                        raise ConversionError("An attached PDF has no stored source file.")
                    originals.append((doc.title, doc.storage_key))
        if not originals:
            raise ConversionError("Select the PDF files on this message before requesting conversion.")
        if len(originals) > 10:
            raise ConversionError("Convert at most ten PDFs into one workbook at a time.")
        sources = []
        size = 0
        for name, key in originals:
            data = await files.storage.get(key)
            size += len(data)
            if size > 80_000_000:
                raise ConversionError("The combined PDF sources exceed the 80 MB conversion limit.")
            pages = await asyncio.to_thread(
                extract_pdf,
                data,
                language=settings.ocr_language,
                max_pages=settings.ocr_max_pages,
                ocr_enabled=settings.ocr_enabled,
                timeout=settings.ocr_timeout_seconds,
                cancelled=cancelled,
            )
            sources.append((name, pages))
            if sum(len(p) for _, p in sources) > 60:
                raise ConversionError("Use at most 60 pages total; no partial workbook was created.")
        content, audit = await asyncio.to_thread(workbook, sources)
        if cancelled.is_set():
            raise ConversionError("Conversion stopped. No completed workbook was created.")
        async with maker() as db:
            if await stop_requested(maker, turn.assistant_message_id):
                cancelled.set()
                raise ConversionError("Conversion stopped. No completed workbook was created.")
            doc = await store_upload(
                db,
                settings,
                files,
                None,
                user_id=turn.user_id,
                filename="Combined_PDF_to_Excel.xlsx",
                data=content,
                project_id=None,
            )
            await db.commit()
            attachment = {"type": "download_file", "id": str(doc.id), "filename": doc.title, "file_type": "xlsx"}
        pages = sum(item["pages"] for item in audit)
        flagged = sum(item["flagged_cells"] for item in audit)
        activity = [
            {
                "tool": "convert_pdfs_to_excel",
                "summary": f"Created workbook from {len(audit)} PDFs / {pages} pages",
                "error": False,
                "action": attachment,
            }
        ]
        text = f"Created **Combined_PDF_to_Excel.xlsx** from {len(audit)} PDF file(s), processing all {pages} pages in order. "
        text += "Each PDF has its own worksheet with editable cells. Use the download attachment below.\n\n"
        text += f"{flagged} cells were highlighted for review. OCR, handwriting and table alignment still need checking against the PDFs; "
        text += "this is not a claim of perfect manual verification."
        outcome = "complete"
    except (ConversionError, HTTPException, ImportError, ValueError, OSError) as exc:
        outcome = "stopped" if cancelled.is_set() else "error"
        detail = (
            str(exc)
            if isinstance(exc, ConversionError)
            else "The file could not be extracted, rendered or saved. Check the server conversion tools."
        )
        text = "No workbook was created. " + detail
        error = detail
        activity = [{"tool": "convert_pdfs_to_excel", "summary": detail, "error": True, "action": None}]
    except Exception:
        text = "No workbook was created. An internal extraction or storage error prevented completion."
        error = text
        outcome = "error"
        activity = [{"tool": "convert_pdfs_to_excel", "summary": text, "error": True, "action": None}]
    finally:
        monitor.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await monitor
    yield {"type": "tool", "stage": "done", "activity": activity}
    yield {"type": "delta", "text": text}
    result = await asyncio.shield(
        finalize(
            maker,
            turn.assistant_message_id,
            text=text,
            outcome=outcome,
            provider="tools",
            model="PDF to Excel",
            input_tokens=None,
            output_tokens=None,
            error=error,
            citations=[],
            tool_activity=activity,
        )
    )
    event = {
        "type": "done" if outcome == "complete" else outcome,
        "message": result.model_dump(mode="json") if result else None,
    }
    if error:
        event["detail"] = error
    yield event
