import { test, expect } from "@playwright/test";
import { describe, fromStored, nextRun, toStored, zonedToUtc, type Schedule } from "../src/lib/schedule";

const NY = "America/New_York";
const iso = (d: Date | null) => d?.toISOString() ?? null;

// F10 (unit): schedules in the person's zone, across daylight saving changes.
test("F10-U1 daily 9:00 in New York stays 9:00 across the November change", () => {
  const s: Schedule = { kind: "daily", time: "09:00" };
  expect(iso(nextRun(s, NY, new Date("2026-10-31T12:00:00Z")))).toBe("2026-10-31T13:00:00.000Z"); // EDT
  expect(iso(nextRun(s, NY, new Date("2026-10-31T13:00:00Z")))).toBe("2026-11-01T14:00:00.000Z"); // EST
});

test("F10-U2 a skipped spring-forward time runs just after the gap; an ambiguous fall-back time runs once, the first time", () => {
  expect(new Date(zonedToUtc(2027, 3, 14, 2, 30, NY)).toISOString()).toBe("2027-03-14T07:30:00.000Z"); // 3:30 EDT
  expect(new Date(zonedToUtc(2026, 11, 1, 1, 30, NY)).toISOString()).toBe("2026-11-01T05:30:00.000Z"); // first 1:30 (EDT)
});

test("F10-U3 weekdays, weekly days, monthly, and other zones", () => {
  // Friday 2026-11-20 10:00 EST → next weekday 9:00 is Monday the 23rd.
  expect(iso(nextRun({ kind: "weekdays", time: "09:00" }, NY, new Date("2026-11-20T15:00:00Z")))).toBe("2026-11-23T14:00:00.000Z");
  expect(iso(nextRun({ kind: "weekly", days: [3], time: "18:30" }, NY, new Date("2026-11-17T12:00:00Z")))).toBe("2026-11-18T23:30:00.000Z");
  expect(iso(nextRun({ kind: "monthly", day: 1, time: "08:00" }, NY, new Date("2026-11-17T12:00:00Z")))).toBe("2026-12-01T13:00:00.000Z");
  expect(iso(nextRun({ kind: "daily", time: "09:00" }, "Pacific/Auckland", new Date("2026-11-17T12:00:00Z")))).toBe("2026-11-17T20:00:00.000Z");
});

test("F10-U4 one-offs: future runs once, past is null", () => {
  expect(iso(nextRun({ kind: "once", date: "2026-11-20", time: "12:00" }, NY, new Date("2026-11-17T12:00:00Z")))).toBe("2026-11-20T17:00:00.000Z");
  expect(nextRun({ kind: "once", date: "2026-11-01", time: "12:00" }, NY, new Date("2026-11-17T12:00:00Z"))).toBeNull();
});

test("F10-U5 stored form round-trips, and descriptions read naturally", () => {
  const all: Schedule[] = [
    { kind: "once", date: "2026-12-04", time: "11:55" },
    { kind: "daily", time: "07:05" },
    { kind: "weekdays", time: "09:00" },
    { kind: "weekly", days: [1, 3], time: "18:30" },
    { kind: "monthly", day: 15, time: "08:00" },
  ];
  for (const s of all) {
    const st = toStored(s, NY);
    expect(fromStored({ ...st, timezone: NY })).toEqual(s);
  }
  expect(describe(all[0])).toBe("Once, Fri, Dec 4, 2026 at 11:55 AM");
  expect(describe(all[2])).toBe("Every weekday at 9:00 AM");
  expect(describe(all[3])).toBe("Every Monday and Wednesday at 6:30 PM");
  expect(describe({ kind: "weekly", days: [5, 1, 3], time: "09:00" })).toBe("Every Monday, Wednesday and Friday at 9:00 AM");
  expect(describe(all[4])).toBe("Monthly on the 15th at 8:00 AM");
  expect(toStored(all[3], NY).rrule).toBe("FREQ=WEEKLY;BYDAY=MO,WE;BYHOUR=18;BYMINUTE=30");
});
