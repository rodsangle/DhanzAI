/**
 * Self-hosted schedule. On Vercel, vercel.json's crons call /api/cron/*. On a server of our own nothing does,
 * so with SELF_CRON=1 the app calls its own cron routes on the same schedule (sweep every 5 minutes: scheduled
 * tasks, reminders, memory; purge once a day). Same Bearer CRON_SECRET check as Vercel Cron.
 */
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs" || process.env.SELF_CRON !== "1" || !process.env.CRON_SECRET) return;
  const base = `http://127.0.0.1:${process.env.PORT || 3000}`;
  const headers = { authorization: `Bearer ${process.env.CRON_SECRET}` };
  const busy = new Set<string>();

  const hit = async (path: string) => {
    if (busy.has(path)) return; // a slow run is never doubled up
    busy.add(path);
    try {
      const res = await fetch(base + path, { headers, signal: AbortSignal.timeout(4 * 60_000) });
      if (!res.ok) console.error(`[schedule] ${path} answered ${res.status}`);
    } catch (e) {
      console.error(`[schedule] ${path} failed: ${(e as Error).message}`);
    } finally {
      busy.delete(path);
    }
  };

  setTimeout(() => void hit("/api/cron/sweep"), 30_000).unref();
  setInterval(() => void hit("/api/cron/sweep"), 5 * 60_000).unref();
  setInterval(() => void hit("/api/cron/purge"), 24 * 60 * 60_000).unref();
  console.log("[schedule] self-hosted schedule on: sweep every 5 min, purge daily");
}
