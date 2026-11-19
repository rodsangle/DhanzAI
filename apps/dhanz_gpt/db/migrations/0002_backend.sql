-- =============================================================================
-- 0002: what the live backend needs beyond the planned schema.
-- =============================================================================

-- Stop button across server instances: the generator polls this flag.
alter table messages add column stop_requested boolean not null default false;

-- Release 1 reads plain-text files and PDFs directly; vector chunks come with memory.
alter table files add column extracted_text text;

-- Daily usage caps reset at the workspace's local midnight.
update workspaces set settings = settings || '{"timezone":"America/New_York"}'::jsonb
  where not settings ? 'timezone';

-- Fast "messages in the last minute" rate-limit check.
create index messages_user_recent on messages (user_id, created_at desc) where role = 'user';
create index files_owner_recent on files (owner_id, created_at desc);

-- -----------------------------------------------------------------------------
-- New sign-ups: only emails on a workspace's allowed domain may join.
-- Runs inside Supabase Auth's insert into auth.users, so a refused domain
-- means no account is created at all.
-- -----------------------------------------------------------------------------
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
declare ws uuid; is_first boolean;
begin
  select id into ws from workspaces
   where allowed_email_domain is not null
     and lower(split_part(new.email, '@', 2)) = lower(allowed_email_domain)
   order by created_at limit 1;
  if ws is null then
    raise exception 'signup_domain_not_allowed' using errcode = 'P0001',
      hint = 'Only RODRECH team accounts can sign in.';
  end if;

  insert into profiles (id, email, name, avatar_url)
  values (new.id, new.email,
          coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name', split_part(new.email, '@', 1)),
          new.raw_user_meta_data->>'avatar_url')
  on conflict (id) do nothing;

  select not exists (select 1 from memberships where workspace_id = ws) into is_first;
  insert into memberships (workspace_id, user_id, role)
  values (ws, new.id, case when is_first then 'owner' else 'member' end)
  on conflict (workspace_id, user_id) do nothing;

  insert into spaces (workspace_id, owner_id, name, is_personal)
  values (ws, new.id, 'My pages', true);
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- Keep the profile email in step if someone changes it in Google.
create or replace function public.handle_user_email_change() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  update profiles set email = new.email where id = new.id;
  return new;
end $$;
drop trigger if exists on_auth_user_email_changed on auth.users;
create trigger on_auth_user_email_changed after update of email on auth.users
  for each row when (old.email is distinct from new.email) execute function public.handle_user_email_change();

-- -----------------------------------------------------------------------------
-- Storage bucket: private, 512 MB cap. Downloads go through signed URLs on the
-- Supabase storage domain, a separate origin from the app.
-- -----------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit)
values ('files', 'files', false, 536870912)
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit;
