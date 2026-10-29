# Database

* **Engine:** PostgreSQL 16 with the `vector` (pgvector) and `pg_trgm` extensions.
  `init/01-extensions.sql` runs automatically the first time the Docker volume is created.
* **Schema and migrations:** managed by Alembic in `backend/alembic`
  (`cd backend && alembic upgrade head`). The models live in `backend/app/models`.
* **Tables (Phase 1):** `users`, `refresh_tokens`, `conversations`, `messages`, `audit_logs`.
  Deleting a user cascades to their conversations, messages and tokens.

Create a new migration after changing models:

```bash
cd backend
alembic revision --autogenerate -m "describe the change"
# review the generated file, then
alembic upgrade head
```
