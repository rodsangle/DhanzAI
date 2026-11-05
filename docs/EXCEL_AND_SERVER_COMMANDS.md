# Excel workbooks and connected AWS commands

This backend-only add-on works with the existing browser/Android PWA. It adds
`excel_workbook` and installs the existing connected-command chat bridge without
rebuilding the browser or replacing the live custom API with an older base image.

## Install on the paired AWS host

Download `deploy/updaters/install_spreadsheet_tools.py` from the published commit,
then run `python3 ~/install_spreadsheet_tools.py --apply`.
Without `--apply` it prepares and tests an image without activating it.

The installer discovers the current Compose overlays from the live API container,
derives a small image from that exact image, adds a startup hook, runs an offline
startup/tool smoke check, and recreates only the API. It saves a rollback command
and restores the previous image if health checks fail. Existing environment
variables, database, browser, weather, OCR, search and paired host settings remain.
Wait for running coding/server jobs to finish first. An unknown customized
operations chat module is refused rather than silently overwritten.

## Excel from chat

Upload an XLSX file with the request, for example:

> Inspect this workbook. Make the heading row bold with a blue fill and white
> text, wrap descriptions, set column widths to 24, freeze the heading row, and
> add a formula in D2:D20 multiplying quantity in B by price in C. Save a copy
> called Formatted.xlsx and give me the download.

The tool inspects sheet names and previews, edits actual cells/styles, and returns
a stored downloadable copy owned by the requesting account. Original uploads are
never overwritten. If several workbooks are attached it asks which one to edit.
Explicit `document_id` selections are checked against the account. Repeated
identical calls within one reply reuse the saved artifact.

Supported actions: new worksheet; text/numeric cells; formulas with relative fill;
bold/italic/font and fill colors; number formats; wrapping/alignment/borders;
column widths and row heights; freeze panes; filters. New workbooks begin with
`Sheet`. Formulas are saved **without calculated caches**; Excel recalculates on
opening. The server does not execute formulas or run Excel. Not every Excel
function is supported. Formatting is not a repair for incorrect PDF/OCR data.
Existing workbooks are updated through their original OOXML package: edited cells
and style additions are patched while unrelated parts and Excel extensions remain.
This preserves conditional-formatting extensions and untouched worksheets instead
of replacing the entire package with openpyxl's rendered workbook. Existing
standard Excel functions use Excel's built-in catalog rather than the smaller
new-formula function list. Targeted inspection can read a specific sheet/range
(up to 500 cells) and reports occupied cells before overwriting a totals row. Macros, embedded objects, external
workbook/data connections and network/DDE formulas are rejected.

Limits: 20 MB input, 40 MB expanded archive, 30 worksheets, 50,000 populated cells,
40 actions per call, 5,000 cells per addressed range, 20,000 rows and 256 columns.
At most four output workbooks per reply. This is intended for ordinary tables,
not large financial models.

## Named AWS commands

Chat uses `connected_operations` to find this account's active grants, and
`run_connected_task` to enqueue a permitted fixed recipe on the paired AWS host.
Existing health/restart commands keep their existing permissions. Queue acceptance
is not completion; ask to check connected task status for the actual outcome.
This companion returns success/failure status; it does not return stdout/stderr.
No AWS credentials, public terminal endpoint or arbitrary model-generated shell
commands are added.

To add a command, run this locally in the AWS terminal:

```bash
python3 ~/dhanz-spreadsheet-setup/add_server_command.py
```

The wizard asks for a new task name, description, working directory, exact command
and timeout, shows the parsed fixed argument list, and saves only after `ADD`.
It preserves the private token and existing tasks. Existing script arguments are
resolved to absolute paths and pinned by SHA-256. Shell operators are not expanded.
After the next companion heartbeat, open **Connected operations** and authorize
the new named task before asking Dhanz to run it. Grants remain account-scoped,
limited, expiring and revocable; no new permissions are granted by installation.

## Multi-step workbook replies

The normal five-round tool limit can interrupt inspection plus several edits.
The add-on extends a reply to at most twelve tool rounds after a successful
`excel_workbook` call. Ordinary tool workflows and replies with only failing Excel
calls retain the existing limit. Each call runs once; the extension does not
restart a reply or replay server tasks. The original installed orchestration
method is retained with guarded local source changes, so provider routing,
token accounting and cancellation continue through the existing implementation.
An unknown interface fails the installer smoke check before activation.

Chat guidance asks the model to inspect the destination once and batch formatting
and formulas in one edit. If the limit is reached, the reply explicitly says a
workbook without an attached download is unfinished.

## Validation

`tests/studio/test_spreadsheets.py` verifies XLSX round trips, relative formulas,
leading zeros, formatting, original preservation, bounded/untrusted inputs,
account isolation, real saved artifacts, reply deduplication, installer payloads
and script pinning. Existing connected-operations tests cover grants, deduplication
and companion execution.
