import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { authMode, currentUserId, DEV_COOKIE, DEV_SESSION_COOKIE, supabaseServer } from "@/lib/server/auth";
import { asService } from "@/lib/server/db";
import { route } from "@/lib/server/http";
import { dhanzLogout } from "@/lib/server/dhanz-auth";

// ?scope=global signs out every device (Settings → Security).
export const POST = route(async (req: Request) => {
  const global = new URL(req.url).searchParams.get("scope") === "global";
  const res = NextResponse.json({ ok: true });
  if (authMode() === "supabase") {
    await (await supabaseServer()).auth.signOut({ scope: global ? "global" : "local" });
  } else {
    const userId = await currentUserId();
    const sid = (await cookies()).get(DEV_SESSION_COOKIE)?.value;
    if (userId && authMode() === "dhanz") {
      // End the DHANZ AI sessions too: this device's, or every one this account opened here.
      const ids = global
        ? (await asService((q) => q<{ session_id: string }[]>`select session_id from dhanz_sessions where user_id = ${userId}`)).map((r) => r.session_id)
        : sid ? [sid] : [];
      await Promise.all(ids.map((id) => dhanzLogout(id).catch(() => {})));
    }
    if (userId && global) await asService((q) => q`delete from auth.sessions where user_id = ${userId}`);
    else if (userId && sid) await asService((q) => q`delete from auth.sessions where id = ${sid} and user_id = ${userId}`);
  }
  res.cookies.delete(DEV_COOKIE);
  res.cookies.delete(DEV_SESSION_COOKIE);
  return res;
});
