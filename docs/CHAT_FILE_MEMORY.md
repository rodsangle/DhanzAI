# Files retained in a chat or project

Dhanz builds a file catalog from the attachments and generated-download actions
already saved in the conversation database. It uses current owned document
records for filenames and IDs, so the model's shortened chat-history window does
not erase those references. No new global personal memories or duplicate file
uploads are created.

Each reply gets a compact catalog of up to 30 available files. The `chat_files`
tool can search by filename, list further entries, and read bounded excerpts of
the stored extracted text. It does not reread every workbook/PDF or send entire
documents to the model on every message. Full spreadsheet data still uses
`excel_workbook` and `copy_workbook_column` against the stored XLSX bytes.

For example, after uploading a workbook, a later message can say:

> What files did I upload in this chat? Find Schedule.xlsx and use it for the
> next workbook copy without asking me to upload it again.

The same project/topic can include its own library files and attachments from
other non-temporary chats in that project. Another project, unrelated chat or
another account's library is not searched. Temporary chats retain only their
own references and do not contribute attachments to sibling project catalogs.

Generated Word/Excel/PDF downloads recorded as `download_file` actions are also
discoverable. Current file ownership is rechecked before returning metadata or
text. Deleted document records and documents without stored file references are
omitted, and deleting a chat removes its chat-only references. Existing file,
conversation and temporary-chat retention settings continue to apply. A file
already stored separately in a project remains subject to that project's normal
library retention.

The automatic catalog is intentionally bounded. Each lookup gathers up to
1,000 distinct references per scope source, then returns a small page; filename
search can locate older matching references without replaying the chat text.
Extracted text can be incomplete (for example, spreadsheet text previews);
filenames alone are not evidence of document content. The model must use the
appropriate file tool before claiming to have read or edited a file.

## Install on AWS

Download `deploy/updaters/install_chat_files.py` from the reviewed commit and run
it with `--apply`. It patches only the current API image's existing studio startup
hook and adds `chat_files.py`. Existing model providers, OCR, spreadsheet tools,
ROG pairing, project instructions, saved personal memories and permissions are
preserved. No database migration or web build is needed. The updater refuses
active build/connected-operation/creative jobs, checks startup as the configured
image user, recreates only the API and writes an image rollback command.

Refresh Dhanz after installation and continue the original chat. Previously
retained uploads/downloads are discovered from the existing database; they do
not need to be uploaded again for this feature. Check it with “List the files
already available in this chat and tell me their filenames.”
