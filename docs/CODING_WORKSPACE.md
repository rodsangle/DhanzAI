# Dhanz 0.9.5 coding workspace preview

This adds three connected features to the existing 0.9.4 builder: GitHub coding drafts, hosted build/test checks and bounded project repairs. The browser/Android PWA receives the same `/app/` build. Existing features and private API extensions are preserved.

## How to use it

1. Open **Codex coding workspace** in the sidebar. Choose an available API model. Codex model availability and generation still depend on the OpenAI API account; ChatGPT subscriptions are separate.
2. Connect/select repositories through the existing GitHub screen. Fine-grained GitHub token permissions for publication: Contents read/write, Pull requests read/write, Workflows write, Actions read. Optional Checks read permits check annotations. Scope the token to the intended repositories. Enter it only in Dhanz's private connection field, never in chat or generated code. No extra permission is needed for an existing connection that already has these rights.
3. Browse a repository and select source paths (up to 12 bounded UTF-8 files), or select an existing completed/failed builder project to repair or extend. The base branch is resolved to an immutable commit before source is read. Repository content is untrusted data. Stored connection tokens are not put in model context, and common credential patterns in selected source are rejected.
4. Describe the change and create a coding draft. The existing durable builder generates complete changed files and needed tests. Open the finished draft, edit files if needed and **Prepare file review**. Review both source diffs and the fixed GitHub Actions workflow. All overwritten paths are resolved at the base commit, including existing files that were not selected for model context; executable modes are preserved. Truncated repository trees are rejected rather than treated as complete. Manual source edits also update that new private project's ZIP; the previous source project remains intact.
5. **Publish & run GitHub checks** confirms the repository, base and external action. Dhanz creates a new `dhanz/…` branch, an atomic commit and a draft PR. It never commits directly to the base branch, merges or deploys. If the base changed, start a fresh draft. If a remote write has an uncertain outcome, check the branch on GitHub rather than blindly retrying.
6. **Refresh check results** fetches only matching workflow/commit results and bounded annotations; it does not download logs. GitHub Actions must be enabled. A missing run or missing tests is not success.
7. **Repair once with AI** creates a new private project attempt after generation/check failure. Optionally enable **Allow one automatic AI repair attempt** when creating the draft. That option may add one paid model call after a generation failure, or after refreshing failed GitHub checks. Authentication, quota, incompatibility, network and timeout failures are not automatically replayed. Repairs never auto-publish; another reviewed publication creates a separate branch/draft PR. One repair is allowed per draft, and failed originals are retained.

## Build/test scope and costs

Generated code never executes on the API/Lightsail server. Tests run on GitHub-hosted Ubuntu runners with read-only job permissions, no persisted checkout credentials and no injected OpenAI key or repository secrets. Existing repository code/dependency install scripts run there as part of the explicitly published check. GitHub runner usage may incur charges under the GitHub account; no runner quota is included with the OpenAI model.

Supported check profiles:

- Python 3.12: install `requirements.txt` if present, compile source and discover/run `unittest` tests. Zero tests fails explicitly. Pytest-only projects need unittest-compatible tests or a later profile extension.
- Flutter 3.47.8 / Dart (connected repositories): resolve packages, analyze, run Flutter tests and compile the web app. Set **Check folder** to the app folder (for Dhanz: `apps/dhanz_flutter`) in a monorepo. Source paths remain relative to the repository root.
- Web/Node.js 22: check `.js` syntax, install declared npm dependencies, run an optional build script and `npm test`. A static page without a test script can build, but tests remain unverified and the test step fails explicitly.

This is a coding workflow with model edits, a file editor, review, GitHub builds/checks and repair. It is not an unrestricted terminal, a desktop-control agent, an automatic deployment service or a guarantee that generated code/tests are correct. Selected source limits are 12 files, 100 KB each and 120,000 characters of total model context. Generated project limits remain 32 files/600 KB, with ordinary text/code extensions.

## Installation and rollback

First run `deploy/updaters/install_coding_workspace.py --apply` on AWS. It requires the installed builder protocol repair and Alembic 0011. It builds a derived current image offline, checks imports/routes, privately backs up PostgreSQL and applies additive migration 0012. It preserves an existing GitHub encryption key. If no key or saved connections exist, it creates a key in a private Compose overlay; it refuses to replace a missing key for existing encrypted connections. It recreates only the API, checks health and authentication, and records an image rollback command. New tables are retained on image rollback so records are not dropped. No model call, repository write or generated-code execution happens during installation.

Then run `deploy/updaters/install_pwa_coding.py --apply`. This requires the exact deployed 0.9.4+22 baseline and coding backend route. It downloads the checked 0.9.5+23 web package/checksum, backs up the browser files privately and changes only the nested app assets. Refresh Edge and reopen the Android PWA.

Production activation still requires running these helpers on AWS; publishing this preview alone does not change the live server. Future laptop synchronization must include the new client source or it may restore the older UI.
