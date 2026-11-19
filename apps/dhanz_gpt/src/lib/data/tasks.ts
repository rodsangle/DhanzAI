import "server-only";
import { asService, asUser } from "@/lib/server/db";
import { describe, fromStored, isValidZone, nextRun, toStored, validate, type Schedule } from "@/lib/schedule";
import { HttpError } from "./errors";
import { MODELS } from "./types";

/**
 * Scheduled tasks (S18). Each person's own (RLS task_own). The cron sweep runs whatever is due:
 * each run is a new chat, recorded in task_runs (one row per task and scheduled time, so a tick
 * can't run twice), and shows as unread until the person opens Scheduled.
 */

export type Notify = "push" | "email";
export type TaskInput = { title: string; prompt: string; schedule: Schedule; timezone: string; notify: Notify[]; model?: string | null };

export interface TaskRunItem {
  id: string;
  status: "running" | "succeeded" | "failed" | "awaiting_approval" | "skipped";
  scheduled_for: string;
  finished_at: string | null;
  conversation_id: string | null;
  summary: string | null;
  seen: boolean;
}

export interface TaskItem {
  id: string;
  title: string;
  prompt: string;
  schedule: Schedule;
  schedule_text: string;
  timezone: string;
  notify: Notify[];
  model: string | null;
  status: "active" | "paused" | "completed";
  next_run_at: string | null;
  last_run_at: string | null;
  runs: TaskRunItem[];
}

const LIMITS = { title: 200, prompt: 10000 };

function clean(input: TaskInput) {
  const title = input.title.trim();
  const prompt = input.prompt.trim();
  if (!title) throw new HttpError(400, "Give the task a name.");
  if (title.length > LIMITS.title) throw new HttpError(400, "Keep the name under 200 characters.");
  if (!prompt) throw new HttpError(400, "Say what the assistant should do each time.");
  if (prompt.length > LIMITS.prompt) throw new HttpError(400, "The instructions are too long.");
  if (!isValidZone(input.timezone)) throw new HttpError(400, "Pick a time zone.");
  const bad = validate(input.schedule);
  if (bad) throw new HttpError(400, bad);
  const stored = toStored(input.schedule, input.timezone);
  const next = nextRun(input.schedule, input.timezone);
  if (!next) throw new HttpError(400, "That time has already passed. Pick a time in the future.");
  const notify = [...new Set(input.notify.filter((n) => n === "push" || n === "email"))];
  const model = input.model && MODELS.some((m) => m.id === input.model) ? input.model : null;
  return { title, prompt, stored, next, notify, model, timezone: input.timezone };
}

/** The active-task cap is a database trigger; turn its error into a sentence. */
function capError(e: unknown): never {
  if (e instanceof HttpError && /active task limit/i.test(e.message)) {
    const n = /\((\d+)\)/.exec(e.message)?.[1] ?? "15";
    throw new HttpError(409, `You can have ${n} active tasks. Pause or delete one first.`);
  }
  throw e;
}

type Row = {
  id: string; title: string; prompt: string; kind: string; run_at: string | null; rrule: string | null; timezone: string;
  notify: Notify[]; model: string | null; status: TaskItem["status"]; next_run_at: string | null; last_run_at: string | null;
};

function toItem(r: Row, runs: (TaskRunItem & { task_id: string })[]): TaskItem {
  const schedule = fromStored(r);
  return {
    id: r.id, title: r.title, prompt: r.prompt, schedule, schedule_text: describe(schedule), timezone: r.timezone,
    notify: r.notify, model: r.model, status: r.status, next_run_at: r.status === "active" ? r.next_run_at : null, last_run_at: r.last_run_at,
    runs: runs.filter((x) => x.task_id === r.id).map(({ task_id: _t, ...x }) => (void _t, x)),
  };
}

export async function listTasks(userId: string): Promise<TaskItem[]> {
  return asUser(userId, async (q) => {
    const rows = await q<Row[]>`
      select id, title, prompt, kind, run_at, rrule, timezone, notify, model, status, next_run_at, last_run_at
      from scheduled_tasks where user_id = ${userId} order by (status = 'active') desc, next_run_at nulls last, created_at desc`;
    const runs = rows.length
      ? await q<(TaskRunItem & { task_id: string })[]>`
          select * from (
            select r.id, r.task_id, r.status, r.scheduled_for, r.finished_at, r.conversation_id, r.summary, r.seen_at is not null as seen,
                   row_number() over (partition by r.task_id order by r.scheduled_for desc) as n
            from task_runs r where r.task_id = any(${rows.map((r) => r.id)}::uuid[])
          ) x where n <= 10 order by scheduled_for desc`
      : [];
    return rows.map((r) => toItem(r, runs));
  });
}

export async function createTask(userId: string, input: TaskInput) {
  const c = clean(input);
  const [m] = await asUser(userId, (q) => q<{ workspace_id: string }[]>`select workspace_id from memberships where user_id = ${userId} limit 1`);
  const id = await asUser(userId, async (q) => {
    const [t] = await q<{ id: string }[]>`
      insert into scheduled_tasks (workspace_id, user_id, title, prompt, kind, run_at, rrule, timezone, next_run_at, notify, model)
      values (${m.workspace_id}, ${userId}, ${c.title}, ${c.prompt}, ${c.stored.kind}, ${c.stored.run_at}, ${c.stored.rrule}, ${c.timezone},
              ${c.next}, ${c.notify}, ${c.model})
      returning id`;
    return t.id;
  }).catch(capError);
  return (await listTasks(userId)).find((t) => t.id === id)!;
}

