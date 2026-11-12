"""Bounded PDF extraction to real editable XLSX cells, without model transcription."""

import csv
import io
import math
import re
import shutil
import statistics
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Cell:
    x: float
    text: str
    confidence: float | None = None
    source_row: int | None = None
    review_note: str = ""


@dataclass
class Page:
    number: int
    rows: list[list[Cell]]
    ocr: bool = False
    columns: list[str] | None = None
    vision: dict | None = None
    vision_input: bytes | None = field(default=None, repr=False)


_PDF_LAYOUT_VERSION = 2


class ConversionError(ValueError):
    pass


def sheet_name(filename, used):
    stem = re.sub(r"[\\/*?:\[\]\x00-\x1f]", "_", Path(filename).stem).strip(" '") or "PDF"
    name = stem[:31]
    suffix = 1
    while name.casefold() in used:
        suffix += 1
        tail = f" ({suffix})"
        name = stem[: 31 - len(tail)] + tail
    used.add(name.casefold())
    return name


def native_rows(text):
    return [
        [Cell(float(m.start()), m.group().strip()) for m in re.finditer(r"\S(?:.*?\S)?(?= {2,}|$)", line)]
        for line in text.splitlines()
        if line.strip()
    ]


def ocr_rows(tsv):
    words = []
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t"):
        text = (row.get("text") or "").strip()
        if not text or row.get("level") != "5":
            continue
        try:
            words.append(
                (
                    float(row["top"]) + float(row["height"]) / 2,
                    float(row["left"]),
                    float(row["width"]),
                    text,
                    float(row["conf"]),
                    float(row["height"]),
                )
            )
        except (KeyError, ValueError):
            continue
    if not words:
        return []
    tolerance = max(3, statistics.median(w[5] for w in words) * 0.45)
    lines = []
    for word in sorted(words):
        if not lines or abs(word[0] - lines[-1][0][0]) > tolerance:
            lines.append([word])
        else:
            lines[-1].append(word)
    result = []
    for line in lines:
        cells = []
        right = -1
        char_width = statistics.median(w[2] / max(1, len(w[3])) for w in line)
        for _, x, width, text, conf, _ in sorted(line, key=lambda w: w[1]):
            if cells and x - right < max(18, char_width * 2.5):
                cells[-1].text += " " + text
                cells[-1].confidence = min(cells[-1].confidence, conf)
            else:
                cells.append(Cell(x, text, conf))
            right = x + width
        result.append(cells)
    return result


def _call(args, timeout=60):
    try:
        result = subprocess.run(args, check=True, capture_output=True, timeout=timeout)  # noqa: S603 - fixed PDF utility argv, no shell
    except (subprocess.SubprocessError, OSError):
        raise ConversionError("A PDF/OCR utility failed or timed out. No completed workbook was created.") from None
    if len(result.stdout) > 5_000_000:
        raise ConversionError("Extracted page text exceeds the safe conversion limit.")
    return result.stdout.decode("utf-8", errors="replace")


