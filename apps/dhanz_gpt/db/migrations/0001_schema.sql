-- =============================================================================
-- Flatbill (RODRECH's in-house assistant): schema v1 (first migration)
-- Chat, projects, files, sharing and memory for the RODRECH team.
-- Target: Supabase Postgres 15+ (uses auth.users, auth.uid(), storage.objects).
--
-- Access rules: Postgres row level security on every table.
--   * The browser reads through RLS (supabase-js + Realtime).
--   * User-owned edits (rename chat, project settings, personalization...) go
--     through Next.js server actions using the user's session, so RLS applies.
--   * System writes (assistant messages, runs, usage, tokens) use the
--     service-role key on the server only. Tables with no write policy are
--     service-role-write by design.
-- Conventions: uuid ids, timestamptz in UTC, status fields have CHECKs,
-- every FK has an explicit ON DELETE and an index.
-- =============================================================================

create extension if not exists pgcrypto;
create extension if not exists pg_trgm;
create extension if not exists vector;

create or replace function public.set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

-- -----------------------------------------------------------------------------
-- Workspace, people
-- -----------------------------------------------------------------------------

create table workspaces (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(name) between 1 and 80),
  allowed_email_domain text,                 -- e.g. 'rodrech.com': sign-up gate
  settings jsonb not null default '{}',      -- public_links_allowed, retention_days, default caps
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null unique,
  name text,
  avatar_url text,
  theme text not null default 'system' check (theme in ('system','light','dark')),
  locale text not null default 'en',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table memberships (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  role text not null default 'member' check (role in ('owner','admin','member')),
  limits jsonb not null default '{}',        -- per-user cap overrides, e.g. {"images_per_day": 100}
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (workspace_id, user_id)
);
create index on memberships (user_id);

-- Helper functions are SECURITY DEFINER so policies don't recurse through RLS.
create or replace function public.is_member(ws uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from memberships where workspace_id = ws and user_id = auth.uid())
$$;

create or replace function public.is_admin(ws uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from memberships
                 where workspace_id = ws and user_id = auth.uid() and role in ('owner','admin'))
$$;

create or replace function public.shares_workspace(other uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from memberships a join memberships b using (workspace_id)
                 where a.user_id = auth.uid() and b.user_id = other)
$$;

-- -----------------------------------------------------------------------------
-- Projects (S09 S10)
-- -----------------------------------------------------------------------------

create table projects (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  owner_id uuid not null references profiles(id) on delete cascade,
  name text not null check (length(name) between 1 and 120),
  instructions text not null default '' check (length(instructions) <= 20000),
  memory_mode text not null default 'default' check (memory_mode in ('default','project_only')),
  archived_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on projects (workspace_id);
create index on projects (owner_id, updated_at desc);

create table project_members (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  role text not null default 'editor' check (role in ('viewer','editor')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (project_id, user_id)
);
create index on project_members (user_id);

create or replace function public.can_view_project(p uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from projects where id = p and owner_id = auth.uid())
      or exists (select 1 from project_members where project_id = p and user_id = auth.uid())
$$;

create or replace function public.can_edit_project(p uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from projects where id = p and owner_id = auth.uid())
      or exists (select 1 from project_members
                 where project_id = p and user_id = auth.uid() and role = 'editor')
$$;

-- -----------------------------------------------------------------------------
-- Files / Library (S11). Bytes live in Storage bucket 'files' at
-- '{owner_id}/{file_id}/{name}'. Soft delete; a job purges after 30 days.
-- -----------------------------------------------------------------------------

create table files (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  owner_id uuid not null references profiles(id) on delete cascade,
  name text not null check (length(name) between 1 and 255),
  mime text not null,
  bytes bigint not null check (bytes > 0 and bytes <= 536870912),   -- 512 MB cap
  storage_path text not null unique,
  source text not null default 'upload'
    check (source in ('upload','generated','drive','agent','audio_transcript')),
  external_id text,                          -- e.g. Google Drive file id
  token_count integer check (token_count is null or token_count <= 2000000),
  status text not null default 'uploading'
    check (status in ('uploading','processing','ready','error')),
  error text,
  favorite boolean not null default false,
  is_temporary boolean not null default false,   -- uploaded in a temporary chat: never in Library
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on files (workspace_id);
create index on files (owner_id, created_at desc) where deleted_at is null and not is_temporary;
create index on files (deleted_at) where deleted_at is not null;
create index files_name_trgm on files using gin (name gin_trgm_ops);

-- -----------------------------------------------------------------------------
-- Assistants: custom presets, the GPT-style feature (S21 S22)
-- -----------------------------------------------------------------------------

create table assistants (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  owner_id uuid references profiles(id) on delete set null,   -- keeps team assistants if the author leaves
  name text not null check (length(name) between 1 and 80),
  description text not null default '',
  instructions text not null default '' check (length(instructions) <= 20000),
  starters text[] not null default '{}',
  recommended_model text,
  capabilities text[] not null default '{}'
    check (capabilities <@ array['web_search','image_generation','code','apps']::text[]),
  visibility text not null default 'private' check (visibility in ('private','workspace')),
  current_version integer not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on assistants (workspace_id, visibility);
create index on assistants (owner_id);

create table assistant_versions (
  id uuid primary key default gen_random_uuid(),
  assistant_id uuid not null references assistants(id) on delete cascade,
  version integer not null,
  snapshot jsonb not null,
  created_by uuid references profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (assistant_id, version)
);
create index on assistant_versions (created_by);

create table assistant_files (
  id uuid primary key default gen_random_uuid(),
  assistant_id uuid not null references assistants(id) on delete cascade,
  file_id uuid not null references files(id) on delete cascade,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (assistant_id, file_id)
);
create index on assistant_files (file_id);

-- -----------------------------------------------------------------------------
-- Conversations and messages (S03 S04 S07 S08 S33)
-- Messages form a tree: edit or regenerate adds a sibling under the same parent.
-- The visible thread is the path from current_leaf_id back to the root.
-- -----------------------------------------------------------------------------

create table conversations (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  project_id uuid references projects(id) on delete cascade,      -- deleting a project deletes its chats (UI confirms with a count)
  assistant_id uuid references assistants(id) on delete set null,
  title text not null default 'New chat' check (length(title) <= 200),
  model text not null,
  kind text not null default 'chat' check (kind in ('chat','research','agent','task_run')),
  is_temporary boolean not null default false,
  archived_at timestamptz,
  current_leaf_id uuid,                       -- FK added after messages
  last_message_at timestamptz not null default now(),
  search tsvector generated always as (to_tsvector('english', coalesce(title, ''))) stored,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on conversations (workspace_id);
create index conversations_sidebar on conversations (user_id, last_message_at desc)
  where archived_at is null and not is_temporary;
create index on conversations (user_id, archived_at) where archived_at is not null;
create index on conversations (project_id, last_message_at desc);
create index on conversations (assistant_id);
create index on conversations (created_at) where is_temporary;   -- 30-day purge
create index conversations_search on conversations using gin (search);

create table messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations(id) on delete cascade,
  parent_id uuid references messages(id) on delete cascade,
  user_id uuid references profiles(id) on delete set null,     -- author of user messages
  role text not null check (role in ('user','assistant','tool','system')),
  content jsonb not null default '[]',        -- blocks: text, image, file_ref, citation, tool_call, tool_result
  text text not null default '',              -- plain text copy for search and embeddings
  model text,
  status text not null default 'complete'
    check (status in ('streaming','complete','stopped','error')),
  error text,
  feedback smallint check (feedback in (-1, 1)),
  feedback_note text,
  usage jsonb,                                -- {"input_tokens":..,"output_tokens":..}
  search tsvector generated always as (to_tsvector('english', text)) stored,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_messages_have_author check (role <> 'user' or user_id is not null)
);
create index on messages (conversation_id, created_at);
create index on messages (parent_id);
create index on messages (user_id);
create index on messages (conversation_id) where status = 'streaming';   -- stuck-stream sweeper
create index messages_search on messages using gin (search);

alter table conversations
  add constraint conversations_current_leaf_fk
  foreign key (current_leaf_id) references messages(id) on delete set null;
create index on conversations (current_leaf_id);

create table message_files (
  id uuid primary key default gen_random_uuid(),
  message_id uuid not null references messages(id) on delete cascade,
  file_id uuid not null references files(id) on delete cascade,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (message_id, file_id)
);
create index on message_files (file_id);

create table project_files (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  file_id uuid not null references files(id) on delete cascade,
  added_by uuid references profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (project_id, file_id)
);
create index on project_files (file_id);
create index on project_files (added_by);

create or replace function public.can_view_conversation(c uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from conversations x
    where x.id = c
      and (x.user_id = auth.uid()
           or (x.project_id is not null and not x.is_temporary and can_view_project(x.project_id)))
  )
$$;

create or replace function public.can_view_file(f uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from files where id = f and owner_id = auth.uid())
      or exists (select 1 from project_files pf where pf.file_id = f and can_view_project(pf.project_id))
      or exists (select 1 from message_files mf join messages m on m.id = mf.message_id
                 where mf.file_id = f and can_view_conversation(m.conversation_id))
      or exists (select 1 from assistant_files af join assistants a on a.id = af.assistant_id
                 where af.file_id = f and a.visibility = 'workspace' and is_member(a.workspace_id))
$$;

-- -----------------------------------------------------------------------------
-- Personalization and memory (S24 S25)
-- -----------------------------------------------------------------------------

create table personalization (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references profiles(id) on delete cascade,
  about_you text not null default '' check (length(about_you) <= 3000),
  response_style text not null default '' check (length(response_style) <= 3000),
  personality text not null default 'default',
  memory_enabled boolean not null default true,
  reference_chat_history boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table memory_summaries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references profiles(id) on delete cascade,
  project_id uuid references projects(id) on delete cascade,   -- null = account-level memory
  body text not null default '',
  refreshed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique nulls not distinct (user_id, project_id)
);
create index on memory_summaries (project_id);

create table memory_suppressions (               -- "Don't mention this again"
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references profiles(id) on delete cascade,
  text text not null check (length(text) between 1 and 500),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on memory_suppressions (user_id);

-- -----------------------------------------------------------------------------
-- Space: pages with co-editing (S12). The live doc is a Yjs document in
-- Liveblocks; doc_snapshot is the persisted copy and text is for search.
-- -----------------------------------------------------------------------------

create table spaces (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  owner_id uuid not null references profiles(id) on delete cascade,
  name text not null check (length(name) between 1 and 120),
  is_personal boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on spaces (workspace_id);
create index on spaces (owner_id);
create unique index one_personal_space on spaces (owner_id) where is_personal;

create table pages (
  id uuid primary key default gen_random_uuid(),
  space_id uuid not null references spaces(id) on delete cascade,
  parent_page_id uuid references pages(id) on delete cascade,
  title text not null default 'Untitled' check (length(title) <= 300),
  doc_snapshot bytea,
  text text not null default '',
  position text not null default 'a0',        -- fractional index for sibling order
  created_by uuid references profiles(id) on delete set null,
  updated_by uuid references profiles(id) on delete set null,
  source_conversation_id uuid references conversations(id) on delete set null,
  search tsvector generated always as (to_tsvector('english', title || ' ' || text)) stored,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint not_own_parent check (parent_page_id is null or parent_page_id <> id)
);
create index on pages (space_id, parent_page_id, position);
create index on pages (parent_page_id);
create index on pages (created_by);
create index on pages (updated_by);
create index on pages (source_conversation_id);
create index pages_search on pages using gin (search);

create table page_access (
  id uuid primary key default gen_random_uuid(),
  space_id uuid references spaces(id) on delete cascade,
  page_id uuid references pages(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  level text not null default 'view' check (level in ('view','comment','edit')),
  granted_by uuid references profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (num_nonnulls(space_id, page_id) = 1)
);
create unique index on page_access (space_id, user_id) where space_id is not null;
create unique index on page_access (page_id, user_id) where page_id is not null;
create index on page_access (user_id);
create index on page_access (granted_by);

-- Access is inherited: a page is visible if the user owns its space, has access
-- to the space, or has access to the page or any ancestor page.
create or replace function public.page_access_level(p uuid) returns text
language sql stable security definer set search_path = public as $$
  with recursive chain as (
    select id, parent_page_id, space_id from pages where id = p
    union all
    select pg.id, pg.parent_page_id, pg.space_id from pages pg join chain c on pg.id = c.parent_page_id
  ), grants as (
    select 'edit'::text as level from chain c join spaces s on s.id = c.space_id
      where s.owner_id = auth.uid()
    union all
    select pa.level from page_access pa
      where pa.user_id = auth.uid()
        and (pa.page_id in (select id from chain)
             or pa.space_id in (select space_id from chain))
  )
  select case
    when bool_or(level = 'edit') then 'edit'
    when bool_or(level = 'comment') then 'comment'
    when bool_or(level = 'view') then 'view'
  end from grants
$$;

create table comments (
  id uuid primary key default gen_random_uuid(),
  page_id uuid not null references pages(id) on delete cascade,
  author_id uuid references profiles(id) on delete set null,
  parent_comment_id uuid references comments(id) on delete cascade,
  anchor jsonb,                               -- Yjs relative positions of the selection
  body text not null check (length(body) between 1 and 10000),
  resolved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on comments (page_id, created_at);
create index on comments (author_id);
create index on comments (parent_comment_id);

-- -----------------------------------------------------------------------------
-- Retrieval chunks for memory, file Q&A, search (pgvector)
-- Dimension must match the embedding model (1024 fits Voyage models).
-- -----------------------------------------------------------------------------

create table chunks (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  owner_id uuid not null references profiles(id) on delete cascade,
  file_id uuid references files(id) on delete cascade,
  message_id uuid references messages(id) on delete cascade,
  page_id uuid references pages(id) on delete cascade,
  ordinal integer not null default 0,
  content text not null,
  embedding vector(1024) not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (num_nonnulls(file_id, message_id, page_id) = 1)
);
create index on chunks (workspace_id);
create index on chunks (owner_id);
create index on chunks (file_id);
create index on chunks (message_id);
create index on chunks (page_id);
create index chunks_embedding on chunks using hnsw (embedding vector_cosine_ops);

-- -----------------------------------------------------------------------------
-- Apps / connectors (S19 S20). Catalog of providers lives in code.
-- OAuth tokens live in app_tokens: RLS on, no policies, so service role only.
-- -----------------------------------------------------------------------------

create table app_connections (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  provider text not null,                    -- 'google_drive','gmail','slack','shopify',...
  external_account_id text not null,
  external_account_label text,
  scopes text[] not null default '{}',
  permission_level text not null default 'important'
    check (permission_level in ('always_ask','any_changes','important','never_ask')),
  status text not null default 'active' check (status in ('active','expired','revoked')),
  last_synced_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, provider, external_account_id)
);
create index on app_connections (workspace_id);

create table app_tokens (
  id uuid primary key default gen_random_uuid(),
  connection_id uuid not null unique references app_connections(id) on delete cascade,
  access_token_enc bytea not null,           -- AES-GCM, key in server env
  refresh_token_enc bytea,
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on app_tokens (expires_at);

-- -----------------------------------------------------------------------------
-- Scheduled tasks (S18)
-- -----------------------------------------------------------------------------

create table scheduled_tasks (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  title text not null check (length(title) between 1 and 200),
  prompt text not null check (length(prompt) between 1 and 10000),
  kind text not null check (kind in ('once','recurring','monitor','event')),
  run_at timestamptz,                        -- kind = once
  rrule text,                                -- kind = recurring | monitor, RFC 5545, evaluated in timezone
  timezone text not null,                    -- IANA name, e.g. 'America/New_York'
  next_run_at timestamptz,
  trigger jsonb,                             -- kind = event: {"event":"gmail.new_message","condition":{...}}
  connection_id uuid references app_connections(id) on delete set null,
  model text,
  notify text[] not null default '{push}' check (notify <@ array['push','email']::text[]),
  status text not null default 'active' check (status in ('active','paused','completed')),
  paused_reason text,
  last_run_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint schedule_matches_kind check (
       (kind = 'once' and run_at is not null)
    or (kind in ('recurring','monitor') and rrule is not null)
    or (kind = 'event' and trigger is not null and connection_id is not null))
);
create index on scheduled_tasks (workspace_id);
create index on scheduled_tasks (user_id, status);
create index on scheduled_tasks (next_run_at) where status = 'active';
create index on scheduled_tasks (connection_id);

-- Active-task cap (15 by default, overridable in memberships.limits).
-- Takes a per-user advisory lock so two concurrent inserts can't both pass.
create or replace function public.enforce_task_cap() returns trigger
language plpgsql security definer set search_path = public as $$
declare cap integer; active_count integer;
begin
  if new.status <> 'active' or (tg_op = 'UPDATE' and old.status = 'active') then
    return new;
  end if;
  perform pg_advisory_xact_lock(hashtext('task_cap:' || new.user_id::text));
  select coalesce((m.limits->>'active_tasks')::int, 15) into cap
    from memberships m where m.user_id = new.user_id and m.workspace_id = new.workspace_id;
  select count(*) into active_count from scheduled_tasks
    where user_id = new.user_id and status = 'active' and id <> new.id;
  if active_count >= coalesce(cap, 15) then
    raise exception 'active task limit reached (%)', coalesce(cap, 15) using errcode = 'P0001';
  end if;
  return new;
end $$;
create trigger scheduled_tasks_cap before insert or update of status on scheduled_tasks
  for each row execute function enforce_task_cap();

create table task_runs (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references scheduled_tasks(id) on delete cascade,
  conversation_id uuid references conversations(id) on delete set null,
  scheduled_for timestamptz not null,
  status text not null default 'running'
    check (status in ('running','succeeded','failed','awaiting_approval','skipped')),
  summary text,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (task_id, scheduled_for)            -- idempotency: a tick can't run twice
);
create index on task_runs (conversation_id);

-- -----------------------------------------------------------------------------
-- Shared links (S30)
-- -----------------------------------------------------------------------------

create table shared_links (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references profiles(id) on delete cascade,
  conversation_id uuid references conversations(id) on delete cascade,
  task_id uuid references scheduled_tasks(id) on delete cascade,
  slug text not null unique default encode(gen_random_bytes(16), 'hex'),
  snapshot jsonb not null,                   -- frozen thread at share time
  snapshot_message_id uuid references messages(id) on delete set null,
  visibility text not null default 'workspace' check (visibility in ('workspace','public')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (num_nonnulls(conversation_id, task_id) = 1)
);
create index on shared_links (owner_id, created_at desc);
create unique index on shared_links (conversation_id) where conversation_id is not null;
create unique index on shared_links (task_id) where task_id is not null;
create index on shared_links (snapshot_message_id);

-- -----------------------------------------------------------------------------
-- Images (S13 S14)
-- -----------------------------------------------------------------------------

create table image_generations (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  conversation_id uuid references conversations(id) on delete set null,
  message_id uuid references messages(id) on delete set null,
  prompt text not null check (length(prompt) between 1 and 8000),
  aspect_ratio text not null default '1:1'
    check (aspect_ratio in ('1:1','2:3','3:2','4:5','5:4','9:16','16:9')),
  template_id text,
  input_file_id uuid references files(id) on delete set null,     -- image being edited
  mask_file_id uuid references files(id) on delete set null,      -- region selection
  output_file_id uuid references files(id) on delete set null,
  provider text not null,
  status text not null default 'queued'
    check (status in ('queued','running','succeeded','failed','refused')),
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on image_generations (workspace_id);
create index on image_generations (user_id, created_at desc);
create index on image_generations (conversation_id);
create index on image_generations (message_id);
create index on image_generations (input_file_id);
create index on image_generations (mask_file_id);
create index on image_generations (output_file_id);

-- -----------------------------------------------------------------------------
-- Deep research (S15) and Work agent runs (S16), approvals
-- -----------------------------------------------------------------------------

create table research_jobs (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  question text not null,
  plan jsonb,                                -- user-editable before start
  sources jsonb not null default '{"web": true}',  -- {web, file_ids[], connection_ids[], sites[], sites_mode}
  status text not null default 'clarifying'
    check (status in ('clarifying','planned','running','interrupted','done','failed','cancelled')),
  report_file_id uuid references files(id) on delete set null,
  citations jsonb not null default '[]',
  job_run_id text,                           -- Inngest run id
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on research_jobs (conversation_id);
create index on research_jobs (user_id, created_at desc);
create index on research_jobs (report_file_id);

create table agent_runs (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  goal text not null,
  plan jsonb,
  status text not null default 'planning'
    check (status in ('planning','running','awaiting_approval','paused','failed','done','cancelled')),
  credits_used integer not null default 0 check (credits_used >= 0),
  job_run_id text,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on agent_runs (conversation_id);
create index on agent_runs (user_id, created_at desc);
create index on agent_runs (status) where status in ('running','awaiting_approval');

create table agent_steps (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references agent_runs(id) on delete cascade,
  ordinal integer not null,
  kind text not null check (kind in ('think','search','app_action','code','browse','write_file')),
  input jsonb not null default '{}',
  output jsonb,
  output_file_id uuid references files(id) on delete set null,
  status text not null default 'pending'
    check (status in ('pending','running','done','failed','skipped')),
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (run_id, ordinal)
);
create index on agent_steps (output_file_id);

create table action_approvals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references profiles(id) on delete cascade,
  connection_id uuid not null references app_connections(id) on delete cascade,
  message_id uuid references messages(id) on delete cascade,
  run_id uuid references agent_runs(id) on delete cascade,
  task_run_id uuid references task_runs(id) on delete cascade,
  action text not null,                      -- e.g. 'slack.post_message'
  importance text not null check (importance in ('read','change','important')),
  payload_preview jsonb not null,
  decision text not null default 'pending'
    check (decision in ('pending','approved','always','denied','expired')),
  decided_at timestamptz,
  expires_at timestamptz not null default now() + interval '24 hours',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (num_nonnulls(message_id, run_id, task_run_id) = 1),
  check ((decision = 'pending') = (decided_at is null) or decision = 'expired')
);
create index on action_approvals (user_id) where decision = 'pending';
create index on action_approvals (connection_id);
create index on action_approvals (message_id);
create index on action_approvals (run_id);
create index on action_approvals (task_run_id);

-- -----------------------------------------------------------------------------
-- Sites (S17): static bundles served from a separate origin
-- -----------------------------------------------------------------------------

create table sites (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  owner_id uuid not null references profiles(id) on delete cascade,
  name text not null check (length(name) between 1 and 120),
  slug text not null unique check (slug ~ '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$'),
  visibility text not null default 'private' check (visibility in ('private','workspace','public')),
  current_version_id uuid,                   -- FK added below
  published_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on sites (workspace_id);
create index on sites (owner_id);

create table site_versions (
  id uuid primary key default gen_random_uuid(),
  site_id uuid not null references sites(id) on delete cascade,
  version integer not null,
  storage_prefix text not null,
  created_by_run_id uuid references agent_runs(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (site_id, version)
);
create index on site_versions (created_by_run_id);

alter table sites add constraint sites_current_version_fk
  foreign key (current_version_id) references site_versions(id) on delete set null;
create index on sites (current_version_id);

-- -----------------------------------------------------------------------------
-- Notifications, usage, exports, security log
-- -----------------------------------------------------------------------------

create table push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references profiles(id) on delete cascade,
  endpoint text not null unique,
  p256dh text not null,
  auth text not null,
  user_agent text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on push_subscriptions (user_id);

create table usage_events (                      -- append-only, service role writes
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  metric text not null
    check (metric in ('message','image','research','agent_credit','voice_second','tts_char')),
  quantity integer not null default 1 check (quantity > 0),
  model text,
  input_tokens integer,
  output_tokens integer,
  cost_micro_usd bigint,                     -- provider cost in millionths of a dollar, for reporting
  idempotency_key text unique,               -- e.g. message id: never double-count a retry
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on usage_events (user_id, metric, created_at desc);
create index on usage_events (workspace_id, created_at desc);

create table data_exports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references profiles(id) on delete cascade,
  status text not null default 'queued'
    check (status in ('queued','running','ready','failed','expired')),
  storage_path text,
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on data_exports (user_id, created_at desc);

create table security_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references profiles(id) on delete cascade,
  kind text not null check (kind in ('sign_in','sign_out','mfa_enabled','mfa_disabled',
                                     'passkey_added','passkey_removed','session_revoked','export_requested')),
  ip inet,
  user_agent text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on security_events (user_id, created_at desc);

-- -----------------------------------------------------------------------------
-- updated_at triggers on every table that has the column
-- -----------------------------------------------------------------------------

do $$
declare t text;
begin
  for t in
    select c.table_name from information_schema.columns c
    join information_schema.tables tb on tb.table_name = c.table_name and tb.table_schema = c.table_schema
    where c.table_schema = 'public' and c.column_name = 'updated_at' and tb.table_type = 'BASE TABLE'
  loop
    execute format('create trigger %I before update on %I for each row execute function set_updated_at()',
                   t || '_updated_at', t);
  end loop;
end $$;

-- -----------------------------------------------------------------------------
-- Row level security
-- -----------------------------------------------------------------------------

do $$
declare t text;
begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table %I enable row level security', t);
  end loop;
end $$;

-- workspaces / people
create policy ws_read   on workspaces for select to authenticated using (is_member(id));
create policy ws_admin  on workspaces for update to authenticated using (is_admin(id)) with check (is_admin(id));

create policy prof_read on profiles for select to authenticated using (id = auth.uid() or shares_workspace(id));
create policy prof_self on profiles for update to authenticated using (id = auth.uid()) with check (id = auth.uid());

create policy mem_read  on memberships for select to authenticated using (is_member(workspace_id));
create policy mem_admin on memberships for all to authenticated
  using (is_admin(workspace_id)) with check (is_admin(workspace_id));

-- projects
create policy proj_read   on projects for select to authenticated using (can_view_project(id));
create policy proj_insert on projects for insert to authenticated
  with check (owner_id = auth.uid() and is_member(workspace_id));
create policy proj_update on projects for update to authenticated
  using (can_edit_project(id)) with check (can_edit_project(id));
create policy proj_delete on projects for delete to authenticated using (owner_id = auth.uid());

create policy pm_read  on project_members for select to authenticated using (can_view_project(project_id));
create policy pm_owner on project_members for all to authenticated
  using (exists (select 1 from projects p where p.id = project_id and p.owner_id = auth.uid()))
  with check (exists (select 1 from projects p where p.id = project_id and p.owner_id = auth.uid())
              and shares_workspace(user_id));

-- files (insert happens server-side after upload; users manage their own)
create policy files_read   on files for select to authenticated using ((deleted_at is null and can_view_file(id)) or owner_id = auth.uid());
create policy files_update on files for update to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy files_delete on files for delete to authenticated using (owner_id = auth.uid());

create policy pf_read  on project_files for select to authenticated using (can_view_project(project_id));
create policy pf_write on project_files for insert to authenticated
  with check (can_edit_project(project_id)
              and exists (select 1 from files f where f.id = file_id and f.owner_id = auth.uid()));
create policy pf_delete on project_files for delete to authenticated using (can_edit_project(project_id));

-- assistants
create policy asst_read on assistants for select to authenticated
  using (owner_id = auth.uid() or (visibility = 'workspace' and is_member(workspace_id)));
create policy asst_insert on assistants for insert to authenticated
  with check (owner_id = auth.uid() and is_member(workspace_id));
create policy asst_update on assistants for update to authenticated
  using (owner_id = auth.uid() or is_admin(workspace_id))
  with check (owner_id = auth.uid() or is_admin(workspace_id));
create policy asst_delete on assistants for delete to authenticated
  using (owner_id = auth.uid() or is_admin(workspace_id));

create policy astv_read on assistant_versions for select to authenticated
  using (exists (select 1 from assistants a where a.id = assistant_id
                 and (a.owner_id = auth.uid() or is_admin(a.workspace_id))));
create policy astf_read on assistant_files for select to authenticated
  using (exists (select 1 from assistants a where a.id = assistant_id
                 and (a.owner_id = auth.uid() or (a.visibility = 'workspace' and is_member(a.workspace_id)))));

-- conversations / messages (messages are written by the server)
create policy conv_read   on conversations for select to authenticated using (can_view_conversation(id));
create policy conv_insert on conversations for insert to authenticated
  with check (user_id = auth.uid() and is_member(workspace_id)
              and (project_id is null or can_edit_project(project_id)));
create policy conv_update on conversations for update to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid() and (project_id is null or can_edit_project(project_id)));
create policy conv_delete on conversations for delete to authenticated using (user_id = auth.uid());

create policy msg_read on messages for select to authenticated using (can_view_conversation(conversation_id));
create policy mf_read  on message_files for select to authenticated
  using (exists (select 1 from messages m where m.id = message_id and can_view_conversation(m.conversation_id)));

-- personalization / memory: owner only
create policy pers_own on personalization for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy msum_own on memory_summaries for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy msup_own on memory_suppressions for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

-- space / pages / comments
create policy space_read on spaces for select to authenticated
  using (owner_id = auth.uid()
         or exists (select 1 from page_access pa where pa.space_id = id and pa.user_id = auth.uid()));
create policy space_insert on spaces for insert to authenticated
  with check (owner_id = auth.uid() and is_member(workspace_id));
create policy space_owner on spaces for update to authenticated
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy space_delete on spaces for delete to authenticated using (owner_id = auth.uid() and not is_personal);

create policy page_read   on pages for select to authenticated using (page_access_level(id) is not null);
create policy page_insert on pages for insert to authenticated
  with check (
    (parent_page_id is null and exists (select 1 from spaces s where s.id = space_id
       and (s.owner_id = auth.uid()
            or exists (select 1 from page_access pa where pa.space_id = s.id
                       and pa.user_id = auth.uid() and pa.level = 'edit'))))
    or (parent_page_id is not null and page_access_level(parent_page_id) = 'edit'));
create policy page_update on pages for update to authenticated
  using (page_access_level(id) = 'edit') with check (page_access_level(id) = 'edit');
create policy page_delete on pages for delete to authenticated using (page_access_level(id) = 'edit');

create policy pa_read on page_access for select to authenticated
  using (user_id = auth.uid()
         or (page_id is not null and page_access_level(page_id) = 'edit')
         or (space_id is not null and exists (select 1 from spaces s where s.id = space_id and s.owner_id = auth.uid())));
create policy pa_grant on page_access for insert to authenticated
  with check (granted_by = auth.uid() and shares_workspace(user_id)
              and ((page_id is not null and page_access_level(page_id) = 'edit')
                   or (space_id is not null and exists (select 1 from spaces s
                       where s.id = space_id and s.owner_id = auth.uid()))));
create policy pa_revoke on page_access for delete to authenticated
  using ((page_id is not null and page_access_level(page_id) = 'edit')
         or (space_id is not null and exists (select 1 from spaces s where s.id = space_id and s.owner_id = auth.uid())));

create policy cmt_read on comments for select to authenticated using (page_access_level(page_id) is not null);
create policy cmt_insert on comments for insert to authenticated
  with check (author_id = auth.uid() and page_access_level(page_id) in ('comment','edit'));
create policy cmt_update on comments for update to authenticated
  using (author_id = auth.uid() or page_access_level(page_id) = 'edit')
  with check (author_id = auth.uid() or page_access_level(page_id) = 'edit');
create policy cmt_delete on comments for delete to authenticated using (author_id = auth.uid());

-- chunks: owner only (shared-project retrieval runs server-side with explicit checks)
create policy chunks_own on chunks for select to authenticated using (owner_id = auth.uid());

-- apps (tokens: no policies = service role only)
create policy conn_own_read on app_connections for select to authenticated using (user_id = auth.uid());
create policy conn_own_update on app_connections for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy conn_own_delete on app_connections for delete to authenticated using (user_id = auth.uid());

-- tasks
create policy task_own on scheduled_tasks for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid() and is_member(workspace_id));
create policy trun_read on task_runs for select to authenticated
  using (exists (select 1 from scheduled_tasks t where t.id = task_id and t.user_id = auth.uid()));

-- shared links: owner manages; viewing a link goes through a server route
-- that reads by slug with the service role and checks visibility.
create policy link_own on shared_links for all to authenticated
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid()
              and (conversation_id is null or exists (select 1 from conversations c
                     where c.id = conversation_id and c.user_id = auth.uid() and not c.is_temporary))
              and (task_id is null or exists (select 1 from scheduled_tasks t
                     where t.id = task_id and t.user_id = auth.uid())));

-- images, research, agent: read own; server writes
create policy img_read on image_generations for select to authenticated using (user_id = auth.uid());
create policy rj_read  on research_jobs for select to authenticated using (user_id = auth.uid());
create policy ar_read  on agent_runs for select to authenticated using (user_id = auth.uid());
create policy as_read  on agent_steps for select to authenticated
  using (exists (select 1 from agent_runs r where r.id = run_id and r.user_id = auth.uid()));
create policy appr_read on action_approvals for select to authenticated using (user_id = auth.uid());

-- sites
create policy site_read on sites for select to authenticated
  using (owner_id = auth.uid() or (visibility in ('workspace','public') and is_member(workspace_id)));
create policy site_update on sites for update to authenticated
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy site_delete on sites for delete to authenticated using (owner_id = auth.uid());
create policy sv_read on site_versions for select to authenticated
  using (exists (select 1 from sites s where s.id = site_id and s.owner_id = auth.uid()));

-- notifications / usage / exports / security
create policy push_own on push_subscriptions for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy usage_read on usage_events for select to authenticated
  using (user_id = auth.uid() or is_admin(workspace_id));
create policy export_read on data_exports for select to authenticated using (user_id = auth.uid());
create policy sec_read on security_events for select to authenticated using (user_id = auth.uid());

-- -----------------------------------------------------------------------------
-- Storage: bucket 'files', private. Path: '{owner_id}/{file_id}/{filename}'.
-- Uploads use signed upload URLs issued by the server; reads use signed URLs
-- after can_view_file(). These policies are a backstop for direct access.
-- -----------------------------------------------------------------------------

create policy files_bucket_owner_read on storage.objects for select to authenticated
  using (bucket_id = 'files' and (storage.foldername(name))[1] = auth.uid()::text);
create policy files_bucket_owner_write on storage.objects for insert to authenticated
  with check (bucket_id = 'files' and (storage.foldername(name))[1] = auth.uid()::text);
create policy files_bucket_owner_delete on storage.objects for delete to authenticated
  using (bucket_id = 'files' and (storage.foldername(name))[1] = auth.uid()::text);
