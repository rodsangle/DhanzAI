# Scanned training forms to Excel

The PDF converter recognizes the ruled five-column apprentice training form
(Apprentice Name, Apprentice Level, Signature, Date, Hours). It anchors cells to
printed horizontal rules and header positions instead of clustering handwriting
coordinates. Rosters use printed name/level baselines. On four-field rosters,
the shared date remains page metadata and the workbook Date column is blank for those rows.
Each PDF remains in its own worksheet, in page order. Other layouts
retain the existing OCR conversion path.

The additive installer preserves the current API image, Compose settings, OCR,
search, browser client and server pairing. It checks known module hashes, validates
startup as the configured image user, and saves an image/settings rollback command.

Run `python3 ~/install_pdf_layout.py --apply` after downloading the published
standalone installer. Re-upload original PDFs: existing attachments and workbooks
are not reprocessed.

AI handwriting is enabled by this installer using the existing server-side OpenAI
key. It sends cropped handwritten fields with physical row numbers, at most one
request per recognized page and 20 requests per conversion. API credits apply.
No model request is made during installation. No automatic provider retries occur.
Use `--apply --local-only` to disable AI handwriting and keep structural OCR.

Vision may update only Signature, Date and Hours. Missing, duplicate or unexpected
row IDs reject the response. Printed names and levels retain OCR values. Unclear
fields, conflicting readings and vision transcriptions receive review comments
and yellow highlighting. Transcription is not certified verification; check the
workbook against the originals before relying on personnel records. Signatures
are text transcriptions rather than embedded signature images.
