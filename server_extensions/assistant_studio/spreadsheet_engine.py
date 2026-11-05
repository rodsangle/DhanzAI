"""Bounded, deterministic XLSX editing. Never executes workbook formulas."""

import io
import re
import zipfile
from copy import copy

from openpyxl import Workbook, load_workbook
from openpyxl.formula import Tokenizer
from openpyxl.formula.translate import Translator
from openpyxl.styles import Border, PatternFill, Side
from openpyxl.utils.cell import range_boundaries
from openpyxl.workbook.properties import CalcProperties

MAX_CELLS = 50000
FUNCTIONS = set(
    "SUM AVERAGE MIN MAX COUNT COUNTA COUNTBLANK SUMIF SUMIFS COUNTIF COUNTIFS AVERAGEIF AVERAGEIFS IF IFS IFERROR IFNA AND OR NOT ROUND ROUNDUP ROUNDDOWN ABS MOD INT CEILING FLOOR SUMPRODUCT SUBTOTAL AGGREGATE VLOOKUP HLOOKUP XLOOKUP INDEX MATCH XMATCH LEFT RIGHT MID LEN TRIM CLEAN CONCAT CONCATENATE TEXTJOIN TEXT VALUE DATE YEAR MONTH DAY TODAY NOW DATEDIF DAYS EDATE EOMONTH WEEKDAY NETWORKDAYS WORKDAY ISBLANK ISNUMBER ISTEXT TRUE FALSE UPPER LOWER PROPER SUBSTITUTE REPLACE FIND SEARCH FILTER SORT UNIQUE SEQUENCE".split()  # noqa: E501 - descriptive tool text
)


def formula(value):
    if not isinstance(value, str) or not value.startswith("=") or len(value) > 8192:
        raise ValueError("Use an Excel formula beginning with =, at most 8192 characters.")
    try:
        tokens = Tokenizer(value).items
    except Exception:
        raise ValueError("Invalid Excel formula.") from None
    for token in tokens:
        if token.type == "FUNC" and token.subtype == "OPEN":
            name = token.value[:-1].upper().removeprefix("_XLFN.")
            if name not in FUNCTIONS:
                raise ValueError("Unsupported formula function: " + name)
        if token.type == "OPERAND" and token.subtype == "RANGE":
            operand = token.value
            if any(x in operand for x in ("|", "\\", "://")) or ("!" in operand and "[" in operand.split("!")[0]):
                raise ValueError("External workbook, network and DDE references are unsupported.")
    return value


def rectangle(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z]{1,3}[1-9][0-9]{0,4}(?::[A-Za-z]{1,3}[1-9][0-9]{0,4})?", value
    ):
        raise ValueError("Use a bounded A1 range, for example A1:F30.")
    a, b, c, d = range_boundaries(value)
    if a > c or b > d or c > 256 or d > 20000 or (c - a + 1) * (d - b + 1) > 5000:
        raise ValueError("Range exceeds 5000 cells, 256 columns or 20000 rows.")
    return a, b, c, d


def load(data=None):
    if data is None:
        return Workbook()
    if len(data) > 20000000:
        raise ValueError("Workbook exceeds 20 MB.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 2000 or sum(p.file_size for p in entries) > 40000000:
                raise ValueError("Workbook expanded size exceeds the processing limit.")
            total_cells = 0
            for item in entries:
                name = item.filename.lower()
                if item.flag_bits & 1 or item.file_size > 10000000 or name.startswith("/") or ".." in name.split("/"):
                    raise ValueError("Unsupported workbook archive.")
                if any(
                    part in name
                    for part in (
                        "vbaproject",
                        "externallinks/",
                        "embeddings/",
                        "macrosheets/",
                        "connections.xml",
                        "querytables/",
                    )
                ):
                    raise ValueError("Macros, embedded objects and external data connections are unsupported.")
                if name.endswith(".xml"):
                    raw = archive.read(item)
                    if b"\x00" in raw or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                        raise ValueError("Unsupported workbook XML.")
                    if name.startswith("xl/worksheets/"):
                        import xml.etree.ElementTree as ET

                        for _, element in ET.iterparse(io.BytesIO(raw), events=("end",)):  # noqa: S314 - DTD/entities and non-UTF8 XML rejected above.
                            if element.tag.rsplit("}", 1)[-1] == "c":
                                rectangle(element.attrib.get("r", ""))
                                total_cells += 1
                                if total_cells > MAX_CELLS:
                                    raise ValueError("Workbook exceeds 50000 cells.")
                            element.clear()
        book = load_workbook(io.BytesIO(data), keep_links=False)
    except (zipfile.BadZipFile, KeyError):
        raise ValueError("Upload a valid .xlsx workbook.") from None
    if len(book.worksheets) > 30 or sum(len(s._cells) for s in book) > MAX_CELLS:
        raise ValueError("Workbook exceeds 30 worksheets or 50000 populated cells.")
    for sheet in book:
        for cell in sheet._cells.values():
            if cell.data_type == "f":
                value = cell.value
                # openpyxl represents array formulas as objects rather than strings.
                if not isinstance(value, str):
                    value = getattr(value, "text", None)
                try:
                    formula(value)
                except ValueError as exc:
                    raise ValueError(
                        f"Existing formula in {sheet.title}!{cell.coordinate} cannot be safely preserved: {exc} "
                        "This error concerns the uploaded workbook, not the requested formatting or new formula."
                    ) from None
    return book


def inspect(data):
    book = load(data)
    return {
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
            raise ValueError("Edit exceeds 50000 addressed cells.")
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
            for key in ("bold", "italic", "wrap_text", "border"):
                if key in options and not isinstance(options[key], bool):
                    raise ValueError(key + " must be true or false.")
            if "number_format" in options and (
                not isinstance(options["number_format"], str) or len(options["number_format"]) > 100
            ):
                raise ValueError("Invalid number format.")
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
        raise ValueError("Result exceeds 50000 populated cells.")
    book.calculation = CalcProperties(calcMode="auto", fullCalcOnLoad=True, forceFullCalc=True)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()
