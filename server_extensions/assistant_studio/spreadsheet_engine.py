"""Bounded, deterministic XLSX editing. Never executes workbook formulas."""

import io
import re
import zipfile
from copy import copy

from openpyxl import Workbook, load_workbook
from openpyxl.formula import Tokenizer
from openpyxl.formula.translate import Translator
from openpyxl.styles import Border, PatternFill, Side
from openpyxl.utils import FORMULAE
from openpyxl.utils.cell import range_boundaries
from openpyxl.workbook.properties import CalcProperties

MAX_CELLS = 200000
MAX_ROWS = 100000
FUNCTIONS = set(
    "SUM AVERAGE MIN MAX COUNT COUNTA COUNTBLANK SUMIF SUMIFS COUNTIF COUNTIFS AVERAGEIF AVERAGEIFS IF IFS IFERROR IFNA AND OR NOT ROUND ROUNDUP ROUNDDOWN ABS MOD INT CEILING FLOOR SUMPRODUCT SUBTOTAL AGGREGATE VLOOKUP HLOOKUP XLOOKUP INDEX MATCH XMATCH LEFT RIGHT MID LEN TRIM CLEAN CONCAT CONCATENATE TEXTJOIN TEXT VALUE DATE YEAR MONTH DAY TODAY NOW DATEDIF DAYS EDATE EOMONTH WEEKDAY NETWORKDAYS WORKDAY ISBLANK ISNUMBER ISTEXT TRUE FALSE UPPER LOWER PROPER SUBSTITUTE REPLACE FIND SEARCH FILTER SORT UNIQUE SEQUENCE LET LAMBDA MAP REDUCE SCAN BYROW BYCOL MAKEARRAY TAKE DROP CHOOSECOLS CHOOSEROWS HSTACK VSTACK TOCOL TOROW WRAPCOLS WRAPROWS EXPAND".split()  # noqa: E501 - descriptive tool text
)


# Reuse Excel's standard function catalog; generation support is not a requirement
# for preserving an uploaded formula. Never evaluate any workbook formula here.
BLOCKED_FUNCTIONS = {
    "WEBSERVICE",
    "HYPERLINK",
    "IMAGE",
    "RTD",
    "INDIRECT",
    "CALL",
    "EXEC",
    "REGISTER",
    "REGISTER.ID",
    "EVALUATE",
    "SQL.REQUEST",
    "STOCKHISTORY",
}


def formula(value, *, existing=False):
    if not isinstance(value, str) or not value.startswith("=") or len(value) > 8192:
        raise ValueError("Use an Excel formula beginning with =, at most 8192 characters.")
    try:
        tokens = Tokenizer(value).items
    except Exception:
        raise ValueError("Invalid Excel formula.") from None
    for token in tokens:
        if token.type == "FUNC" and token.subtype == "OPEN":
            name = token.value[:-1].upper().removeprefix("_XLFN.").removeprefix("_XLWS.")
            if name in BLOCKED_FUNCTIONS or name.startswith("CUBE"):
                raise ValueError("Unsupported formula function: " + name)
            supported = (FUNCTIONS | FORMULAE) if existing else (FUNCTIONS | {"LOOKUP"})
            if name not in supported:
                raise ValueError("Unsupported formula function: " + name)
        if token.type == "OPERAND" and token.subtype == "RANGE":
            operand = token.value
            if any(x in operand for x in ("|", "\\", "://")) or ("!" in operand and "[" in operand.split("!")[0]):
                raise ValueError("External workbook, network and DDE references are unsupported.")
    return value


def rectangle(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z]{1,3}[1-9][0-9]{0,5}(?::[A-Za-z]{1,3}[1-9][0-9]{0,5})?", value
    ):
        raise ValueError("Use a bounded A1 range, for example A1:F30.")
    a, b, c, d = range_boundaries(value)
    if a > c or b > d or c > 256 or d > MAX_ROWS or (c - a + 1) * (d - b + 1) > 5000:
        raise ValueError("Range exceeds 5000 cells, 256 columns or 100000 rows.")
    return a, b, c, d


