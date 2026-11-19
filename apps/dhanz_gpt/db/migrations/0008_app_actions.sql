-- 0008: app actions in chat. An approval pauses an answer; what's needed to resume it is kept here.
alter table action_approvals
  add column tool_use_id text,
  add column tool_name text,
  add column state jsonb,                 -- the answer's tool steps so far, to continue after the decision
  add column result_summary text;
-- "Always allow" for one action on one connection.
alter table app_connections add column always_allowed text[] not null default '{}';
