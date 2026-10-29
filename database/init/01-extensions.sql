-- Runs once when the PostgreSQL volume is first created (docker-entrypoint-initdb.d).
-- pgvector powers the Phase 2 knowledge engine (semantic search over embeddings).
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
