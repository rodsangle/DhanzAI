"""Stream a complete source column into a private copy of an owned workbook."""
import io
import math
import re
from pathlib import PureWindowsPath

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

from . import spreadsheet_engine as engine
from .spreadsheet_package import preserve

SOURCE_RESIDENT_LIMITS = {'xl/sharedstrings.xml': 16000000, 'xl/styles.xml': 4000000,
                          'xl/workbook.xml': 2000000}


def filename(value):
    """A path is a lookup label for an upload, never filesystem authority."""
    if not isinstance(value, str) or not value.strip() or len(value) > 2000 or '://' in value:
        raise ValueError('Specify an uploaded .xlsx filename, document ID, or Windows path as a filename label.')
    name = PureWindowsPath(value.strip().strip('"').replace('/', '\\')).name
    if not name.lower().endswith('.xlsx') or len(name) > 255:
        raise ValueError('Choose an uploaded .xlsx workbook.')
    return name


def normalized(value):
    return re.sub(r'\s+', ' ', str(value or '').strip()).casefold()


def header(sheet, wanted, row=None):
    if not isinstance(wanted, str) or not wanted.strip() or len(wanted) > 200:
        raise ValueError('Specify the column heading, for example Tool ID or LID.')
    if row is not None and (isinstance(row, bool) or not isinstance(row, int) or not 1 <= row <= engine.MAX_ROWS):
        raise ValueError('Header row must be a whole row number between 1 and 100000.')
    matches = []
    rows = ([c for (r, _), c in sheet._cells.items() if (r == row if row else r <= 50)],) if hasattr(sheet, '_cells') else sheet.iter_rows(min_row=row or 1, max_row=row or 50)
    for cells in rows:
        for cell in cells:
            if cell.value is not None and normalized(cell.value) == normalized(wanted):
                matches.append((cell.row, cell.column))
    if len(matches) != 1:
        raise ValueError(f'Heading {wanted!r} in {sheet.title!r} matched {len(matches)} cells. Specify a unique heading and header row.')
    return matches[0]


def source_column(data, sheet_name, heading, header_row=None):
    # Worksheet XML is streamed, not materialized as workbook cell objects. Its
    # aggregate cell count is not the output count; ZIP bytes and resident text/
    # style indexes bound resource use independently of irrelevant source cells.
    engine.validate_archive(data, max_cells=None, expanded_bytes=400000000,
                            part_bytes=300000000, max_columns=16384, max_rows=1048576,
                            resident_limits=SOURCE_RESIDENT_LIMITS, source_external_links=True)
    book = load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
    try:
        if len(book.sheetnames) > 60 or sheet_name not in book.sheetnames:
            raise ValueError('Choose an existing source worksheet; at most 60 source worksheets are supported.')
        sheet = book[sheet_name]
        sheet.reset_dimensions()  # ignore inflated/stale Excel dimension metadata
        row, column = header(sheet, heading, header_row)
        records = []
        formulas = set()
        last = 0
        for source_index, cells in enumerate(sheet.iter_rows(min_row=row+1, min_col=column, max_col=column), row+1):
            cell = cells[0]
            if source_index > engine.MAX_ROWS:
                if cell.value is not None and cell.value != '':
                    raise ValueError('The selected source column has data beyond row 100000; it cannot fit this bounded destination with blank positions preserved.')
                continue
            index = len(records)
            kind = cell.data_type
            value = cell.value
            if kind == 'f':
                formulas.add(index)
            records.append((value, cell.number_format, kind))
            if value is not None and value != '':
                last = len(records)
        records = records[:last]
        if not records:
            raise ValueError('The source column has no data below its heading.')
        if formulas:
            cached = load_workbook(io.BytesIO(data), read_only=True, data_only=True, keep_links=False)
            try:
                cached_sheet = cached[sheet_name]
                cached_sheet.reset_dimensions()
                for i, cells in enumerate(cached_sheet.iter_rows(min_row=row+1, max_row=row+len(records), min_col=column, max_col=column)):
                    if i in formulas:
                        cell = cells[0]
                        if cell.value is None:
                            raise ValueError(f'Source formula {sheet_name}!{get_column_letter(column)}{row+i+1} has no saved value. Recalculate and save in Excel, then upload again; values were not guessed.')
                        records[i] = (cell.value, records[i][1], cell.data_type)
            finally:
                cached.close()
        for value, _, _ in records:
            if isinstance(value, str) and len(value) > 32767:
                raise ValueError('A source value exceeds Excel cell text limits; no value was truncated.')
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError('A source value is not a finite Excel number; no replacement was guessed.')
        return records, row, column
    finally:
        book.close()


