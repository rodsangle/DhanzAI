# CSV totals agent

The generated `New_app.zip` contained a Python command-line CSV calculator. This
integration makes that specific reviewed calculator available as `csv_totals`
in Dhanz chat. It does not add arbitrary uploaded-code execution or a general
agent hosting service. A separate always-running process or public port is not
needed.

The original implementation stripped column names but continued to look them up
in a dictionary with untrimmed keys. A header such as ` price ` consequently lost
its numeric values. It also used binary floating-point sums and did not reject
duplicate headers or inconsistent rows. The reviewed core uses positional CSV
fields, validates the complete table, and returns exact bounded decimal totals.

## Use in Dhanz

Install `deploy/updaters/install_csv_totals_agent.py --apply` on the existing AWS
host, using Python 3. It builds from the current API image, preserves existing
Compose overlays/settings, tests startup as the configured image user, and
records a rollback command. It refuses deployment while builds, media jobs or
connected server tasks are active. No CSV or provider request is processed by
the installer. A built-in literal sample is checked offline.

Start a new chat, upload a UTF-8 CSV/TSV, and ask:

> Use csv_totals on sales.csv. Total price and quantity. Exclude the ID column
> and report any blank or nonnumeric cells.

Select exact column headings when you know them. Without a column selection,
all numeric columns are totaled, including numeric identifiers. The tool does
not interpret currencies, thousands separators or decimal-comma numbers; it
reports those cells as nonnumeric. Comma, semicolon, tab and pipe delimiters are
supported. Files with duplicate/empty headers, inconsistent records or excessive
values fail without returning partial totals.

Limits: 25 MB, 100,000 data rows and 200 columns. Full file bytes are used instead
of the knowledge library's text excerpt. Explicit document IDs require ownership
and a retained chat/project reference or a current attachment. Filename selection
prefers current attachments, then recent chat attachments. Other accounts,
unrelated libraries and arbitrary Windows/server paths cannot be read.

Calculation is deterministic and makes no provider/network requests. Normal
assistant replies may still use the account's configured AI provider. Existing
permissions are preserved. No web-client rebuild is required.

## Standalone use

`server_extensions/assistant_studio/csv_totals_agent.py` also runs independently
with Python 3.8+ and no additional packages:

```bash
python3 csv_totals_agent.py sales.csv --columns price quantity
```

Use `py -3` instead of `python3` in Windows PowerShell. Output is structured JSON,
with decimal totals as strings. This command reads the explicitly supplied
local path; the Dhanz chat tool uses uploaded documents instead.
