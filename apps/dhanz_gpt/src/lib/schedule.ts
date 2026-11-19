/**
 * Task schedules (S18): what the form offers, how it's stored, and when it next runs.
 * Shared by the browser (preview, descriptions) and the server (cron).
 *
 * Stored in scheduled_tasks as kind 'once' + run_at, or kind 'recurring' + an RRULE subset
 * (RFC 5545: FREQ=DAILY|WEEKLY|MONTHLY with BYDAY, BYMONTHDAY, BYHOUR, BYMINUTE), always evaluated
 * in the task's IANA time zone, so "9:00 AM" stays 9:00 AM across daylight saving changes.
 */

export type Schedule =
  | { kind: "once"; date: string; time: string } // date YYYY-MM-DD, time HH:MM (24 h), local to the zone
  | { kind: "daily"; time: string }
  | { kind: "weekdays"; time: string }
  | { kind: "weekly"; days: number[]; time: string } // 0 = Sunday … 6 = Saturday
  | { kind: "monthly"; day: number; time: string }; // 1–28, so every month has it

const RR_DAYS = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"];
export const DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

const hm = (time: string) => {
  const m = /^(\d{1,2}):(\d{2})$/.exec(time);
  if (!m || +m[1] > 23 || +m[2] > 59) throw new Error("Pick a time.");
  return [+m[1], +m[2]] as const;
};
const pad = (n: number) => String(n).padStart(2, "0");

export function validate(s: Schedule): string | null {
  try {
    hm(s.time);
  } catch (e) {
    return (e as Error).message;
  }
  if (s.kind === "once" && !/^\d{4}-\d{2}-\d{2}$/.test(s.date)) return "Pick a date.";
  if (s.kind === "weekly" && (!s.days.length || s.days.some((d) => d < 0 || d > 6))) return "Pick at least one day.";
  if (s.kind === "monthly" && !(Number.isInteger(s.day) && s.day >= 1 && s.day <= 28)) return "Pick a day from 1 to 28.";
  return null;
}

export function isValidZone(tz: string) {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}

