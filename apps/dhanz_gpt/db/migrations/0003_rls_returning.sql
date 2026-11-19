-- =============================================================================
-- 0003: read policies that work for INSERT ... RETURNING.
-- A row returned by INSERT/UPDATE must pass the table's SELECT policy. Policies that looked the row up
-- again by id (can_view_conversation(id), can_view_project(id), page_access_level(id)) can't see a row
-- inserted by the same statement, so creating a chat or project failed. These versions check the row's
-- own columns, and use SECURITY DEFINER helpers that only read membership tables (no policy recursion).
-- =============================================================================

create or replace function public.is_project_member(p uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from project_members where project_id = p and user_id = auth.uid())
$$;

create or replace function public.has_space_grant(s uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from page_access where space_id = s and user_id = auth.uid())
$$;

create or replace function public.owns_space(s uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from spaces where id = s and owner_id = auth.uid())
$$;

drop policy if exists conv_read on conversations;
create policy conv_read on conversations for select to authenticated
  using (user_id = auth.uid()
         or (project_id is not null and not is_temporary and can_view_project(project_id)));

drop policy if exists proj_read on projects;
create policy proj_read on projects for select to authenticated
  using (owner_id = auth.uid() or is_project_member(id));

drop policy if exists space_read on spaces;
create policy space_read on spaces for select to authenticated
  using (owner_id = auth.uid() or has_space_grant(id));

drop policy if exists page_read on pages;
create policy page_read on pages for select to authenticated
  using (owns_space(space_id) or created_by = auth.uid() or page_access_level(id) is not null);
