import crypto from "node:crypto";
import fs from "node:fs";
import https from "node:https";
import path from "node:path";
import { test, expect, signIn, assistantArticles } from "./fixtures";
import { sql, tempUser } from "./db";

// F10 Scheduled tasks (S18) and their notifications (S26).
const CRON = { Authorization: "Bearer local-test-secret" };
const ready = (page: import("@playwright/test").Page) => expect(page.getByRole("button", { name: /^Test / }).filter({ visible: true })).toBeVisible();
const outbox = (to: string) => {
  const f = path.join(__dirname, "..", ".data", "outbox.jsonl");
  return fs.existsSync(f) ? fs.readFileSync(f, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l)).filter((m) => m.to === to) : [];
};
const NY = "America/New_York";

async function apiTask(page: import("@playwright/test").Page, over: Record<string, unknown> = {}) {
  const res = await page.request.post("/api/tasks", {
    data: { title: "Drop recap", prompt: "Write a plan for the week's drops", timezone: NY, notify: ["email"], schedule: { kind: "weekdays", time: "09:00" }, ...over },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  return res.json();
}
const makeDue = (id: string) => sql`update scheduled_tasks set next_run_at = now() - interval '1 minute' where id = ${id}`;
const sweep = async (page: import("@playwright/test").Page) => {
  const r = await page.request.get("/api/cron/sweep", { headers: CRON });
  expect(r.ok()).toBeTruthy();
  return r.json();
};

test.describe("F10 Scheduled tasks", () => {
  test("F10-H1 create a weekday task from the Scheduled page", async ({ page, a11y }) => {
    const u = await tempUser("sched");
    await signIn(page, u.email);
    await page.goto("/scheduled");
    await ready(page);
    await expect(page.getByText("Nothing scheduled")).toBeVisible();
    await a11y("S18 empty");
    await page.getByRole("button", { name: "New task" }).first().click();
    const dialog = page.getByRole("dialog", { name: "New scheduled task" });
    await dialog.getByLabel("Name").fill("Monday drop recap");
    await dialog.getByLabel("What should it do each time?").fill("Write a plan for this week's drops");
    await dialog.getByLabel("Repeats").selectOption("weekly");
    await dialog.getByRole("checkbox", { name: "Wednesday" }).click();
    await dialog.getByLabel("Time", { exact: true }).fill("08:30");
    await dialog.getByLabel("Time zone").selectOption(NY);
    await expect(dialog.getByText(/^Every Monday and Wednesday at 8:30 AM\. Next run /)).toBeVisible();
    await a11y("S18 new task");
    await dialog.getByRole("button", { name: "Schedule" }).click();
    await expect(page.getByText(/^Scheduled\. First run /)).toBeVisible();
    const card = page.getByRole("list", { name: "Tasks" }).getByRole("listitem").filter({ hasText: "Monday drop recap" });
    await expect(card).toContainText("Every Monday and Wednesday at 8:30 AM");
    await expect(card).toContainText("Next run");
    const [row] = await sql`select rrule, timezone, notify from scheduled_tasks where user_id = ${u.id}`;
    expect(row.rrule).toBe("FREQ=WEEKLY;BYDAY=MO,WE;BYHOUR=8;BYMINUTE=30");
    expect(row.timezone).toBe(NY);
  });

  test("F10-H2 the cron runs a due task once: a chat, an email, an unread badge, and the next time", async ({ page }) => {
    const u = await tempUser("runner");
    await signIn(page, u.email);
    const t = await apiTask(page);
    await makeDue(t.id);
    const out = await sweep(page);
    expect(out.tasks.ran).toBeGreaterThanOrEqual(1);
    const runs = await sql`select status, conversation_id, summary from task_runs where task_id = ${t.id}`;
    expect(runs).toHaveLength(1);
    expect(runs[0].status).toBe("succeeded");
    const [conv] = await sql`select title, kind from conversations where id = ${runs[0].conversation_id}`;
    expect(conv).toEqual({ title: "Drop recap", kind: "task_run" });
    // Moved to the next weekday 9:00 New York time; a second sweep doesn't run it again.
    const [task] = await sql`select next_run_at from scheduled_tasks where id = ${t.id}`;
    expect(new Date(task.next_run_at).getTime()).toBeGreaterThan(Date.now());
    expect(new Date(task.next_run_at).toLocaleTimeString("en-US", { timeZone: NY, hour: "numeric", minute: "2-digit" })).toBe("9:00 AM");
    await sweep(page);
    expect(await sql`select id from task_runs where task_id = ${t.id}`).toHaveLength(1);
    // Email with a link to the chat.
    const mail = outbox(u.email);
    expect(mail).toHaveLength(1);
    expect(mail[0].subject).toBe("Scheduled: Drop recap");
    expect(mail[0].text).toContain(`/c/${runs[0].conversation_id}`);
    // Unread in the sidebar until Scheduled is opened.
    await page.goto("/");
    await expect(page.getByRole("link", { name: "Scheduled, 1 new" })).toBeVisible();
    await page.getByRole("link", { name: "Scheduled, 1 new" }).click();
    const card = page.getByRole("list", { name: "Tasks" }).getByRole("listitem").filter({ hasText: "Drop recap" });
    await expect(card.getByRole("list", { name: "Recent runs of Drop recap" })).toContainText("Done");
    await expect(page.getByRole("link", { name: "Scheduled", exact: true })).toBeVisible();
    await card.getByRole("link", { name: /^Open/ }).click();
    await expect(page).toHaveURL(`/c/${runs[0].conversation_id}`);
    await expect(assistantArticles(page)).toHaveCount(1);
  });

  test("F10-H3 Run now, pause, resume, edit and delete", async ({ page }) => {
    const u = await tempUser("controls");
    await signIn(page, u.email);
    const t = await apiTask(page, { notify: [] });
    const [{ next_run_at: before }] = await sql`select next_run_at from scheduled_tasks where id = ${t.id}`;
    await page.goto("/scheduled");
    const card = page.getByRole("list", { name: "Tasks" }).getByRole("listitem").filter({ hasText: "Drop recap" });
    const menu = async (item: string) => {
      await card.getByRole("button", { name: "Options for Drop recap" }).click();
      await page.getByRole("menuitem", { name: item }).click();
    };
    await menu("Run now");
    await expect(card.getByRole("list", { name: "Recent runs of Drop recap" })).toContainText("Done", { timeout: 20_000 });
    const [{ next_run_at: after }] = await sql`select next_run_at from scheduled_tasks where id = ${t.id}`;
    expect(after).toEqual(before);
    await menu("Run now");
    await expect(page.getByText("It just ran. Try again in a minute.", { exact: true })).toBeVisible();
    // A real 60-second window, not calendar minutes: a run 59 s ago still blocks, one 61 s ago doesn't.
    await sql`update task_runs set started_at = now() - interval '59 seconds' where task_id = ${t.id}`;
    expect((await page.request.post(`/api/tasks/${t.id}/run`)).status()).toBe(429);
    await sql`update task_runs set started_at = now() - interval '61 seconds' where task_id = ${t.id}`;
    expect((await page.request.post(`/api/tasks/${t.id}/run`)).status()).toBe(200);
    await expect.poll(async () => (await sql`select count(*)::int as n from task_runs where task_id = ${t.id} and status = 'running'`)[0].n, { timeout: 20_000 }).toBe(0);

    await menu("Pause");
    await expect(card.getByText("Paused", { exact: true })).toBeVisible();
    await expect(card).not.toContainText("Next run");
    await makeDue(t.id);
    await sweep(page);
    expect(await sql`select id from task_runs where task_id = ${t.id}`).toHaveLength(2);
    await menu("Resume");
    await expect(card).toContainText("Next run");

    await menu("Edit");
    const dialog = page.getByRole("dialog", { name: "Edit task" });
    await dialog.getByLabel("Repeats").selectOption("monthly");
    await dialog.getByLabel("Day of the month").selectOption("15");
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(card).toContainText("Monthly on the 15th at 9:00 AM");

    await menu("Delete");
    await page.getByRole("dialog", { name: "Delete Drop recap?" }).getByRole("button", { name: "Delete task" }).click();
    await expect(page.getByText("Nothing scheduled")).toBeVisible();
    // The chat from the earlier run stays.
    const [{ n }] = await sql`select count(*)::int as n from conversations where user_id = ${u.id} and kind = 'task_run'`;
    expect(n).toBe(2);
  });

  test("F10-E1 a one-off runs once and is then done; a past time is refused", async ({ page }) => {
    const u = await tempUser("oneoff");
    await signIn(page, u.email);
    const past = await page.request.post("/api/tasks", {
      data: { title: "Late", prompt: "x", timezone: NY, notify: [], schedule: { kind: "once", date: "2026-01-01", time: "09:00" } },
    });
    expect(past.status()).toBe(400);
    expect((await past.json()).error).toBe("That time has already passed. Pick a time in the future.");
    const t = await apiTask(page, { title: "Launch reminder", notify: [], schedule: { kind: "once", date: "2030-01-01", time: "09:00" } });
    await makeDue(t.id);
    await sweep(page);
    const [row] = await sql`select status, next_run_at from scheduled_tasks where id = ${t.id}`;
    expect(row).toEqual({ status: "completed", next_run_at: null });
    await page.goto("/scheduled");
    const card = page.getByRole("list", { name: "Tasks" }).getByRole("listitem").filter({ hasText: "Launch reminder" });
    await expect(card.getByText("Done", { exact: true }).first()).toBeVisible();
  });

  test("F10-E2 at most 15 active tasks; another person's tasks are out of reach", async ({ page, browser }) => {
    const u = await tempUser("cap");
    await signIn(page, u.email);
    let first = "";
    for (let i = 0; i < 15; i++) {
      const t = await apiTask(page, { title: `Task ${i + 1}`, notify: [] });
      if (!first) first = t.id;
    }
    const over = await page.request.post("/api/tasks", { data: { title: "One too many", prompt: "x", timezone: NY, notify: [], schedule: { kind: "daily", time: "09:00" } } });
    expect(over.status()).toBe(409);
    expect((await over.json()).error).toBe("You can have 15 active tasks. Pause or delete one first.");

    const ctx = await browser.newContext();
    const other = await ctx.newPage();
    const mate = await tempUser("taskmate");
    await signIn(other, mate.email);
    expect(await (await other.request.get("/api/tasks")).json()).toEqual([]);
    expect((await other.request.post(`/api/tasks/${first}/run`)).status()).toBe(404);
    expect((await other.request.post(`/api/tasks/${first}/pause`, { data: { paused: true } })).status()).toBe(404);
    expect((await other.request.delete(`/api/tasks/${first}`)).status()).toBe(404);
    await ctx.close();
  });

  test("F10-H4 push: the result reaches a subscribed browser, encrypted; a gone subscription is removed", async ({ page }) => {
    const u = await tempUser("push");
    await signIn(page, u.email);
    // A stand-in push service, and a browser key pair (what a real browser makes when it subscribes).
    const got: { headers: import("node:http").IncomingHttpHeaders; body: Buffer }[] = [];
    let status = 201;
    const certs = path.join(__dirname, "certs");
    const tls = { key: fs.readFileSync(path.join(certs, "test-push.key")), cert: fs.readFileSync(path.join(certs, "test-push.crt")) };
    const server = https.createServer(tls, (req, res) => {
      const chunks: Buffer[] = [];
      req.on("data", (c) => chunks.push(c));
      req.on("end", () => {
        got.push({ headers: req.headers, body: Buffer.concat(chunks) });
        res.writeHead(status).end();
      });
    });
    await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
    const port = (server.address() as { port: number }).port;
    const ua = crypto.createECDH("prime256v1");
    ua.generateKeys();
    const auth = crypto.randomBytes(16);
    const b64u = (b: Buffer) => b.toString("base64url");
    const endpoint = `https://127.0.0.1:${port}/push/device-1`;
    try {
      // Only browser push services are accepted (127.0.0.1 is allowed for this test only).
      const keys = { p256dh: b64u(ua.getPublicKey()), auth: b64u(auth) };
      for (const bad of ["https://169.254.169.254/latest", "https://internal.rodrech.com/hook", `http://127.0.0.1:${port}/push`]) {
        expect((await page.request.post("/api/push", { data: { endpoint: bad, keys } })).status(), bad).toBe(400);
      }
      const sub = await page.request.post("/api/push", { data: { endpoint, keys } });
      expect(sub.ok(), await sub.text()).toBeTruthy();
      expect((await (await page.request.get(`/api/push?endpoint=${encodeURIComponent(endpoint)}`)).json()).subscribed).toBe(true);

      const t = await apiTask(page, { title: "Push recap", notify: ["push"] });
      await makeDue(t.id);
      await sweep(page);
      expect(got).toHaveLength(1);
      const { headers, body } = got[0];
      expect(headers["content-encoding"]).toBe("aes128gcm");
      expect(String(headers.authorization)).toMatch(/^vapid t=[\w-]+\.[\w-]+\.[\w-]+, k=[\w-]+$/);
      // RFC 8291: salt(16) | record size(4) | key id length(1) | sender public key | ciphertext.
      const salt = body.subarray(0, 16);
      const idlen = body[20];
      const asPublic = body.subarray(21, 21 + idlen);
      const cipher = body.subarray(21 + idlen);
      const secret = ua.computeSecret(asPublic);
      const info = Buffer.concat([Buffer.from("WebPush: info\0"), ua.getPublicKey(), asPublic]);
      const ikm = Buffer.from(crypto.hkdfSync("sha256", secret, auth, info, 32));
      const cek = Buffer.from(crypto.hkdfSync("sha256", ikm, salt, Buffer.from("Content-Encoding: aes128gcm\0"), 16));
      const nonce = Buffer.from(crypto.hkdfSync("sha256", ikm, salt, Buffer.from("Content-Encoding: nonce\0"), 12));
      const d = crypto.createDecipheriv("aes-128-gcm", cek, nonce);
      d.setAuthTag(cipher.subarray(cipher.length - 16));
      const plain = Buffer.concat([d.update(cipher.subarray(0, cipher.length - 16)), d.final()]);
      const payload = JSON.parse(plain.subarray(0, plain.lastIndexOf(2)).toString("utf8"));
      const [run] = await sql`select conversation_id from task_runs where task_id = ${t.id}`;
      expect(payload).toMatchObject({ title: "Push recap", url: `/c/${run.conversation_id}`, tag: `task-${t.id}` });
      expect(payload.body.length).toBeGreaterThan(10);

      // The push service says the subscription is gone: it's deleted.
      status = 410;
      await sql`update task_runs set started_at = now() - interval '2 minutes' where task_id = ${t.id}`; // one run a minute
      expect((await page.request.post(`/api/tasks/${t.id}/run`)).status()).toBe(200);
      await expect.poll(async () => (await sql`select count(*)::int as n from push_subscriptions where endpoint = ${endpoint}`)[0].n, { timeout: 20_000 }).toBe(0);
    } finally {
      server.close();
    }
  });

  test("F10-H5 Settings → Notifications explains push and email", async ({ page, a11y }) => {
    const u = await tempUser("notif");
    await signIn(page, u.email);
    await page.goto("/");
    await ready(page);
    await page.getByRole("button", { name: /^Test notif/ }).click();
    await page.getByRole("menuitem", { name: "Settings" }).click();
    await page.getByRole("tab", { name: "Notifications" }).click();
    await expect(page.getByRole("switch", { name: "Push notifications on this browser" })).toBeVisible();
    await expect(page.getByText(`Tasks set to email you send results to ${u.email}. Pick per task in Scheduled.`)).toBeVisible();
    await a11y("S26 notifications");
  });
});