def rectangle(value):
    from openpyxl.utils.cell import range_boundaries
    if not isinstance(value, str) or not re.fullmatch(r'[A-Z]{1,3}[1-9][0-9]{0,5}:[A-Z]{1,3}[1-9][0-9]{0,5}', value):
        raise ValueError('Invalid server-generated copy range.')
    a, b, c, d = range_boundaries(value)
    if a != c or not 1 <= b <= d <= engine.MAX_ROWS or c > 256:
        raise ValueError('Copy exceeds 100000 rows or 256 destination columns.')
    return a, b, c, d


def copy_column(source, destination, *, source_sheet, source_header, destination_sheet,
                destination_header, source_header_row=None, destination_header_row=None,
                overwrite=False):
    if not isinstance(overwrite, bool):
        raise ValueError('overwrite must be true or false.')
    records, source_row, source_col = source_column(source, source_sheet, source_header, source_header_row)
    book = engine.load(destination)
    if destination_sheet not in book.sheetnames:
        raise ValueError('Choose an existing destination worksheet.')
    sheet = book[destination_sheet]
    target_row, target_col = header(sheet, destination_header, destination_header_row)
    final_row = target_row + len(records)
    if final_row > engine.MAX_ROWS:
        raise ValueError('Destination would exceed 100000 rows including headers. Split into separate workbooks.')
    missing = sum((r, target_col) not in sheet._cells for r in range(target_row+1, final_row+1))
    if sum(len(s._cells) for s in book) + missing > engine.MAX_CELLS:
        raise ValueError('Destination would exceed 200000 populated cells. Use a smaller destination workbook.')
    conflicts = []
    for index, (value, _, _) in enumerate(records, target_row+1):
        cell = sheet.cell(index, target_col)
        if isinstance(cell, MergedCell) or any(cell.coordinate in area for area in sheet.merged_cells.ranges):
            raise ValueError('The destination copy range contains merged cells. Choose an unmerged destination column.')
        if not overwrite and cell.value not in (None, '') and cell.value != value:
            conflicts.append(cell.coordinate)
    if conflicts:
        raise ValueError(f'Destination contains {len(conflicts)} different existing values (first cells: {", ".join(conflicts[:10])}). Confirm replacement before setting overwrite=true.')
    for index, (value, number_format, kind) in enumerate(records, target_row+1):
        cell = sheet.cell(index, target_col)
        cell.value = value
        if isinstance(value, str):
            cell.data_type = 'e' if kind == 'e' else 's'  # literal = text cannot become a formula
        if number_format and number_format != 'General':
            cell.number_format = number_format  # preserve numeric ID leading-zero display
    book.calculation = CalcProperties(calcMode='auto', fullCalcOnLoad=True, forceFullCalc=True)
    output = io.BytesIO()
    book.save(output)
    area = f'{get_column_letter(target_col)}{target_row+1}:{get_column_letter(target_col)}{final_row}'
    actions = [{'type': 'set_cells', 'sheet': destination_sheet, 'range': area}]
    result = preserve(destination, output.getvalue(), actions, rectangle)
    return result, {'rows_copied': len(records), 'nonempty_values': sum(v not in (None, '') for v, _, _ in records),
                    'source_range': f'{get_column_letter(source_col)}{source_row+1}:{get_column_letter(source_col)}{source_row+len(records)}',
                    'destination_range': area, 'blank_row_positions_preserved': True,
                    'source_formulas': 'saved values only; formulas were not evaluated'}
