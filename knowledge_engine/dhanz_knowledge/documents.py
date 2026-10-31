"""Uploaded-file validation and text extraction.

Supported: PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx), CSV, plain text / Markdown /
source code, and images (PNG, JPEG, WebP, GIF — passed to vision-capable models).
Legacy binary Office formats (.doc/.xls/.ppt) are rejected with a clear message.
"""

from __future__ import annotations

import csv
import io
import math
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePath

from .ocr import OCRError

MAX_UNCOMPRESSED_BYTES = 100_000_000  # zip-bomb guard for Office files
MAX_ZIP_ENTRIES = 5_000
MAX_TEXT_CHARS = 2_000_000
MAX_TABLE_ROWS = 200  # rows per sheet rendered as text for the model

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".json", ".yaml", ".yml", ".toml", ".ini", ".xml", ".html", ".htm",
    ".py", ".dart", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".swift", ".c", ".h", ".cpp", ".hpp", ".cs",
    ".go", ".rs", ".rb", ".php", ".sql", ".sh", ".ps1", ".css", ".scss", ".vue", ".r", ".m", ".scala", ".lua",
}  # fmt: skip
IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
OFFICE = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
LEGACY = {".doc", ".xls", ".ppt"}


class UnsupportedFile(Exception):
    """The file is not accepted. The message is safe to show to users."""


@dataclass
class ExtractedDocument:
    kind: str  # pdf | docx | xlsx | pptx | csv | text | code | image
    mime_type: str
    text: str
    notes: list[str] = field(default_factory=list)  # e.g. "scanned PDF: no text layer"

    @property
    def is_image(self) -> bool:
        return self.kind == "image"


def safe_filename(name: str) -> str:
    base = PurePath(name.replace("\\", "/")).name.strip() or "file"
    cleaned = "".join(c if c.isalnum() or c in " ._-()" else "_" for c in base)
    return cleaned[:150]


def _sniff_image(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def _check_zip(data: bytes) -> zipfile.ZipFile:
    if not data.startswith(b"PK\x03\x04"):
        raise UnsupportedFile("The file does not look like a valid Office document.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise UnsupportedFile("The Office document is damaged.") from None
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
        raise UnsupportedFile("The document expands to an unreasonable size and was rejected.")
    if any(i.flag_bits & 0x1 for i in infos):
        raise UnsupportedFile("Password-protected documents are not supported.")
    return zf


def extract_document(filename: str, data: bytes, *, pdf_ocr: Callable[[int], str] | None = None) -> ExtractedDocument:
    """Validate the file's real type (not just its name) and extract readable text."""
    ext = PurePath(filename.lower()).suffix
    if ext in LEGACY:
        raise UnsupportedFile(f"Legacy {ext} files are not supported. Save it as {ext}x and upload again.")
    if ext in IMAGE_TYPES:
        mime = _sniff_image(data)
        if mime is None:
            raise UnsupportedFile("The image file is damaged or not really an image.")
        return ExtractedDocument("image", mime, "")
    if ext == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise UnsupportedFile("The file does not look like a valid PDF.")
        return _pdf(data, pdf_ocr)
    if ext in OFFICE:
        zf = _check_zip(data)
        zf.close()
        return {".docx": _docx, ".xlsx": _xlsx, ".pptx": _pptx}[ext](data)
    if ext in (".csv", ".tsv"):
        return _csv(_decode(data), "\t" if ext == ".tsv" else None)
    if ext in TEXT_EXTENSIONS:
        text = _decode(data)
        kind = "text" if ext in (".txt", ".md", ".markdown", ".rst", ".log") else "code"
        return ExtractedDocument(kind, "text/plain", text[:MAX_TEXT_CHARS])
    raise UnsupportedFile(f"Files of type '{ext or 'unknown'}' are not supported.")


def _decode(data: bytes) -> str:
    if b"\x00" in data[:4096]:
        raise UnsupportedFile("The file looks binary, not text.")
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _pdf(data: bytes, pdf_ocr: Callable[[int], str] | None = None) -> ExtractedDocument:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    notes = []
    ocr_stopped = False
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise UnsupportedFile("Password-protected PDFs are not supported.")
        pages = []
        for i, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                if pdf_ocr is not None and not ocr_stopped:
                    try:
                        text = pdf_ocr(i).strip()
                        if text:
                            notes.append(f"Page {i}: OCR text may contain recognition errors.")
                        else:
                            notes.append(f"Page {i}: OCR found no readable text.")
                    except OCRError as exc:
                        notes.append(str(exc))
                        ocr_stopped = True
                elif not ocr_stopped:
                    notes.append(f"Page {i}: no text layer; OCR is disabled.")
            if text:
                pages.append(f"## Page {i}\n{text}")
            if sum(len(p) for p in pages) > MAX_TEXT_CHARS:
                break
    except PdfReadError:
        raise UnsupportedFile("The PDF is damaged and could not be read.") from None
    if not pages:
        notes.append("This PDF has no readable text. Its contents could not be read; see the OCR notes.")
    return ExtractedDocument("pdf", "application/pdf", "\n\n".join(pages)[:MAX_TEXT_CHARS], notes)


def _docx(data: bytes) -> ExtractedDocument:
    import docx

    document = docx.Document(io.BytesIO(data))
    lines: list[str] = []
    for para in document.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name or "").lower() if para.style is not None else ""
        if style.startswith("heading"):
            level = "".join(c for c in style if c.isdigit()) or "2"
            lines.append("#" * min(int(level) + 1, 6) + " " + text)
        elif "list" in style:
            lines.append("- " + text)
        else:
            lines.append(text)
    for n, table in enumerate(document.tables, start=1):
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        if rows:
            lines.append(f"\n### Table {n}\n" + _markdown_table(rows))
    return ExtractedDocument("docx", OFFICE[".docx"], "\n".join(lines)[:MAX_TEXT_CHARS])


def _pptx(data: bytes) -> ExtractedDocument:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    lines: list[str] = []
    for i, slide in enumerate(prs.slides, start=1):
        lines.append(f"## Slide {i}")
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text = "".join(run.text for run in para.runs).strip()
                    if text:
                        lines.append(text)
            if getattr(shape, "has_table", False) and shape.has_table:
                rows = [[cell.text.strip() for cell in row.cells] for row in shape.table.rows]
                lines.append(_markdown_table(rows))
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                lines.append(f"Speaker notes: {notes}")
    return ExtractedDocument("pptx", OFFICE[".pptx"], "\n".join(lines)[:MAX_TEXT_CHARS])


def _xlsx(data: bytes) -> ExtractedDocument:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            if any(v is not None and str(v).strip() for v in row):
                rows.append(["" if v is None else v for v in row])
        if rows:
            parts.append(f"## Sheet: {ws.title}\n" + describe_table(rows))
    wb.close()
    return ExtractedDocument("xlsx", OFFICE[".xlsx"], "\n\n".join(parts)[:MAX_TEXT_CHARS])


def _csv(text: str, delimiter: str | None) -> ExtractedDocument:
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if any(c.strip() for c in r)]
    return ExtractedDocument("csv", "text/csv", describe_table(rows)[:MAX_TEXT_CHARS])


