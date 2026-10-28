# Knowledge engine (Phase 2 — not implemented yet)

This directory will hold the web-research and Retrieval-Augmented Generation (RAG) package.
Nothing here is wired into the app yet, and Dhanz tells users it has no live web access.

Planned design (see `docs/ARCHITECTURE.md` and `docs/ROADMAP.md`):

1. **Search** — pluggable search-API adapters (e.g. Brave, Bing, Tavily, self-hosted SearXNG).
2. **Fetch** — HTTP fetcher that checks `robots.txt`, rate-limits per host, identifies itself
   with a clear User-Agent, and never bypasses paywalls, logins or access controls.
3. **Extract** — readability-style main-content extraction; keep title, URL, author,
   publication date and retrieval date.
4. **Index** — chunk text, embed with the configured provider, store in PostgreSQL + pgvector
   (`CREATE EXTENSION vector` is already enabled by `database/init`).
5. **Retrieve and answer** — hybrid (vector + keyword) retrieval; the model answers only from
   retrieved passages and must cite them with clickable links and dates. Retrieved content is
   passed as untrusted data and cannot change the assistant's rules.

Storing documents improves what Dhanz can *look up*; it does not retrain the underlying models.
