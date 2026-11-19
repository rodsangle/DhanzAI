import { after } from "next/server";
import { latestExport, requestExport, runExport } from "@/lib/server/export";
import { requireUser, route } from "@/lib/server/http";

// Settings → Data controls → Export: the latest export's status, or start a new one (runs in the background).
export const GET = route(async () => latestExport(await requireUser()));
export const POST = route(async () => {
  const row = await requestExport(await requireUser());
  if (row.status === "queued") after(() => runExport(row.id));
  return row;
});
