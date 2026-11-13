# Architecture: closing the ChatGPT parity gaps in DHANZ AI

DHANZ already has its stack: FastAPI with PostgreSQL and pgvector, a Flutter app, and Caddy on
AWS. This plan does not choose a new stack. It orders the missing features from
`features.csv` and fits each into the existing code and the live server.

## Build order

| # | feature | why this order | size |
| --- | --- | --- | --- |
| 1 | Branch a chat from any reply | visible, self-contained, no schema change to existing tables | S |
| 2 | Archive chats | small; clears the history without deleting | S |
| 3 | Public share links (revocable) | biggest of the three; needs a public page and privacy rules | M |
| 4 | Plans, quotas and payments (Stripe) | the largest gap; needs the owner's Stripe account and pricing decisions | L |
| 5 | Scheduled recurring prompts | needs a job runner; builds on reminders | M |
| 6 | Project-only memory, memory summary | memory table plus a project flag | M |
| 7 | Deep-research plan and progress view | extends the existing research pipeline | M |

Items 1–3 are this round.

## How they reach the live server

The live API is a customised image. Update scripts have patched `app/main.py`,
`app/models/__init__.py` and `app/services/chat_service.py` in it, so these features must not
edit existing files beyond one-line, append-only hooks.

- **Package:** `app/conversation_extras/` holds its own models, routes and clean-up. Nothing in
  the existing routes changes.
- **Hooks:** `main.py` calls `conversation_extras.install(app)`, and `models/__init__.py`
  imports its models.
- **Tables:** `conversation_archives` and `shared_conversations`. They are new tables with
  foreign keys to `users` and `conversations` (ON DELETE CASCADE). Deleting a chat or an account
  deletes its shares and archive mark, so no copy outlives the original.
- **Migrations:** the repository gets an Alembic migration (`0009`). On the live server, whose
  Alembic chain contains server-only migrations, `scripts/server/deploy_conversation_extras.py`
  creates the two tables with `IF NOT EXISTS`, the same way earlier server extensions were
  installed. It also checks the hooks' anchors, builds an image from the running one, tests it,
  keeps a rollback image, and reports health.

## API (prefix `/api/v1`)

| method | path | auth | purpose |
| --- | --- | --- | --- |
| POST | `/conversation-extras/{id}/branch` `{message_id}` | user | new chat with messages up to and including that message |
| GET | `/conversation-extras/archived` | user | archived chat ids (the app hides them from the history) |
| PUT / DELETE | `/conversation-extras/{id}/archive` | user | archive / restore |
| POST | `/conversation-extras/{id}/share` | user | create a share: a frozen copy of the chat as it is now |
| GET | `/conversation-extras/shares` | user | the user's share links |
| DELETE | `/conversation-extras/shares/{token}` | user | revoke a link |
| GET | `/shared/{token}` | public | read a shared chat |

## Privacy rules for share links

- **Frozen copy:** a share holds a copy of the chat at the moment it is shared. Later messages
  are not shared.
- **What is copied:** the role, text, model name and the titles and URLs of web sources. Never
  attachments, file names, tool activity, memory, project names or the owner's identity.
- **Link:** the token is random (192 bits). Revoked or deleted links return 404 and say nothing
  more.
- **Temporary chats** cannot be shared or branched.
- **Rate limit:** 20 shares a minute per user.

## App

- **Branch:** a reply action, "Branch in new chat", opens the new chat.
- **Archive:** "Archive" in a chat's menu. Settings → "Archived chats" lists them with Restore.
- **Share:** "Share chat" in the chat's top bar opens a dialog to create a link, copy it and
  revoke it. Settings → "Shared links" lists all links with Revoke.
- **Public page:** `/share/<token>` is a read-only page that works without signing in.
- **Older servers:** on a server without the extension, the app hides or explains these features
  ("not available on this server yet") instead of failing.
