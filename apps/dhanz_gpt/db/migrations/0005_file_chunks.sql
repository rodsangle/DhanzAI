-- 0005: searchable chunks of file text, so big project files are read by relevance
-- instead of being cut off. Full-text search (Postgres tsvector), no embeddings key needed.

create table file_chunks (
  id bigint generated always as identity primary key,
  file_id uuid not null references files(id) on delete cascade,
  idx integer not null check (idx >= 0),
  content text not null,
  tsv tsvector generated always as (to_tsvector('english', content)) stored,
  created_at timestamptz not null default now(),
  unique (file_id, idx)
);
create index file_chunks_tsv on file_chunks using gin (tsv);

alter table file_chunks enable row level security;
-- Readable exactly when the file is (files RLS applies inside the subquery). Written by the server only.
create policy chunks_read on file_chunks for select to authenticated
  using (exists (select 1 from files f where f.id = file_id));
