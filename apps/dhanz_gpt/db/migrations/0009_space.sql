-- 0009: Space (S12), built on the tables 0001 created.
-- Changes from the 0001 plan:
--   * Pages are stored as editor JSON (`doc`) plus plain text, instead of a Liveblocks Yjs snapshot. Live CRDT
--     co-editing can come back later by adding Liveblocks; until then `version` goes up on every content save and
--     a save based on an older version is refused, so two people can't silently overwrite each other.
--   * A space can be opened to everyone in the workspace (`everyone_level`).
--   * Access on a space now counts for everyone with a grant on it, not only the owner (e.g. grants can be
--     read by anyone who can see the space; editors of a space can share it).
--   * Comments keep the quoted passage and who resolved them. Presence shows who has a page open.

alter table spaces add column everyone_level text check (everyone_level in ('view','comment','edit'));

alter table pages alter column title set default '';
alter table pages add column doc jsonb not null default '{"type":"doc","content":[]}';
alter table pages add column version integer not null default 1;
alter table pages add constraint pages_text_size check (length(text) <= 500000);
alter table pages drop column doc_snapshot;

alter table comments drop column anchor;
alter table comments add column quote text check (length(quote) <= 1000);
alter table comments add column resolved_by uuid references profiles(id) on delete set null;
create index on comments (resolved_by);

create table page_presence (
  page_id uuid not null references pages(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  editing boolean not null default false,
  seen_at timestamptz not null default now(),
  primary key (page_id, user_id)
);
create index on page_presence (user_id);
alter table page_presence enable row level security;

-- A subpage must live in its parent's space.
create or replace function public.page_parent_same_space() returns trigger language plpgsql as $$
begin
  if new.parent_page_id is not null and not exists (
    select 1 from pages where id = new.parent_page_id and space_id = new.space_id) then
    raise exception 'parent page is in another space';
  end if;
  return new;
end $$;
create trigger pages_parent_same_space before insert or update of parent_page_id, space_id on pages
  for each row execute function page_parent_same_space();

-- Content saves bump the version; title-only saves and moves don't (they can't lose anyone's typing).
create or replace function public.pages_bump_version() returns trigger language plpgsql as $$
begin
  if new.doc is distinct from old.doc then new.version := old.version + 1; end if;
  return new;
end $$;
create trigger pages_bump_version before update on pages for each row execute function pages_bump_version();

-- The strongest level the current user has on a space: the owner edits, then grants, then the everyone level.
create or replace function public.space_access_level(s uuid) returns text
language sql stable security definer set search_path = public as $$
  with grants as (
    select 'edit'::text as level from spaces where id = s and owner_id = auth.uid()
    union all
    select level from page_access where space_id = s and user_id = auth.uid()
    union all
    select everyone_level from spaces where id = s and everyone_level is not null and is_member(workspace_id)
  )
  select case when bool_or(level = 'edit') then 'edit' when bool_or(level = 'comment') then 'comment'
              when bool_or(level = 'view') then 'view' end from grants
$$;

-- A page's level: the best of its space's level and any grant on the page or an ancestor (inherited down).
create or replace function public.page_access_level(p uuid) returns text
language sql stable security definer set search_path = public as $$
  with recursive chain as (
    select id, parent_page_id, space_id from pages where id = p
    union all
    select pg.id, pg.parent_page_id, pg.space_id from pages pg join chain c on pg.id = c.parent_page_id
  ), grants as (
    select space_access_level(sp.space_id) as level from pages sp where sp.id = p
    union all
    select pa.level from page_access pa where pa.user_id = auth.uid() and pa.page_id in (select id from chain)
  )
  select case when bool_or(level = 'edit') then 'edit' when bool_or(level = 'comment') then 'comment'
              when bool_or(level = 'view') then 'view' end from grants
$$;
grant execute on function public.space_access_level(uuid), public.page_access_level(uuid) to authenticated;

-- Policies, replaced.
-- Read policies check the row's own columns (see 0003): a policy that looks the row up again by id can't see a
-- row the same statement just inserted, which breaks INSERT ... RETURNING.
create or replace function public.has_page_grant_in_space(s uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from page_access pa join pages pg on pg.id = pa.page_id where pg.space_id = s and pa.user_id = auth.uid())
$$;
grant execute on function public.has_page_grant_in_space(uuid) to authenticated;

drop policy space_read on spaces;
drop policy space_owner on spaces;
create policy space_read on spaces for select to authenticated using (
  owner_id = auth.uid()
  or (everyone_level is not null and is_member(workspace_id))
  or has_space_grant(id)
  or has_page_grant_in_space(id));
create policy space_owner on spaces for update to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());

drop policy page_insert on pages;
create policy page_insert on pages for insert to authenticated with check (
  created_by = auth.uid() and (
    (parent_page_id is null and space_access_level(space_id) = 'edit')
    or (parent_page_id is not null and page_access_level(parent_page_id) = 'edit')));

drop policy pa_read on page_access;
drop policy pa_grant on page_access;
drop policy pa_revoke on page_access;
create policy pa_read on page_access for select to authenticated using (
  user_id = auth.uid()
  or (space_id is not null and space_access_level(space_id) is not null)
  or (page_id is not null and page_access_level(page_id) is not null));
create policy pa_grant on page_access for insert to authenticated with check (
  granted_by = auth.uid() and shares_workspace(user_id)
  and ((space_id is not null and space_access_level(space_id) = 'edit')
       or (page_id is not null and page_access_level(page_id) = 'edit')));
create policy pa_change on page_access for update to authenticated
  using ((space_id is not null and space_access_level(space_id) = 'edit') or (page_id is not null and page_access_level(page_id) = 'edit'))
  with check (granted_by = auth.uid()
    and ((space_id is not null and space_access_level(space_id) = 'edit') or (page_id is not null and page_access_level(page_id) = 'edit')));
create policy pa_revoke on page_access for delete to authenticated using (
  (space_id is not null and space_access_level(space_id) = 'edit')
  or (page_id is not null and page_access_level(page_id) = 'edit'));

drop policy cmt_delete on comments;
create policy cmt_delete on comments for delete to authenticated
  using (author_id = auth.uid() or page_access_level(page_id) = 'edit');

create policy pp_read on page_presence for select to authenticated using (page_access_level(page_id) is not null);
create policy pp_write on page_presence for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid() and page_access_level(page_id) is not null);
