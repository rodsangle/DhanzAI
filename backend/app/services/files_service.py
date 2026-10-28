"""Uploaded files: validate, scan, extract, store and index them in the user's library."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.base import utcnow
from app.models import KnowledgeDocument
from app.services import knowledge_service
from app.services.scanner import ClamAVScanner, MalwareFound, ScanError
from app.services.storage import FileStorage
from dhanz_knowledge import Embedder
from dhanz_knowledge.documents import UnsupportedFile, extract_document, safe_filename

log = logging.getLogger(__name__)


@dataclass
class FilesRuntime:
    storage: FileStorage
    scanner: ClamAVScanner | None


def build_files_runtime(settings: Settings) -> FilesRuntime:
    scanner = ClamAVScanner(settings.clamav_host, settings.clamav_port) if settings.clamav_host else None
    return FilesRuntime(storage=FileStorage(settings.storage_dir), scanner=scanner)


async def store_upload(
    db: AsyncSession,
    settings: Settings,
    files: FilesRuntime,
    embedder: Embedder | None,
    *,
    user_id: uuid.UUID,
    filename: str,
    data: bytes,
    project_id: uuid.UUID | None,
) -> KnowledgeDocument:
    """Validate → malware scan → extract text → store bytes → index. Caller commits."""
    if len(data) == 0:
        raise HTTPException(422, "The file is empty.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Files larger than {settings.max_upload_mb} MB are not accepted.")
    name = safe_filename(filename)
    try:
        # Parsing can be CPU-heavy (large PDFs/spreadsheets): keep it off the event loop.
        extracted = await asyncio.to_thread(extract_document, name, data)
    except UnsupportedFile as exc:
        raise HTTPException(422, str(exc)) from None
    except Exception:  # noqa: BLE001 - malformed files must not crash the API
        log.exception("Extraction failed for %s", name)
        raise HTTPException(422, "The file could not be read. It may be damaged.") from None

    scan_status = "not_scanned"
    if files.scanner is not None:
        try:
            await files.scanner.scan(data)
            scan_status = "clean"
        except MalwareFound as exc:
            log.warning("Malware rejected for user %s: %s", user_id, exc.signature)
            raise HTTPException(422, f"The file was rejected by the malware scanner ({exc.signature}).") from None
        except ScanError:
            log.exception("Malware scan failed")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "The malware scanner is unavailable. Try again later."
            ) from None

    key = await files.storage.put(data)
    doc_id = uuid.uuid4()
    doc = KnowledgeDocument(
        id=doc_id,
        user_id=user_id,
        kind="file",
        url=f"upload:{doc_id}",
        title=name,
        content=extracted.text,
        content_hash=hashlib.sha256(data).hexdigest(),
        added_via="upload",
        retrieved_at=utcnow(),
        project_id=project_id,
        file_type=extracted.kind,
        mime_type=extracted.mime_type,
        size_bytes=len(data),
        storage_key=key,
        scan_status=scan_status,
        notes=" ".join(extracted.notes) or None,
    )
    db.add(doc)
    await db.flush()
    if extracted.text:
        await knowledge_service.store_chunks(db, doc, extracted.text, embedder)
    return doc


async def delete_document_files(files: FilesRuntime, docs: list[KnowledgeDocument]) -> None:
    for doc in docs:
        if doc.storage_key:
            try:
                await files.storage.delete(doc.storage_key)
            except OSError:
                log.warning("Could not delete stored file %s", doc.storage_key)
