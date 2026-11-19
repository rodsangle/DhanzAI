-- 0010: Dhanz GPT on the DHANZ AI server.
--  * Sign-up mode. 'domain' (the default, unchanged): only emails on a workspace's allowed domain join it.
--    'personal': every new account gets its own private workspace, so public accounts never see each
--    other in share lists. The deploy script sets 'personal'.
--  * dhanz_sessions: for each Dhanz GPT session (a row in auth.sessions), the DHANZ AI account tokens,
--    encrypted with APP_TOKEN_KEY, and when they were last checked with the DHANZ API. Deleting the
--    session deletes them.

create table platform_settings (
  key text primary key,
  value text not null,
  updated_at timestamptz not null default now()
);
insert into platform_settings (key, value) values ('signup_mode', 'domain') on conflict (key) do nothing;
alter table platform_settings enable row level security; -- no policies: server-side only

create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
declare ws uuid; is_first boolean; mode text;
begin
  select id into ws from workspaces
   where allowed_email_domain is not null
     and lower(split_part(new.email, '@', 2)) = lower(allowed_email_domain)
   order by created_at limit 1;
  if ws is null then
    select value into mode from platform_settings where key = 'signup_mode';
    if coalesce(mode, 'domain') <> 'personal' then
      raise exception 'signup_domain_not_allowed' using errcode = 'P0001',
        hint = 'This email can''t join a workspace here.';
    end if;
    insert into workspaces (name, settings)
    values (left(coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)) || '''s workspace', 80),
            jsonb_build_object('timezone', coalesce(new.raw_user_meta_data->>'timezone', 'America/New_York'),
                               'public_links_allowed', true))
    returning id into ws;
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

create table dhanz_sessions (
  session_id uuid primary key references auth.sessions(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  access_token bytea not null,          -- sealed (AES-256-GCM)
  refresh_token bytea not null,         -- sealed; DHANZ rotates it on every refresh
  access_expires_at timestamptz not null,
  checked_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);
create index on dhanz_sessions (user_id);
alter table dhanz_sessions enable row level security; -- no policies: server-side only
