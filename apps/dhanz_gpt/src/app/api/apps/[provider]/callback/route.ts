import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { OAUTH_COOKIE, readState } from "@/lib/apps/oauth";
import { safeEqual } from "@/lib/apps/crypto";
import { provider } from "@/lib/apps/registry";
import { saveConnection } from "@/lib/apps/store";
import { AppError } from "@/lib/apps/types";
import { appUrl } from "@/lib/server/email";
import { requireUser, route } from "@/lib/server/http";

// Back from the provider: check the state against the signed cookie (same person, same app, not expired),
// trade the code for tokens, save the connection, and return to Apps.
export const GET = route(async (req: Request, { params }: { params: Promise<{ provider: string }> }) => {
  const uid = await requireUser();
  const p = provider((await params).provider);
  const url = new URL(req.url);
  const back = (q: string) => {
    const res = NextResponse.redirect(appUrl(`/apps?${q}`), 302);
    res.cookies.set(OAUTH_COOKIE, "", { path: "/api/apps", maxAge: 0 });
    return res;
  };
  const st = readState((await cookies()).get(OAUTH_COOKIE)?.value);
  if (!p || !st || st.p !== p.id || st.uid !== uid || !safeEqual(st.s, url.searchParams.get("state") ?? "")) {
    return back(`error=${encodeURIComponent("That connection attempt expired or didn't match. Try again.")}`);
  }
  if (url.searchParams.get("error")) return back(`error=${encodeURIComponent(`${p.name} wasn't connected.`)}`);
  const code = url.searchParams.get("code");
  if (!code) return back(`error=${encodeURIComponent(`${p.name} didn't send a sign-in code.`)}`);
  try {
    const { tokens, account } = await p.exchange({ code, redirectUri: appUrl(`/api/apps/${p.id}/callback`), codeVerifier: st.v, shop: st.shop, query: url.searchParams });
    await saveConnection(uid, p.id, account, tokens);
    return back(`connected=${p.id}`);
  } catch (e) {
    return back(`error=${encodeURIComponent(e instanceof AppError ? e.message : `${p.name} didn't connect. Try again.`)}`);
  }
});
