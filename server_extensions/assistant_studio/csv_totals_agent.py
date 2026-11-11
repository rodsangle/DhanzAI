"""CSV totals calculator: standalone CLI and the deterministic Dhanz agent core."""

import argparse
import csv
import io
import json
import re
from decimal import Decimal, localcontext
from pathlib import Path

MAX_BYTES = 25 * 1024 * 1024
MAX_ROWS = 100_000
MAX_COLUMNS = 200
NUMBER = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,3})?$")


def calculate(data, columns=None, delimiter=None):
    if not isinstance(data, bytes) or len(data) > MAX_BYTES:
        raise ValueError("Use a CSV file no larger than 25 MB.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Save the CSV as UTF-8 and upload it again.") from None
    if "\x00" in text:
        raise ValueError("The file is not a supported UTF-8 CSV.")
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:65536], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    if delimiter not in (",", ";", "\t", "|"):
        raise ValueError("Choose comma, semicolon, tab or pipe as the delimiter.")
    try:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        raw_headers = next(reader, None)
        if not raw_headers or len(raw_headers) > MAX_COLUMNS:
            raise ValueError("Use a header row with 1–200 columns.")
        headers = [h.strip() for h in raw_headers]
        if any(not h or len(h) > 300 for h in headers) or len(set(headers)) != len(headers):
            raise ValueError(
                "Column headers must be nonempty and unique after trimming spaces (at most 300 characters)."
            )
        if columns is not None and (
            not isinstance(columns, list)
            or not 1 <= len(columns) <= MAX_COLUMNS
            or any(not isinstance(c, str) or c not in headers for c in columns)
            or len(set(columns)) != len(columns)
        ):
            raise ValueError("Choose unique, existing column headers to total.")
        selected = headers if columns is None else columns
        indices = [(headers.index(h), h) for h in selected]
        totals = {h: Decimal(0) for h in selected}
        numeric = {h: 0 for h in selected}
        ignored = {h: 0 for h in selected}
        blanks = {h: 0 for h in selected}
        rows = 0
        with localcontext() as context:
            context.prec = 384
            for row in reader:
                if not row or not any(cell.strip() for cell in row):
                    continue
                rows += 1
                if rows > MAX_ROWS:
                    raise ValueError("The CSV exceeds 100,000 data rows; no partial totals were returned.")
                if len(row) != len(headers):
                    raise ValueError(
                        f"CSV record {rows + 1} has a different number of fields than the header; no totals returned."
                    )
                for index, header in indices:
                    value = row[index].strip()
                    if not value:
                        blanks[header] += 1
                    elif not NUMBER.fullmatch(value):
                        ignored[header] += 1
                    else:
                        if len(value) > 128:
                            raise ValueError("A numeric value is too long; no partial totals were returned.")
                        number = Decimal(value)
                        if not number.is_finite() or abs(number.adjusted()) > 100:
                            raise ValueError(
                                "A numeric value exceeds the supported magnitude; no partial totals returned."
                            )
                        totals[header] += number
                        numeric[header] += 1
        result = []
        for header in selected:
            value = format(totals[header], "f")
            if "." in value:
                value = value.rstrip("0").rstrip(".")
            result.append(
                {
                    "column": header,
                    "total": value if numeric[header] else None,
                    "numeric_values": numeric[header],
                    "nonnumeric_values": ignored[header],
                    "blank_values": blanks[header],
                }
            )
        return {
            "rows_processed": rows,
            "headers": headers,
            "columns": result,
            "delimiter": delimiter,
            "complete": True,
            "note": "Totals are exact decimal strings. Non-numeric cells are counted, not evaluated. "
            "Select measure columns to avoid summing numeric IDs. Currency symbols, thousands separators and "
            "decimal-comma notation are not interpreted automatically.",
        }
    except csv.Error:
        raise ValueError(
            "CSV parsing failed; no partial totals were returned. Check quoting, delimiter and field sizes."
        ) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Calculate numeric CSV totals without API calls.")
    parser.add_argument("csv_path")
    parser.add_argument("--columns", nargs="+", help="Exact column headers; default: all columns.")
    parser.add_argument("--delimiter", choices=[",", ";", "\t", "|"])
    args = parser.parse_args(argv)
    try:
        with Path(args.csv_path).open("rb") as handle:
            data = handle.read(MAX_BYTES + 1)
        print(json.dumps(calculate(data, args.columns, args.delimiter), indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"CSV calculation failed: {exc}\n")


if __name__ == "__main__":
    main()