export async function updateTask(userId: string, id: string, input: TaskInput) {
  const c = clean(input);
  const rows = await asUser(userId, (q) => q`
    update scheduled_tasks set title = ${c.title}, prompt = ${c.prompt}, kind = ${c.stored.kind}, run_at = ${c.stored.run_at},
      rrule = ${c.stored.rrule}, timezone = ${c.timezone}, notify = ${c.notify}, model = ${c.model},
      next_run_at = ${c.next}, status = case when status = 'completed' then 'active' else status end, updated_at = now()
    where id = ${id} returning id`).catch(capError);
  if (!rows.length) throw new HttpError(404, "That task doesn't exist.");
  return (await listTasks(userId)).find((t) => t.id === id)!;
}

/** Pause, or resume (the next run is worked out from now, so a paused week doesn't all run at once). */
export async function setTaskPaused(userId: string, id: string, paused: boolean) {
  const [t] = await asUser(userId, (q) => q<Row[]>`select * from scheduled_tasks where id = ${id}`);
  if (!t) throw new HttpError(404, "That task doesn't exist.");
  if (paused) {
    await asUser(userId, (q) => q`update scheduled_tasks set status = 'paused', updated_at = now() where id = ${id}`);
  } else {
    const next = nextRun(fromStored(t), t.timezone);
    if (!next) throw new HttpError(400, "That one-off time has passed. Edit the task to pick a new time.");
    await asUser(userId, (q) => q`update scheduled_tasks set status = 'active', next_run_at = ${next}, updated_at = now() where id = ${id}`).catch(capError);
  }
  return (await listTasks(userId)).find((x) => x.id === id)!;
}

export async function deleteTask(userId: string, id: string) {
  const rows = await asUser(userId, (q) => q`delete from scheduled_tasks where id = ${id} returning id`);
  if (!rows.length) throw new HttpError(404, "That task doesn't exist.");
}

export async function markRunsSeen(userId: string) {
  await asService((q) => q`
    update task_runs r set seen_at = now() from scheduled_tasks t
    where t.id = r.task_id and t.user_id = ${userId} and r.seen_at is null and r.status in ('succeeded', 'failed')`);
}

export async function unseenRunCount(userId: string) {
  const [{ n }] = await asUser(userId, (q) => q<{ n: number }[]>`
    select count(*)::int as n from task_runs r join scheduled_tasks t on t.id = r.task_id
    where t.user_id = ${userId} and r.seen_at is null and r.status in ('succeeded', 'failed')`);
  return n;
}

/* ------------------------------------------------------------------ runner side (system) */

export type DueRun = { run_id: string; task_id: string; user_id: string; title: string; prompt: string; model: string | null; notify: Notify[]; scheduled_for: string };

/**
 * Claims up to `limit` due runs: records each (idempotent per task and scheduled time) and moves the
 * task to its next time first, so a slow or crashed run can't make the same tick fire twice.
 */
export async function claimDueRuns(limit = 5, now = new Date()): Promise<DueRun[]> {
  return asService(async (q) => {
    const due = await q<(Row & { user_id: string })[]>`
      select * from scheduled_tasks where status = 'active' and next_run_at <= ${now}
      order by next_run_at limit ${limit} for update skip locked`;
    const out: DueRun[] = [];
    for (const t of due) {
      const next = t.kind === "once" ? null : nextRun(fromStored(t), t.timezone, now);
      await q`
        update scheduled_tasks set last_run_at = ${now}, next_run_at = ${next},
          status = case when ${next === null} then 'completed' else status end, updated_at = now()
        where id = ${t.id}`;
      const [run] = await q<{ id: string }[]>`
        insert into task_runs (task_id, scheduled_for, status) values (${t.id}, ${t.next_run_at}, 'running')
        on conflict (task_id, scheduled_for) do nothing returning id`;
      if (run) out.push({ run_id: run.id, task_id: t.id, user_id: t.user_id, title: t.title, prompt: t.prompt, model: t.model, notify: t.notify, scheduled_for: t.next_run_at! });
    }
    return out;
  });
}

/** "Run now": an extra run at this moment, without moving the schedule. At most one run a minute (any kind). */
export async function claimManualRun(userId: string, id: string): Promise<DueRun> {
  const [t] = await asUser(userId, (q) => q<Row[]>`select * from scheduled_tasks where id = ${id}`);
  if (!t) throw new HttpError(404, "That task doesn't exist.");
  const at = new Date();
  const run = await asService(async (q) => {
    await q`select pg_advisory_xact_lock(hashtext(${"task-run:" + id}))`;
    const [recent] = await q`select 1 from task_runs where task_id = ${id} and started_at > now() - interval '1 minute' limit 1`;
    if (recent) return null;
    const [r] = await q<{ id: string }[]>`
      insert into task_runs (task_id, scheduled_for, status) values (${id}, ${at}, 'running')
      on conflict (task_id, scheduled_for) do nothing returning id`;
    return r ?? null;
  });
  if (!run) throw new HttpError(429, "It just ran. Try again in a minute.");
  return { run_id: run.id, task_id: id, user_id: userId, title: t.title, prompt: t.prompt, model: t.model, notify: t.notify, scheduled_for: at.toISOString() };
}

export async function finishRun(runId: string, r: { status: "succeeded" | "failed"; conversation_id: string | null; summary: string }) {
  await asService((q) => q`
    update task_runs set status = ${r.status}, conversation_id = ${r.conversation_id}, summary = ${r.summary.slice(0, 500)},
      finished_at = now(), updated_at = now()
    where id = ${runId}`);
}

/** Runs left "running" by a crashed instance. */
export async function failStuckRuns() {
  const rows = await asService((q) => q`
    update task_runs set status = 'failed', summary = 'The run was interrupted.', finished_at = now(), updated_at = now()
    where status = 'running' and started_at < now() - interval '15 minutes' returning id`);
  return rows.length;
}
