# Dhanz 0.9.4 assistant studio preview

This additive release targets the uploaded 0.9.2 backend (Alembic 0010) and the deployed 0.9.3+21 nested PWA. It preserves existing API code and active Compose overlays. It does not replace the server with the older public backend.

- Reply ratings are persisted per account and message. A second click clears a rating. They are feedback records; they do not automatically retrain a model.
- App & agent builder creates private, durable source-file projects through the configured official OpenAI API. It discovers available model IDs, prioritizes Codex IDs and offers supported general-model fallbacks. API usage is billed by the existing OpenAI account; a ChatGPT model-picker choice is not an API credential or entitlement. A listed model can still reject generation due to quota or access.
- Builds continue after leaving the screen. Completed projects offer actual ZIP downloads and source viewing. Static app previews run in an opaque-origin sandbox with network and forms disabled. This release does not execute Python, run terminal commands, install generated projects or deploy them.
- Explicit PDF-to-Excel requests with PDFs attached to the same message use original stored source bytes and process every page, rather than model-selected excerpts. Native text uses Poppler; scanned pages use existing OCR settings/Tesseract. Output has one editable worksheet per PDF, unique valid names, string cells preserving leading zeros, formatting and source-page comments. Low-confidence OCR and ambiguous missing cells are highlighted. Complex layouts and handwriting require review; this is not perfect manual verification or guaranteed reproduction of every table.
- Limits: 10 PDFs, 80 MB combined, configured OCR page limit per PDF (currently 20), 60 pages total, 10,000 rows and 50 columns per sheet. Limit failures create no partial workbook. Conversion bypasses paid model generation.

## Deployment

First run `deploy/updaters/install_assistant_studio.py --apply` on AWS. The single-file helper embeds only the reviewed extension source, reads the active image and Compose labels, checks expected interfaces, builds a derived image and tests imports/worksheet rendering. It takes a private PostgreSQL dump before migration 0011, then recreates only the API and checks health and authentication. Existing files and secrets are not printed. A private rollback command restores the prior image; additive tables remain to preserve records.

Next run `deploy/updaters/install_pwa_studio.py --apply`. This requires the authenticated studio route and the matched 0.9.3+21 release, downloads the checked compiled 0.9.4+22 build and checksum, takes a private browser backup and replaces only nested `/app/` assets. No Flutter SDK or native APK is needed. Refresh Edge and reopen the Android PWA.

Keep the printed backup paths. Do not paste database dumps, `.env` files, keys or private build source into chat. The laptop source snapshot must also be updated before a future server synchronization; deploying old local source can undo these changes.

## Verification

Python tests cover authenticated ownership, persistence, idempotent builds, job claiming, actual ZIP output, unsafe paths, provider failures, migration preservation, page limits, cancellation, OCR confidence and a genuine 13-page PDF conversion. Flutter CI analyzes and tests the matching client and builds the compiled `/app/` package with Flutter 3.47.8. Neither suite establishes extraction accuracy for a particular user PDF that has not been supplied for testing.
