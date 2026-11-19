import { HttpError, receiveUpload } from "@/lib/data";
import { storageDriver } from "@/lib/server/storage";
import { idParam, requireUser, route } from "@/lib/server/http";

// Local storage driver only. With Supabase Storage the browser uploads straight to the bucket.
export const PUT = route(async (req: Request, { params }: { params: Promise<{ id: string }> }) => {
  if (storageDriver() !== "local") throw new HttpError(404, "Not found");
  const userId = await requireUser();
  const len = Number(req.headers.get("content-length") ?? 0);
  if (len > 512 * 1024 * 1024) throw new HttpError(413, "Over the 512 MB limit.");
  await receiveUpload(userId, idParam((await params).id), Buffer.from(await req.arrayBuffer()));
  return { ok: true };
});
