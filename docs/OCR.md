# Scanned PDF recognition

Backend account mode supports local OCR for PDF pages with no embedded text. Recognized
text enters the same private document, citation, project and retrieval pipeline as ordinary
PDF text. No external OCR service receives the file. Standalone Ollama chat does not use this API.

Set these variables in the backend environment, then restart the API:

```dotenv
OCR_ENABLED=true
OCR_LANGUAGE=eng
OCR_MAX_PAGES=20
OCR_TIMEOUT_SECONDS=90
```

The backend Docker image includes Poppler and Tesseract with English recognition data.
Rebuild it using `docker compose up -d --build`. For a native server, install Poppler
(`pdftoppm`) and Tesseract, and add both executables to the server process's PATH.
Additional language packs must be installed separately; `OCR_LANGUAGE=eng+spa` selects
English and Spanish. See the [Tesseract installation guide](https://tesseract-ocr.github.io/tessdoc/Installation.html)
and [language options](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html).

Verify by uploading an image-only PDF in Knowledge library, inspecting its extracted text,
then asking a question with it attached. Existing uploads must be uploaded again to extract
OCR text. Digital text pages are preserved; only pages with no extracted text invoke OCR.

Recognition is approximate and may misread numbers, handwriting, tables or drawings.
Document notes identify OCR pages, failures and missing text. Processing stops invoking OCR
after the first engine failure; any digital text remains available. Each document has a
shared time budget and a limit on recognized pages. Rendering uses a 2400-pixel longest edge;
temporary inputs and images are deleted after each page. Limits bound subprocess time and
rendered dimensions, but do not replace container memory/CPU limits for untrusted documents.

Run `python -m pytest knowledge_engine/tests/test_ocr.py -q` from the repository root.
These tests cover orchestration with simulated executables; actual recognition quality needs
the manual upload check on a server with both engines installed.
