# Update against the universal assistant specification

The supplied specification is preserved in [PROJECT_REQUIREMENTS.md](PROJECT_REQUIREMENTS.md).
The existing [architecture](ARCHITECTURE.md) and [feature roadmap](ROADMAP.md) remain the
implementation references. This update extends the existing application rather than creating
a second Phase 1 project.

## Added in this update

- Optional local recognition of scanned PDF pages using Poppler and Tesseract.
- Recognition warnings and page/time limits; recognized text uses existing private indexing,
  document attachments, project boundaries and source citations.
- Malware scanning before document parsing when ClamAV is configured; scanner failures remain
  fail-closed.
- Docker OCR dependencies, backend configuration, regression tests and [setup instructions](OCR.md).
- Corrected stale Phase 1 roadmap entries for projects and conversation exports.

## Requirements still needing work or external setup

The specification is not fully delivered or verified by this update. In particular:

- Google and Apple account sign-in, email verification and MFA are not implemented.
- General report/spreadsheet file generation is not implemented; conversation exports exist.
- Direct calendar account integration is not implemented; calendar-file export exists.
- Object storage currently uses the server's local disk; production encryption relies on
  deployment storage rather than application-level message encryption.
- Standalone local Ollama mode does not provide all backend features, account synchronization,
  document processing or research. Offline history/cache still needs work.
- Real-engine OCR quality, native push delivery, release update installation and store distribution
  require environment/device verification. CI configuration alone is not a released application.
- Signing certificates, Apple/Google developer accounts, provider credentials, HTTPS hosting,
  and store review remain operator requirements. iOS builds require macOS/Xcode and Apple signing.

Follow [INSTALL.md](INSTALL.md), [RELEASE.md](RELEASE.md), [SECURITY.md](SECURITY.md) and
[ROADMAP.md](ROADMAP.md) for platform commands, release checks and further limitations.