def extract_pdf(data, *, language="eng", max_pages=20, ocr_enabled=True, timeout=60, cancelled=None):
    if not all(shutil.which(name) for name in ("pdfinfo", "pdftotext")):
        raise ConversionError("PDF text utilities are missing on the server.")
    with tempfile.TemporaryDirectory(prefix="dhanz-pdf-xlsx-") as temp:
        root = Path(temp)
        source = root / "input.pdf"
        source.write_bytes(data)
        info = _call(["pdfinfo", str(source)], timeout)
        match = re.search(r"^Pages:\s*(\d+)", info, re.M)
        if not match or not 1 <= int(match[1]) <= max_pages:
            raise ConversionError(
                f"The PDF page count is unavailable or exceeds the {max_pages}-page conversion limit. Nothing was truncated."  # noqa: E501 - complete extraction diagnostic/prompt
            )
        pages = []
        for number in range(1, int(match[1]) + 1):
            if cancelled and cancelled.is_set():
                raise ConversionError("Conversion stopped. No completed workbook was created.")
            text = _call(
                ["pdftotext", "-f", str(number), "-l", str(number), "-layout", "-enc", "UTF-8", str(source), "-"],
                timeout,
            )
            rows = native_rows(text)
            use_ocr = len(text.strip()) < 200 or len(text.split()) < 30
            if use_ocr:
                if not ocr_enabled or not all(shutil.which(name) for name in ("pdftoppm", "tesseract")):
                    raise ConversionError(
                        f"Page {number} needs OCR, but OCR is disabled or unavailable. No partial workbook was returned."  # noqa: E501 - complete extraction diagnostic/prompt
                    )
                prefix = root / "page"
                _call(
                    [
                        "pdftoppm",
                        "-f",
                        str(number),
                        "-l",
                        str(number),
                        "-r",
                        "180",
                        "-scale-to",
                        "2500",
                        "-singlefile",
                        "-png",
                        str(source),
                        str(prefix),
                    ],
                    timeout,
                )
                tsv = _call(["tesseract", str(prefix) + ".png", "stdout", "-l", language, "tsv"], timeout)
                rows = ocr_rows(tsv)
                from PIL import Image, ImageOps

                from .pdf_table_layout import LABELS, columns, extract_rows, geometry, metadata

                image_path = root / "page.png"
                shape = geometry(image_path, tsv)
                if shape is None:
                    import csv

                    from .pdf_table_layout import words

                    tokens = words(tsv)
                    body = sorted(w["y"] for w in tokens if w["text"].lower() == "pipefitter")
                    if len(body) >= 5:
                        pitch = statistics.median(b - a for a, b in zip(body, body[1:], strict=False) if b - a > 10)
                        top = max(0, round(body[0] - pitch * 1.5))
                        bottom = round(body[0] - pitch * 0.2)
                        header_path = root / "probe.png"
                        with Image.open(image_path) as image:
                            crop = image.convert("L").crop((0, top, image.width, bottom))
                            ImageOps.autocontrast(ImageOps.invert(crop)).save(header_path)
                        extra = _call(
                            ["tesseract", str(header_path), "stdout", "-l", language, "--psm", "6", "tsv"], timeout
                        )
                        output = io.StringIO()
                        fields = next(csv.reader(io.StringIO(tsv), delimiter="\t"))
                        writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t")
                        for item in csv.DictReader(io.StringIO(extra), delimiter="\t"):
                            item["top"] = str(int(item["top"]) + top)
                            writer.writerow(item)
                        shape = geometry(image_path, tsv + "\n" + output.getvalue())
                        header_path.unlink(missing_ok=True)
                if shape:
                    header_path = root / "header.png"
                    with Image.open(image_path) as image:
                        crop = image.convert("L").crop(
                            (shape["left"], shape["header_top"], shape["right"], shape["header_bottom"])
                        )
                        ImageOps.autocontrast(ImageOps.invert(crop)).save(header_path)
                    header_tsv = _call(
                        ["tesseract", str(header_path), "stdout", "-l", language, "--psm", "6", "tsv"], timeout
                    )
                    x_edges = columns(header_tsv, shape)
                    if x_edges:
                        records = extract_rows(image_path, tsv, shape, x_edges)
                        metadata_rows = [[Cell(0, line)] for line in metadata(tsv, shape["header_top"])]
                        rows = metadata_rows + [[Cell(i, label) for i, label in enumerate(LABELS)]]
                        rows += [
                            [
                                Cell(c["column"], c["text"], c["confidence"], c["source_row"], c["review_note"])
                                for c in record
                            ]
                            for record in records
                        ]
                        if shape.get("roster_columns"):
                            rows += [[Cell(0, line)] for line in metadata(tsv, shape["rows"][-1] + 10, after=True)]
                        from .pdf_handwriting import vision_image

                        page = Page(
                            number,
                            rows,
                            True,
                            LABELS.copy(),
                            vision={"status": "not_requested"},
                            vision_input=vision_image(image_path, shape, x_edges, len(records)),
                        )
                        pages.append(page)
                        image_path.unlink(missing_ok=True)
                        header_path.unlink(missing_ok=True)
                        continue
                image_path.unlink(missing_ok=True)
            pages.append(Page(number, rows, use_ocr))
        return pages


def _key(row):
    return " ".join(c.text for c in row).strip().casefold()


def _header(text):
    labels = (
        "name",
        "id",
        "code",
        "qty",
        "level",
        "signature",
        "date",
        "hours",
        "quantity",
        "unit",
        "description",
        "total",
        "amount",
        "item",
    )
    return sum(bool(re.search(r"\b" + word + r"\b", text)) for word in labels) >= 2


