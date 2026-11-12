# Office-style workbook preview and clipboard images

Web 0.10.2 adds an Excel-style green ribbon, cell grid with row/column headings,
a name/range box and formula bar to XLSX previews. The panel still opens only
on Preview and supports resizing, expanding and closing.

## Workbook tools

- Click a cell; Shift-click to select a rectangle, or type a bounded range such
  as `G33:AI33`. Enter a value/formula and press the check button to stage it.
- Home: undo/redo pending edits, copy/paste tab-separated cells, bold/italic/
  underline, font color/size, fills, borders, wrapping, alignment, number formats,
  column widths and row heights. Leading zeros remain text.
- Insert: add a worksheet when saving the copy.
- Formulas: AutoSum prepares a formula for review; the formula bar accepts supported
  formulas. Relative filling across a range is performed by the backend on save.
- View: freeze the header, add a filter to the selected range and change zoom.
- Worksheet tabs and row/column navigation page through bounded views of the file.
- **Save copy** persists the staged actions as a new owned XLSX document. Download
  retrieves the saved document, not unsaved edits. The original is retained.

The editor uses Dhanz's workbook tools, not Microsoft's Excel application. Formulas
are stored without a calculation engine; Excel recalculates when opened. Formula
fills may show a pending marker before saving. Existing formulas, conditional
formatting extensions and unmodified package parts use the preservation path.
Macros, embedded objects, external data connections and unsafe formulas remain
unsupported. New worksheets become available after saving. Other document formats
retain their existing read-only previews and download controls.

Unsaved changes are local to the open preview. Closing or switching files asks
before discarding them. Navigation to a new chat clears the preview; save first.

## Clipboard images

In the browser, focus the chat input and press Ctrl+V (or Cmd+V) after copying a
screenshot/image. A Paste image button also reads the clipboard after a user click,
subject to browser permission. No background clipboard polling occurs. Plain text
paste is not intercepted. Supported types: PNG/JPEG/WebP/GIF, at most four images,
10 MB each and 20 MB per paste; SVG/HTML are not converted into executable content.
Images enter the existing account/server/project-bound upload queue and are not
sent as a chat message automatically. The originating upload ticket is captured
before reading clipboard bytes so switching chats does not attach to the wrong
chat. Native clients without image-clipboard support retain Attach files.

## Install on the existing AWS host

Download `deploy/updaters/install_office_preview.py` from the published commit and
run `python3 ~/install_office_preview.py --apply`. This single installer prepares
an additive API image with authenticated workbook read/save routes, checks startup,
then installs the latest checked web-channel build. Each step prints rollback
information. There is no database migration or change to stored original files.

The routes verify document ownership. Save keys bind the source, filename and
changes; PostgreSQL transaction locks make concurrent retries return the existing
copy instead of duplicating it. No AI API call is used for direct ribbon edits.

Refresh Edge with Ctrl+F5. For an installed Android PWA, open
`https://dhanzai.com/app/update.html`, refresh, then close and reopen the app.
