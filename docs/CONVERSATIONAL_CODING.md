# Dhanz 0.9.7 conversational coding setup

The Codex workspace now gathers a coding task through a chat box and explained choice cards. There are no setup dropdowns in this workspace. You can click an option, type its name/number, or give a free answer where the question needs requirements, paths, a branch or an app folder. An explicit Python/Flutter/web request pre-fills its recognized project type rather than asking again. Ambiguous or unavailable models/repositories are clarified instead of guessed.

## Starting from the normal chat

Type the request into the normal composer and choose **Continue in Codex**. This sends neither a duplicate ordinary chat prompt nor a paid planning request. The coding page receives the typed draft and the selected conversation ID, scoped to the current account and server. It reads that conversation through the existing authenticated API and displays a bounded recent text excerpt (up to eight completed user/assistant messages, 3,500 characters total). Hidden/system/tool messages and unfinished replies are excluded. View or remove the imported text before starting. History from temporary chats and attachment contents are not imported; select code files explicitly from the repository browser.

You can also open **Chat with Codex** in the sidebar and start with a fresh request. The setup asks about must-have behavior, new/previous/repository work, destination, selected source, project/check profile, model and optional single repair. Existing file review, manual editing, ZIP downloads, GitHub publication, hosted checks and repair controls are preserved.

## Model calls and persistence

These setup questions run locally using the actual available models, connected repositories and saved-project lists. They are guided configuration, not free-form model-generated planning replies or an unrestricted coding terminal. The paid model call starts only when you choose **Start coding** (or type that after the setup is ready). A confirmation summary shows the collected settings. Task details, added requirements and included chat text become the existing private coding-draft request. Repeating Start coding without changing those inputs reuses the saved result rather than queueing another request in that page session.

In-progress setup remains in the page until the draft is created; refreshing/navigating away can lose unsaved setup. Created coding drafts/project instructions remain on the server as before. The selected chat itself is not rewritten by this handoff. Publishing changes still requires reviewing files and explicitly publishing a new branch/draft PR; setup answers never perform those writes.

## Installation

`deploy/updaters/install_pwa_coding_chat.py --apply` installs only the compiled nested `/app/` browser build. It accepts the known 0.9.4, 0.9.5 and 0.9.6 client sources, requires the existing coding backend, validates the package/checksum, keeps a private backup and prints rollback instructions. No backend image restart, database migration, API key change or native APK is required. Existing read aloud, sharing, spelling, reply ratings and other client features remain.

Flutter CI analyzes the whole matching client, runs planner/context/interaction tests and the existing tests, then compiles the web app with Flutter 3.47.8. Setup privacy tests cover foreign-account context rejection and temporary-chat exclusion; platform publication remains an explicit separate action.
