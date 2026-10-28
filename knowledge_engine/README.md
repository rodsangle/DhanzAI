# Knowledge engine (`dhanz_knowledge`)

Web research and retrieval for DHANZ AI. A plain Python package (no web framework) used by the
backend; tested on its own with `cd knowledge_engine && pytest -q`.

| Module | Responsibility |
|---|---|
| `search.py` | Search-API adapters: Brave Search, Tavily, self-hosted SearXNG. No scraping of search result pages. |
| `safety.py` | SSRF protection: http/https only, ports 80/443, no embedded credentials, every resolved address must be public. |
| `fetcher.py` | Polite fetching: robots.txt (RFC 9309) per host, per-host spacing, identifies itself (`DhanzAI-Research`), no cookies, 2 MB cap, HTML/text only, every redirect re-validated. 401/402/403 are reported as "requires a login or subscription" and never worked around. |
| `extract.py` | Main-content extraction (drops scripts, navigation, cookie banners), title, site name, author, publication date (meta tags, JSON-LD, `<time>`). |
| `ranking.py` | Paragraph-aware chunking with overlap, BM25, cosine similarity, reciprocal-rank fusion. |
| `embeddings.py` | Embedding adapters: OpenAI, Gemini, Ollama. Each vector records its model; vectors from different models are never compared. |
| `research.py` | The pipeline: decide whether to search (`needs_search`), extract pasted links, search → read pages in parallel → rank passages → fall back to search snippets for pages that could not be read → number sources `[1]..[n]` with publication/retrieval dates for the prompt. |

## How the backend uses it

1. For each chat message the backend decides whether to research: the user's web mode
   (*Always*, *Off*) or, in *Auto*, a heuristic for time-sensitive questions. Links pasted in the
   message are always read (unless web is *Off*).
2. The user's private **knowledge library** is searched too (hybrid keyword + vector when an
   embedding model is configured; keyword only otherwise).
3. Sources go into the system prompt inside a `<sources>` block that is explicitly marked as
   untrusted data; the model must cite `[n]` and say when sources are missing or conflicting.
4. The app shows the numbered sources (title, site, publication date, retrieval date) as
   clickable cards under the answer.
5. Pages read during research are saved to the user's library in the background if they
   allowed it (Settings → *Save researched pages to my library*).

Storing pages makes them searchable and citable; it does **not** retrain any AI model.
