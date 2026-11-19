import { NextResponse } from "next/server";
import { exportForDownload } from "@/lib/server/export";
import { idParam, requireUser, route } from "@/lib/server/http";
import { readObject, signedDownloadUrl, storageDriver } from "@/lib/server/storage";

// The export zip, for its owner, until it expires (the email links here; signing in is required).
export const GET = route(async (_req: Request, { params }: { params: Promise<{ id: string }> }) => {
  const { storagePath } = await exportForDownload(await requireUser(), idParam((await params).id));
  const name = `dhanz-gpt-export-${new Date().toISOString().slice(0, 10)}.zip`;
  if (storageDriver() === "supabase") {
    const res = NextResponse.redirect(await signedDownloadUrl(storagePath, name, false), 302);
    res.headers.set("Cache-Control", "private, no-store");
    return res;
  }
  const bytes = await readObject(storagePath);
  if (!bytes) return NextResponse.json({ error: "That export isn't available." }, { status: 404 });
  return new Response(new Uint8Array(bytes), {
    headers: {
      "Content-Type": "application/zip",
      "Content-Disposition": `attachment; filename="${name}"`,
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
});
