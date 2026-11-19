-- What the person asked for along with a message: image mode and size, web search, "think longer".
-- Read when the answer is (re)generated, so Retry keeps the same choices. Only the server writes it.
alter table messages add column if not exists options jsonb not null default '{}'::jsonb;
