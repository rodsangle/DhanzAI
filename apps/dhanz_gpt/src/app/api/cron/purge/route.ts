import { NextResponse } from "next/server";
import { purgeExpired } from "@/lib/data";
import { removeObjects } from "@/lib/server/storage";
import { cronAuthorized } from "@/lib/server/cron";

// Daily (vercel.json): files trashed 30+ days ago, temporary chats over 30 days, abandoned uploads, expired exports.
export async function GET(req: Request) {
  if (!cronAuthorized(req)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const { paths, chats, exports } = await purgeExpired();
  let storageError: string | null = null;
  try {
    await removeObjects(paths);
  } catch (e) {
    storageError = (e as Error).message; // rows are gone; orphaned objects are logged for a manual sweep
    console.error("[cron/purge] storage cleanup failed", { count: paths.length, storageError });
  }
  return NextResponse.json({ objects: paths.length, chats, exports, storageError });
}
