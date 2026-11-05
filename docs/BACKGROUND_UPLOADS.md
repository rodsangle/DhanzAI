# Background uploads (0.9.9 preview)

The Knowledge Library previously owned a sequential upload loop in its screen
state. After navigation it could use a disposed widget reference, abandon the
remaining files, or lose progress messages. Chat folder preparation was also
owned by its composer widget, and late file results could attach to a newly
opened chat.

The app now owns a non-auto-dispose upload queue. Library file batches, library
folders, chat attachments and chat folder preparation all use it. Navigating to
another page, switching chats or starting a new chat does not stop queued work.
The original project is captured before the picker opens. Existing conversations
retain their pending attachments when revisited; files from an abandoned new-chat
draft are still saved in the private library and never attached to a different
new chat automatically. Sending waits for that chat's own pending uploads, not
unrelated library uploads.

An app-wide status bar links to **Uploads**. The page distinguishes queued,
preparing, uploading/processing, saved, failed and cancelled work. It does not
invent a percentage while the server runs OCR/indexing. Each HTTP upload runs
sequentially so a large batch does not launch many OCR jobs on the 4 GB host.
Folder archives preserve their paths and existing exclusions. The queue retains
at most 100 MB of selected/prepared input and 200 busy items; completed inputs
release their byte buffers/browser file handles.

Failed uploads keep their error while later files continue. A user can inspect
the library before explicitly retrying, since an ambiguous response may mean a
file was already saved. Network failures are not automatically replayed. Only an
explicit HTTP 401 can trigger the existing token refresh and one guarded retry.
Queued/preparing work can be cancelled before any HTTP upload starts. A request
already received by the server may finish; cancellation is not falsely reported
for that case.

Account/server changes clear pending work and ignore results from the previous
scope. Each request checks the original session before sending. Upload state is
in browser memory: keep the app open. Reloading/closing the tab, signing out or
switching servers does not preserve a resumable queue. Android may suspend a
backgrounded PWA; this change guarantees in-app navigation continuity, not OS
background execution after suspension.

Install `deploy/updaters/install_pwa_uploads.py --apply` on AWS over the verified
0.9.8 browser build. The helper also accepts known older controls builds, verifies
the package checksum and metadata, saves a private backup, and changes only the
nested Flutter assets. It does not rebuild/restart the API or change its database,
GitHub connection, server pairing, OCR, weather or search. Version is 0.9.9+27.
The existing 0.9.8 backend is required for folder parsing.

The separate latest `install_operations_chat.py --apply` enables authorized
GitHub coding tools in ordinary chat. See [Connected operations](CONNECTED_OPERATIONS.md).