/** Milliseconds the zone is ahead of UTC at this instant. */
function offset(utcMs: number, tz: string) {
  const p = new Intl.DateTimeFormat("en-US", {
    timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).formatToParts(new Date(utcMs));
  const g = (t: string) => +p.find((x) => x.type === t)!.value;
  return Date.UTC(g("year"), g("month") - 1, g("day"), g("hour"), g("minute"), g("second")) - (utcMs - (utcMs % 1000));
}

/** The instant a wall-clock time happens in a zone. A time skipped by a spring-forward change moves to just after it. */
export function zonedToUtc(y: number, mo: number, d: number, h: number, mi: number, tz: string) {
  const guess = Date.UTC(y, mo - 1, d, h, mi);
  const first = guess - offset(guess, tz);
  const second = guess - offset(first, tz);
  // If that wall time doesn't exist (the hour skipped in spring), `second` lands an hour early; use `first`, just after the gap.
  const wall = new Date(second + offset(second, tz));
  return wall.getUTCHours() === h && wall.getUTCMinutes() === mi ? second : first;
}

/** The local calendar date (and weekday) of an instant in a zone. */
export function localDate(utcMs: number, tz: string) {
  const t = utcMs + offset(utcMs, tz);
  const d = new Date(t);
  return { y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate(), dow: d.getUTCDay() };
}

/** The first run strictly after `after`, or null if a one-off is in the past. */
export function nextRun(s: Schedule, tz: string, after: Date = new Date()): Date | null {
  const [h, mi] = hm(s.time);
  if (s.kind === "once") {
    const [y, m, d] = s.date.split("-").map(Number);
    const t = zonedToUtc(y, m, d, h, mi, tz);
    return t > after.getTime() ? new Date(t) : null;
  }
  const start = localDate(after.getTime(), tz);
  for (let i = 0; i < 400; i++) {
    const day = new Date(Date.UTC(start.y, start.m - 1, start.d + i));
    const [y, m, d, dow] = [day.getUTCFullYear(), day.getUTCMonth() + 1, day.getUTCDate(), day.getUTCDay()];
    const match =
      s.kind === "daily" || (s.kind === "weekdays" && dow >= 1 && dow <= 5) || (s.kind === "weekly" && s.days.includes(dow)) || (s.kind === "monthly" && d === s.day);
    if (!match) continue;
    const t = zonedToUtc(y, m, d, h, mi, tz);
    if (t > after.getTime()) return new Date(t);
  }
  return null;
}

/** For the database: kind, run_at (one-offs) and rrule (recurring). */
export function toStored(s: Schedule, tz: string): { kind: "once" | "recurring"; run_at: Date | null; rrule: string | null } {
  const [h, mi] = hm(s.time);
  if (s.kind === "once") {
    const [y, m, d] = s.date.split("-").map(Number);
    return { kind: "once", run_at: new Date(zonedToUtc(y, m, d, h, mi, tz)), rrule: null };
  }
  const at = `BYHOUR=${h};BYMINUTE=${mi}`;
  const rrule =
    s.kind === "daily" ? `FREQ=DAILY;${at}`
    : s.kind === "weekdays" ? `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;${at}`
    : s.kind === "weekly" ? `FREQ=WEEKLY;BYDAY=${[...new Set(s.days)].sort().map((d) => RR_DAYS[d]).join(",")};${at}`
    : `FREQ=MONTHLY;BYMONTHDAY=${s.day};${at}`;
  return { kind: "recurring", run_at: null, rrule };
}

/** Back from the database to the form's shape. */
export function fromStored(t: { kind: string; run_at: string | Date | null; rrule: string | null; timezone: string }): Schedule {
  if (t.kind === "once" && t.run_at) {
    const ms = new Date(t.run_at).getTime();
    const l = localDate(ms, t.timezone);
    const local = new Date(ms + offset(ms, t.timezone));
    return { kind: "once", date: `${l.y}-${pad(l.m)}-${pad(l.d)}`, time: `${pad(local.getUTCHours())}:${pad(local.getUTCMinutes())}` };
  }
  const parts = Object.fromEntries((t.rrule ?? "").split(";").map((kv) => kv.split("=")));
  const time = `${pad(+(parts.BYHOUR ?? 9))}:${pad(+(parts.BYMINUTE ?? 0))}`;
  if (parts.FREQ === "DAILY") return { kind: "daily", time };
  if (parts.FREQ === "MONTHLY") return { kind: "monthly", day: +parts.BYMONTHDAY, time };
  const days = (parts.BYDAY ?? "").split(",").map((d: string) => RR_DAYS.indexOf(d)).filter((d: number) => d >= 0).sort();
  if (days.join() === "1,2,3,4,5") return { kind: "weekdays", time };
  return { kind: "weekly", days, time };
}

function clock(time: string) {
  const [h, mi] = hm(time);
  return new Date(Date.UTC(2000, 0, 1, h, mi)).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "UTC" });
}

/** "Every weekday at 9:00 AM", for lists and confirmations. */
export function describe(s: Schedule): string {
  const at = clock(s.time);
  switch (s.kind) {
    case "once": {
      const [y, m, d] = s.date.split("-").map(Number);
      const date = new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
      return `Once, ${date} at ${at}`;
    }
    case "daily": return `Every day at ${at}`;
    case "weekdays": return `Every weekday at ${at}`;
    case "weekly": {
      const days = [...s.days].sort().map((d) => DAY_NAMES[d]);
      return `Every ${days.length > 2 ? `${days.slice(0, -1).join(", ")} and ${days.at(-1)}` : days.join(" and ")} at ${at}`;
    }
    case "monthly": {
      const suffix = s.day % 10 === 1 && s.day !== 11 ? "st" : s.day % 10 === 2 && s.day !== 12 ? "nd" : s.day % 10 === 3 && s.day !== 13 ? "rd" : "th";
      return `Monthly on the ${s.day}${suffix} at ${at}`;
    }
  }
}