def validate_archive(data, *, max_cells=MAX_CELLS, expanded_bytes=80000000,
                     part_bytes=40000000, max_columns=256):
    """Bound ZIP expansion and scan worksheet coordinates before loading cells.

    XML is checked in chunks, then parsed incrementally. This also supports the
    read-only source reader without loading an entire source workbook into RAM.
    """
    import xml.etree.ElementTree as ET
    if not isinstance(data, bytes) or len(data) > 50000000:
        raise ValueError("Workbook exceeds 50 MB.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 2000 or sum(p.file_size for p in entries) > expanded_bytes:
                raise ValueError("Workbook expanded size exceeds the processing limit.")
            if len({p.filename for p in entries}) != len(entries):
                raise ValueError("Duplicate workbook archive entries are unsupported.")
            total_cells = 0
            for item in entries:
                name = item.filename.lower()
                if item.flag_bits & 1 or item.file_size > part_bytes or name.startswith("/") or ".." in name.split("/"):
                    raise ValueError("Unsupported workbook archive.")
                if any(part in name for part in (
                    "vbaproject", "externallinks/", "embeddings/", "macrosheets/",
                    "connections.xml", "querytables/",
                )):
                    raise ValueError("Macros, embedded objects and external data connections are unsupported.")
                if not name.endswith(".xml"):
                    continue
                tail = b""
                with archive.open(item) as stream:
                    while chunk := stream.read(65536):
                        probe = (tail + chunk).upper()
                        if b"\x00" in probe or b"<!DOCTYPE" in probe or b"<!ENTITY" in probe:
                            raise ValueError("Unsupported workbook XML.")
                        tail = probe[-16:]
                if name.startswith("xl/worksheets/"):
                    with archive.open(item) as stream:
                        for _, element in ET.iterparse(stream, events=("end",)):
                            tag = element.tag.rsplit("}", 1)[-1]
                            if tag == "c":
                                address = element.attrib.get("r", "")
                                if not re.fullmatch(r"[A-Za-z]{1,3}[1-9][0-9]{0,5}", address):
                                    raise ValueError("Unsupported workbook cell coordinate.")
                                a, b, _, _ = range_boundaries(address)
                                if a > max_columns or b > MAX_ROWS:
                                    raise ValueError(f"Workbook exceeds {max_columns} columns or {MAX_ROWS} rows.")
                                total_cells += 1
                                if total_cells > max_cells:
                                    raise ValueError(f"Workbook exceeds {max_cells} populated cells.")
                            elif tag == "row" and not 1 <= int(element.attrib.get("r", "0")) <= MAX_ROWS:
                                raise ValueError(f"Workbook exceeds {MAX_ROWS} rows.")
                            element.clear()
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise ValueError("Upload a valid .xlsx workbook.") from None


def load(data=None):
    if data is None:
        return Workbook()
    validate_archive(data)
    try:
        book = load_workbook(io.BytesIO(data), keep_links=False)
    except (zipfile.BadZipFile, KeyError):
        raise ValueError("Upload a valid .xlsx workbook.") from None
    if len(book.worksheets) > 30 or sum(len(s._cells) for s in book) > MAX_CELLS:
        raise ValueError("Workbook exceeds 30 worksheets or 200000 populated cells.")
    for sheet in book:
        for cell in sheet._cells.values():
            if cell.data_type == "f":
                value = cell.value
                # openpyxl represents array formulas as objects rather than strings.
                if not isinstance(value, str):
                    value = getattr(value, "text", None)
                try:
                    formula(value, existing=True)
                except ValueError as exc:
                    raise ValueError(
                        f"Existing formula in {sheet.title}!{cell.coordinate} cannot be safely preserved: {exc} "
                        "This error concerns the uploaded workbook, not the requested formatting or new formula."
                    ) from None
    return book


def inspect(data, sheet=None, cell_range=None):
    book = load(data)
    if sheet is not None or cell_range is not None:
        if sheet not in book.sheetnames or cell_range is None:
            raise ValueError("For a targeted inspection, provide an existing sheet name and bounded range.")
        a, b, c, d = rectangle(cell_range)
        if (c - a + 1) * (d - b + 1) > 500:
            raise ValueError("Inspect at most 500 cells per targeted request.")
        selected = book[sheet]
        cells = []
        for row in selected.iter_rows(min_row=b, max_row=d, min_col=a, max_col=c):
            for cell in row:
                value = cell.value
                if cell.data_type == "f" and not isinstance(value, str):
                    value = getattr(value, "text", None)
                cells.append(
                    {
                        "cell": cell.coordinate,
                        "value": str(value)[:2000] if value is not None else None,
                        "occupied": value is not None,
                        "data_type": cell.data_type,
                    }
                )
        return {
            "sheet": sheet,
            "range": cell_range,
            "cells": cells,
            "occupied_cells": [cell["cell"] for cell in cells if cell["occupied"]],
            "all_empty": not any(cell["occupied"] for cell in cells),
        }
    return {
        "preview_only": True,
        "note": "Preview size is not the copy limit. Use copy_workbook_column for complete columns without sending all rows to chat.",
        "sheets": [
            {
                "name": s.title,
                "rows": s.max_row,
                "columns": s.max_column,
                "preview": [
                    [str(c.value)[:300] if c.value is not None else None for c in row]
                    for row in s.iter_rows(max_row=min(s.max_row, 12), max_col=min(s.max_column, 12))
                ],
            }
            for s in book
        ]
    }


def edit(data, actions):
    if not isinstance(actions, list) or not 1 <= len(actions) <= 40:
        raise ValueError("Provide 1–40 explicit workbook actions.")
    book = load(data)
    touched = 0
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("Each action must be an object.")
        kind = action.get("type")
        name = action.get("sheet")
        if kind == "add_sheet":
            if (
                not isinstance(name, str)
                or not name
                or len(name) > 31
                or re.search(r"[\\/*?:\[\]]", name)
                or name in book.sheetnames
                or len(book.sheetnames) >= 30
            ):
                raise ValueError("Use a unique valid worksheet name of at most 31 characters.")
            book.create_sheet(name)
            continue
        if name not in book.sheetnames:
            raise ValueError("Choose an existing worksheet: " + ", ".join(book.sheetnames))
        sheet = book[name]
        bounds = rectangle(action.get("range", "A1"))
        a, b, c, d = bounds
        touched += (c - a + 1) * (d - b + 1)
        if touched > MAX_CELLS:
            raise ValueError("Edit exceeds 200000 addressed cells.")
        if kind == "set_cells":
            values = action.get("values")
            if (
                not isinstance(values, list)
                or len(values) != d - b + 1
                or any(not isinstance(row, list) or len(row) != c - a + 1 for row in values)
            ):
                raise ValueError("Values must match the specified range dimensions exactly.")
            for y, row in enumerate(values, b):
                for x, value in enumerate(row, a):
                    if value is not None and not isinstance(value, (str, int, float, bool)):
                        raise ValueError("Cells accept text, numbers, booleans or null.")
                    if isinstance(value, str) and len(value) > 32767:
                        raise ValueError("Cell text is too long.")
                    cell = sheet.cell(y, x, value)
                    if value is None:
                        cell.value = None
                    if isinstance(value, str):
                        cell.data_type = "s"  # leading zeros and literal = text stay text
        elif kind == "set_formula":
            value = formula(action.get("formula"))
            origin = sheet.cell(b, a).coordinate
            for row in sheet.iter_rows(min_row=b, max_row=d, min_col=a, max_col=c):
                for cell in row:
                    cell.value = formula(Translator(value, origin=origin).translate_formula(cell.coordinate))
        elif kind == "format_range":
            options = action.get("format", {})
            allowed = {
                "bold",
                "italic",
                "underline",
                "font_size",
                "font_color",
                "fill_color",
                "number_format",
                "wrap_text",
                "horizontal",
                "border",
                "column_width",
                "row_height",
            }
            if not isinstance(options, dict) or set(options) - allowed:
                raise ValueError("Unsupported formatting option.")
            for key in ("font_color", "fill_color"):
                if key in options and not re.fullmatch(r"[0-9a-fA-F]{6}", str(options[key])):
                    raise ValueError("Colors require six hexadecimal digits.")
            if "horizontal" in options and options["horizontal"] not in ("left", "center", "right", "general"):
                raise ValueError("Invalid horizontal alignment.")
            for key in ("bold", "italic", "underline", "wrap_text", "border"):
                if key in options and not isinstance(options[key], bool):
                    raise ValueError(key + " must be true or false.")
            if "number_format" in options and (
                not isinstance(options["number_format"], str) or len(options["number_format"]) > 100
            ):
                raise ValueError("Invalid number format.")
            if "font_size" in options and (
                not isinstance(options["font_size"], (int, float)) or not 1 <= options["font_size"] <= 72
            ):
                raise ValueError("Font size must be 1–72 points.")
            for key in ("column_width", "row_height"):
                if key in options and (not isinstance(options[key], (int, float)) or not 1 <= options[key] <= 200):
                    raise ValueError("Dimensions must be 1–200.")
            for row in sheet.iter_rows(min_row=b, max_row=d, min_col=a, max_col=c):
                for cell in row:
                    font = copy(cell.font)
                    for key in ("bold", "italic"):
                        if key in options:
                            setattr(font, key, options[key])
                    if "font_color" in options:
                        font.color = options["font_color"]
                    if "underline" in options:
                        font.underline = "single" if options["underline"] else None
                    if "font_size" in options:
                        font.sz = options["font_size"]
                    cell.font = font
                    if "fill_color" in options:
                        cell.fill = PatternFill("solid", fgColor=options["fill_color"])
                    if "number_format" in options:
                        cell.number_format = options["number_format"]
                    align = copy(cell.alignment)
                    if "wrap_text" in options:
                        align.wrap_text = options["wrap_text"]
                    if "horizontal" in options:
                        align.horizontal = options["horizontal"]
                    cell.alignment = align
                    if "border" in options:
                        side = Side(style="thin") if options["border"] else Side()
                        cell.border = Border(left=side, right=side, top=side, bottom=side)
            if "column_width" in options:
                from openpyxl.utils import get_column_letter

                for x in range(a, c + 1):
                    sheet.column_dimensions[get_column_letter(x)].width = options["column_width"]
            if "row_height" in options:
                for y in range(b, d + 1):
                    sheet.row_dimensions[y].height = options["row_height"]
        elif kind == "freeze_panes":
            sheet.freeze_panes = sheet.cell(b, a)
        elif kind == "auto_filter":
            sheet.auto_filter.ref = action["range"]
        else:
            raise ValueError("Unknown workbook action: " + str(kind))
    if sum(len(s._cells) for s in book) > MAX_CELLS:
        raise ValueError("Result exceeds 200000 populated cells.")
    book.calculation = CalcProperties(calcMode="auto", fullCalcOnLoad=True, forceFullCalc=True)
    output = io.BytesIO()
    book.save(output)
    if data is not None:
        from .spreadsheet_package import preserve

        return preserve(data, output.getvalue(), actions, rectangle)
    return output.getvalue()
