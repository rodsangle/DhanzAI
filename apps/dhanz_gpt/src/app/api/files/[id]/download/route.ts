import { NextResponse } from "next/server";
import { getFileForView, readFileBytes } from "@/lib/data";
import { signedDownloadUrl, storageDriver } from "@/lib/server/storage";
import { currentUserId, idParam, route } from "@/lib/server/http";

// Access is checked here (RLS, or a shared link the viewer can open). Supabase driver: redirect to a
// 60-second signed URL on the storage domain (separate origin). Local driver: stream with a sandbox CSP.
export const GET = route(async (req: Request, { params }: { params: Promise<{ id: string }> }) => {
  const file = await getFileForView(await currentUserId(), idParam((await params).id));
  const inline = new URL(req.url).searchParams.get("inline") === "1";
  if (storageDriver() === "supabase") {
    const res = NextResponse.redirect(await signedDownloadUrl(file.storage_path, file.name, inline), 302);
    res.headers.set("Cache-Control", "private, no-store");
    return res;
  }
  const bytes = await readFileBytes(file);
  return new Response(new Uint8Array(bytes), {
    headers: {
      "Content-Type": file.mime,
      "Content-Disposition": `${inline ? "inline" : "attachment"}; filename*=UTF-8''${encodeURIComponent(file.name)}`,
      "Cache-Control": "private, max-age=3600",
      "Content-Security-Policy": "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox",
      "X-Content-Type-Options": "nosniff",
    },
  });
});
