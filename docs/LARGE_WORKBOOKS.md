# Copy full columns between uploaded workbooks

The `copy_workbook_column` chat tool copies an entire named column without
putting its row values into a model prompt. It reads the stored XLSX directly,
streams the source worksheet, and returns a real downloadable edited workbook.
The existing 500-cell inspection response is a preview, not a copy limit.

For example, upload `Schedule.xlsx` and the destination template, then ask:

> Copy the entire Tool ID column from SOW in Schedule.xlsx to the LID column in
> the template we just created. Use copy_workbook_column. Preserve leading zeros,
> row order and blank positions. Save Schedule_LID_Updated.xlsx and report how
> many rows were copied.

Both documents must belong to the signed-in account and have stored XLSX bytes.
The tool can use document IDs or exact uploaded filenames. If multiple uploads
share a filename, it first uses the matching file attached to the current
message, then the most recent matching attachment in this conversation. Two
same-named files attached together remain ambiguous: attach just the intended
one instead of looking for a hidden document ID. It never picks an arbitrary
newest file from the whole library. Another user's file cannot resolve through
the filename, ID or conversation lookup.

## Limits and preservation

* Source: 500,000 populated cells across at most 60 worksheets; up to 1,024 columns.
* Destination: 200,000 populated cells across at most 30 worksheets; up to 256 columns.
* Worksheets: at most 100,000 rows including the heading. One operation copies
  one full column below its heading, preserving internal blanks and excluding
  trailing empty cells.
* Processing input: at most 50 MB compressed per workbook. Archive expansion is
  bounded to 150 MB for a streamed source and 80 MB for a loaded destination.
  The server's existing upload-size setting remains an additional limit.
* One large copy runs at a time across API processes using a shared file lock.
  Compact summaries go to chat; there is no unlimited context or memory setting.

Headings match case and whitespace. The first 50 rows are searched for a unique
heading; an explicit header-row number disambiguates repeated or lower headings.
Destination headers must already exist. Existing conflicting data is reported
with its cell addresses and requires authorization to replace it. Merged
destination cells are rejected. Neither original file is overwritten.

Literal text, including leading zeros and `=`-prefixed text, stays text. Numeric
ID number formats are preserved. Formulas in the selected source column use
their saved cached values; if Excel has not saved a calculated value, the tool
asks for recalculation and a new upload rather than inventing one. It does not
execute formulas. Unrelated source formulas do not need to be understood to copy
stored values from the selected column.

Existing destination formulas and Excel extensions remain subject to the existing
safe editing validation. The output merges only the changed destination cells
and required styles into the original OOXML package, preserving unrelated
worksheets and parts. Macro-enabled files, embedded objects, external workbook
links/data connections, DTDs/entities and duplicate ZIP entries remain unsupported.

## Windows paths and OneDrive

The cloud web app cannot open `C:\Users\...\OneDrive\Schedule.xlsx` just from its
name. A local path does not grant browser or cloud access to that file. Upload it
through Attach files/Knowledge Library first. Once uploaded, the tool can use the
basename `Schedule.xlsx` from that path to identify the owned stored copy.

This is not live OneDrive access or automatic synchronization. If the local
workbook changes, upload the changed version and identify it by document ID.
No arbitrary AWS path or URL is opened by this tool. A PC filesystem bridge or
OneDrive connector would be a separate feature requiring explicit scoped access.

## AWS update

Download `deploy/updaters/install_bulk_workbooks.py` from the reviewed GitHub
commit and run it with `--apply`. It builds from the current API image, verifies
the existing spreadsheet modules have a recognized hash, preserves other studio
hooks (including the ROG worker), checks startup and a real small workbook copy
offline, and recreates only the API container. It refuses active builder,
connected-operation or creative-generation work. A printed rollback command
restores the previous image if needed. No schema migration or browser rebuild is
required. Refresh Dhanz and start a new chat after installation.
