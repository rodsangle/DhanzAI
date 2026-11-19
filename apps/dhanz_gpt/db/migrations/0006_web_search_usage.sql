-- 0006: count web searches per answer (billed per search on the Claude API) next to its tokens.
alter table usage_events add column web_searches integer check (web_searches is null or web_searches >= 0);