def _anchors(rows, ocr):
    starts = sorted(c.x for row in rows if len(row) > 1 for c in row)
    if not starts:
        return [0.0]
    clusters = []
    tolerance = 15 if ocr else 2
    for x in starts:
        if clusters and abs(x - statistics.mean(clusters[-1])) <= tolerance:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    threshold = max(2, sum(len(row) > 1 for row in rows) // 8)
    selected = [statistics.mean(group) for group in clusters if len(group) >= threshold]
    return selected[:50] or [c.x for c in next(row for row in rows if len(row) > 1)][:50]


def workbook(sources):
    """sources = [(original filename, ordered extracted pages)]. No source data is fabricated."""
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    if not sources or len(sources) > 10 or sum(len(pages) for _, pages in sources) > 60:
        raise ConversionError("Use 1–10 PDFs and at most 60 pages total. No partial workbook was returned.")
    book = Workbook()
    book.remove(book.active)
    used = set()
    audit = []
    border = Border(*(Side(style="thin", color="D1D5DB") for _ in range(4)))
    for filename, pages in sources:
        sheet = book.create_sheet(sheet_name(filename, used))
        candidates = Counter()
        for page in pages:
            keys = set()
            for i, row in enumerate(page.rows):
                key = _key(row)
                is_title = i < 4 and bool(re.search(r"\b(training|protocol|attendance|instructor|company|log)\b", key))
                if _header(key) or is_title or re.fullmatch(r"page\s+\d+(?:\s+(?:of|/)\s*\d+)?", key):
                    keys.add(key)
            candidates.update(keys)
        repeated = {key for key, count in candidates.items() if count >= max(2, math.ceil(len(pages) / 2))}
        seen = set()
        row_number = 0
        uncertain = 0
        # OCR coordinates and native layout columns have different units; keep
        # a separate anchor set so mixed PDFs do not combine incompatible units.
        anchors = {
            mode: _anchors([row for page in pages if page.ocr == mode and not page.columns for row in page.rows], mode)
            for mode in (False, True)
        }
        columns = max([len(a) for a in anchors.values()] + [len(p.columns) for p in pages if p.columns])
        for page in pages:
            rows = page.rows or [[Cell(0, "[No readable text extracted on this page]", 0)]]
            for row in rows:
                key = _key(row)
                if key in repeated and key in seen:
                    continue
                seen.add(key)
                row_number += 1
                if row_number > 10000:
                    raise ConversionError("A worksheet exceeds 10,000 extracted rows. Nothing was truncated.")
                values = {}
                for item in row:
                    col = (
                        int(item.x) + 1
                        if page.columns
                        else min(range(len(anchors[page.ocr])), key=lambda i: abs(anchors[page.ocr][i] - item.x)) + 1
                    )
                    if col in values:
                        prior = values[col]
                        prior.text += " " + item.text
                        if prior.confidence is not None and item.confidence is not None:
                            prior.confidence = min(prior.confidence, item.confidence)
                    else:
                        values[col] = Cell(item.x, item.text, item.confidence, item.source_row, item.review_note)
                for col in range(1, columns + 1):
                    item = values.get(col)
                    value = item.text if item else None
                    if value and len(value) > 32767:
                        raise ConversionError("A cell exceeds Excel text limits; no data was silently cut.")
                    cell = sheet.cell(row_number, col, value)
                    if isinstance(value, str):
                        cell.data_type = "s"  # preserve IDs/zeros and prevent formula injection
                    cell.border = border
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
                    note = f"Source: {filename}; page {page.number}. "
                    if item and item.source_row is not None:
                        note += f"Printed table row {item.source_row}. "
                    if item and item.review_note:
                        note += item.review_note + " "
                    flagged = item is not None and item.confidence is not None and item.confidence < 85
                    flagged = flagged or bool(item and item.review_note)
                    if page.ocr:
                        note += "OCR extraction; not manually verified. "
                        note += (
                            f"Confidence: {item.confidence:.0f}/100. "
                            if item and item.confidence is not None
                            else (
                                "Confidence unavailable. "
                                if item and item.text
                                else "No OCR text in this cell; verify whether blank or unreadable. "
                            )
                        )
                        flagged = flagged or (not item and len(row) > 1)
                    if flagged:
                        cell.fill = PatternFill("solid", fgColor="FFF2CC")
                        uncertain += 1
                        note += "Verify against the PDF; no replacement value was guessed."
                    cell.comment = Comment(note, "Dhanz")
                    if _header(key) or row_number == 1:
                        cell.font = Font(bold=True, color="111827")
                        if not flagged:
                            cell.fill = PatternFill("solid", fgColor="DBEAFE")
        for col in range(1, columns + 1):
            lengths = [len(str(c.value or "")) for c in sheet[get_column_letter(col)]]
            width = min(60, max(14, sorted(lengths)[int((len(lengths) - 1) * 0.9)] + 2))
            sheet.column_dimensions[get_column_letter(col)].width = width
        for row in sheet:
            lines = max(
                math.ceil(len(str(c.value or "")) / max(8, sheet.column_dimensions[c.column_letter].width - 2))
                for c in row
            )
            sheet.row_dimensions[row[0].row].height = min(150, max(18, lines * 15))
        sheet.freeze_panes = "A2"
        sheet["A1"].comment = Comment(
            f"All {len(pages)} pages processed in order. {sum(p.ocr for p in pages)} pages used OCR. "
            f"{uncertain} cells flagged. Layout and handwriting need human review; this is not a claim of perfect verification. "  # noqa: E501 - complete extraction diagnostic/prompt
            "Only confidently identified repeated headings were removed. " + sheet["A1"].comment.text,
            "Dhanz",
        )
        audit.append(
            {
                "filename": filename,
                "sheet": sheet.title,
                "pages": len(pages),
                "ocr_pages": sum(p.ocr for p in pages),
                "rows": row_number,
                "flagged_cells": uncertain,
                "aligned_pages": sum(bool(p.columns) for p in pages),
                "vision_pages": sum((p.vision or {}).get("status") == "complete" for p in pages),
                "vision_warnings": [
                    f"Page {p.number}: {(p.vision or {}).get('status')}"
                    for p in pages
                    if p.columns and (p.vision or {}).get("status") not in ("complete", "not_requested")
                ],
                "input_tokens": sum((p.vision or {}).get("input_tokens", 0) for p in pages),
                "output_tokens": sum((p.vision or {}).get("output_tokens", 0) for p in pages),
            }
        )
    output = io.BytesIO()
    book.save(output)
    return output.getvalue(), audit
