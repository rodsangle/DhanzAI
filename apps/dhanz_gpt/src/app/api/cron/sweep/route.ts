import { NextResponse } from "next/server";
import { claimDueRuns, failStuckRuns, sweepExports, sweepStuckStreams } from "@/lib/data";
import { cronAuthorized } from "@/lib/server/cron";
import { runExport } from "@/lib/server/export";
import { executeRun } from "@/lib/server/tasks";

export const maxDuration = 300;

// Every 5 minutes (vercel.json):
// - answers left "streaming" by a crashed instance become retryable errors, and so do task runs;
// - scheduled tasks that are due run (up to 5 per tick; the rest wait for the next tick);
// - exports that never started are run, and ones stuck running are marked failed.
export async function GET(req: Request) {
  if (!cronAuthorized(req)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const swept = await sweepStuckStreams();
  const stuckRuns = await failStuckRuns();
  const due = await claimDueRuns(5);
  for (const run of due) await executeRun(run);
  const exports = await sweepExports();
  for (const id of exports.queued) await runExport(id);
  return NextResponse.json({ swept, tasks: { ran: due.length, stuck: stuckRuns }, exports: { failed: exports.failed, ran: exports.queued.length } });
}
