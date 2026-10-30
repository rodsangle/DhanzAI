"""Local OCR using Poppler and Tesseract, without sending documents to a service."""

from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path


class OCRError(Exception):
    """Safe, user-facing recognition failure."""


class PDFOCR:
    def __init__(self, data: bytes, *, language: str = "eng", max_pages: int = 20, timeout: int = 90):
        self.data = data
        self.language = language
        self.max_pages = max_pages
        self.deadline = time.monotonic() + timeout
        self.attempted = 0

    def _run(self, args: list[str]) -> None:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise OCRError("OCR processing time limit reached; some pages were not read.")
        try:
            # Fixed executable names and generated paths; no shell or document-supplied arguments.
            subprocess.run(  # noqa: S603
                args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=remaining
            )
        except FileNotFoundError:
            raise OCRError("OCR requires Poppler (pdftoppm) and Tesseract installed on the server.") from None
        except subprocess.TimeoutExpired:
            raise OCRError("OCR processing time limit reached; some pages were not read.") from None
        except (subprocess.CalledProcessError, OSError):
            raise OCRError("OCR could not read a page. Check the file and installed OCR language packs.") from None

    def __call__(self, page: int) -> str:
        if self.attempted >= self.max_pages:
            raise OCRError(f"OCR page limit ({self.max_pages}) reached; some pages were not read.")
        self.attempted += 1
        with tempfile.TemporaryDirectory(prefix="dhanz-ocr-") as directory:
            root = Path(directory)
            source, image, output = root / "input.pdf", root / "page", root / "recognized"
            source.write_bytes(self.data)
            self._run(
                [
                    "pdftoppm",
                    "-f",
                    str(page),
                    "-l",
                    str(page),
                    "-singlefile",
                    "-scale-to",
                    "2400",
                    "-png",
                    str(source),
                    str(image),
                ]
            )
            self._run(["tesseract", str(image) + ".png", str(output), "-l", self.language])
            text_file = output.with_suffix(".txt")
            if not text_file.exists():
                raise OCRError("OCR did not produce readable text.")
            with text_file.open(encoding="utf-8") as handle:
                return handle.read(2_000_000).strip()