def _num(v) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v) if math.isfinite(v) else None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def describe_table(rows: list[list]) -> str:
    """Render a table for the model: shape, per-column statistics computed exactly, and the first rows.

    Statistics are computed here (not by the model) so totals and averages are reliable.
    """
    header = [str(c).strip() or f"Column {i + 1}" for i, c in enumerate(rows[0])]
    body = rows[1:]
    width = len(header)
    lines = [f"{len(body)} data rows × {width} columns."]
    stats = []
    for i, name in enumerate(header):
        values = [r[i] for r in body if i < len(r) and str(r[i]).strip() != ""]
        nums = [n for n in (_num(v) for v in values) if n is not None]
        if values and len(nums) >= 0.8 * len(values):
            total = sum(nums)
            stats.append(
                f"- {name}: numeric, {len(nums)} values, sum={total:,.4g}, mean={total / len(nums):,.4g}, "
                f"min={min(nums):,.4g}, max={max(nums):,.4g}"
            )
        elif values:
            distinct = len({str(v) for v in values})
            stats.append(f"- {name}: text, {len(values)} values, {distinct} distinct")
    if stats:
        lines.append("Column statistics (computed exactly by DHANZ AI):\n" + "\n".join(stats))
    shown = body[:MAX_TABLE_ROWS]
    lines.append(_markdown_table([header, *shown]))
    if len(body) > len(shown):
        lines.append(f"(First {len(shown)} of {len(body)} rows shown.)")
    return "\n".join(lines)


def _markdown_table(rows: list[list]) -> str:
    width = max(len(r) for r in rows)

    def cell(v) -> str:
        return str(v).replace("|", "\\|").replace("\n", " ").strip()

    norm = [[cell(r[i]) if i < len(r) else "" for i in range(width)] for r in rows]
    out = ["| " + " | ".join(norm[0]) + " |", "|" + "---|" * width]
    out += ["| " + " | ".join(r) + " |" for r in norm[1:]]
    return "\n".join(out)
