-- 0007: scheduled-task results show as unread until the person opens Scheduled.
alter table task_runs add column seen_at timestamptz;
create index task_runs_unseen on task_runs (task_id) where seen_at is null and status in ('succeeded', 'failed');
