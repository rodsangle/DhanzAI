import { NextResponse } from "next/server";
import { z } from "zod";
import { HttpError, storagePathsOwnedBy } from "@/lib/data";
import { asService } from "@/lib/server/db";
import { removeObjects, supabaseAdmin } from "@/lib/server/storage";
import { authMode, DEV_COOKIE, DEV_SESSION_COOKIE, supabaseServer } from "@/lib/server/auth";
import { body, requireUser, route } from "@/lib/server/http";
import { dhanzLogout } from "@/lib/server/dhanz-auth";

// Deletes the account for real: stored files, then the auth user, which cascades to every row they own.
export const DELETE = route(async (req: Request) => {
  const userId = await requireUser();
  const { confirm } = await body(req, z.object({ confirm: z.literal("DELETE") }));
  if (confirm !== "DELETE") throw new HttpError(400, "Type DELETE to confirm.");
  const [{ owners }] = await asService((q) => q`
    select count(*) filter (where role = 'owner')::int as owners from memberships
    where workspace_id = (select workspace_id from memberships where user_id = ${userId})`);
  const [{ me, members, ws }] = await asService((q) => q`
    select m.role = 'owner' as me, m.workspace_id as ws,
           (select count(*)::int from memberships x where x.workspace_id = m.workspace_id) as members
    from memberships m where m.user_id = ${userId}`);
  // Alone in the workspace (every DHANZ account has its own): the workspace goes with the account.
  const alone = members <= 1;
  if (me && owners <= 1 && !alone) throw new HttpError(409, "You're the workspace's only owner. Make someone else an owner first.");
  await removeObjects(await storagePathsOwnedBy(userId));
  if (authMode() === "supabase") {
    await (await supabaseServer()).auth.signOut({ scope: "global" });
    const { error } = await supabaseAdmin().auth.admin.deleteUser(userId);
    if (error) throw new Error(`deleteUser failed: ${error.message}`);
  } else {
    if (authMode() === "dhanz") {
      const sessions = await asService((q) => q<{ session_id: string }[]>`select session_id from dhanz_sessions where user_id = ${userId}`);
      await Promise.all(sessions.map((r) => dhanzLogout(r.session_id).catch(() => {})));
    }
    await asService((q) => q`delete from auth.users where id = ${userId}`);
  }
  if (alone) await asService((q) => q`delete from workspaces w where w.id = ${ws} and not exists (select 1 from memberships m where m.workspace_id = w.id)`);
  const res = NextResponse.json({ ok: true });
  res.cookies.delete(DEV_COOKIE);
  res.cookies.delete(DEV_SESSION_COOKIE);
  return res;
});
