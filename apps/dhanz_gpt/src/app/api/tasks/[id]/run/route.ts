import { after } from "next/server";
import { claimManualRun } from "@/lib/data";
import { idParam, requireUser, route } from "@/lib/server/http";
import { executeRun } from "@/lib/server/tasks";

// "Run now": an extra run in the background; the schedule doesn't move.
export const POST = route(async (_req: Request, { params }: { params: Promise<{ id: string }> }) => {
  const run = await claimManualRun(await requireUser(), idParam((await params).id));
  after(() => executeRun(run));
  return { run_id: run.run_id };
});
