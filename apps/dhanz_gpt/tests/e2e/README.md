# End-to-end checks

Python Playwright against a running build (`npx next build && npx next start -p 3100`, with a fresh `.data/`).

- `flows.py`: the recon flows (sign in, stream, stop, retry, branches, resume after reload, uploads, images, search, rename, share, projects, settings, teammates, mobile). Saves screenshots to `$SHOTS` (default `../replica/clone-screens`).
- `a11y.py`: keyboard-only flow, plus axe-core WCAG 2.1 A/AA on each built screen in light and dark.
- `a11y2.py`: axe-core on real conversations (code block, table, image).

Uses the demo model's dev hooks: `/fail` (error mid-answer) and `/slow` (slower streaming).

Backend suites (run against a local Postgres with `tests/e2e/reset-local-db.sh`):
- `isolation.py`: a second user tries 18 ways into the first user's data, plus account deletion (26 checks).
- `providers.py`: the Claude and image adapters through the official SDK against `tests/mock-api/server.mjs` (start it, then run the app with `MODEL_PROVIDER=anthropic ANTHROPIC_BASE_URL=http://localhost:4010 IMAGE_PROVIDER=openai OPENAI_BASE_URL=http://localhost:4010/v1`, plus a second instance on port 3101).
