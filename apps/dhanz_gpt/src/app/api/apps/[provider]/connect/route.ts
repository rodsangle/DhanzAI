import { NextResponse } from "next/server";
import { appKeyConfigured } from "@/lib/apps/crypto";
import { newState, OAUTH_COOKIE } from "@/lib/apps/oauth";
import { provider } from "@/lib/apps/registry";
import { SHOP_RE } from "@/lib/apps/shopify";
import { appUrl } from "@/lib/server/email";
import { requireUser, route } from "@/lib/server/http";

// Starts connecting an app: off to the provider's consent screen, back to ./callback.
export const GET = route(async (req: Request, { params }: { params: Promise<{ provider: string }> }) => {
  const uid = await requireUser();
  const p = provider((await params).provider);
  if (!p) return NextResponse.json({ error: "Unknown app." }, { status: 404 });
  if (!p.configured() || !appKeyConfigured()) return NextResponse.redirect(appUrl(`/apps?error=${encodeURIComponent(`${p.name} isn't set up for this workspace yet.`)}`), 302);
  let shop: string | null = null;
  if (p.needsShop) {
    shop = (new URL(req.url).searchParams.get("shop") ?? "").trim().toLowerCase().replace(/^https?:\/\//, "").replace(/\/.*$/, "");
    if (shop && !shop.includes(".")) shop = `${shop}.myshopify.com`;
    if (!SHOP_RE.test(shop)) return NextResponse.redirect(appUrl(`/apps?error=${encodeURIComponent("Enter your store's .myshopify.com address.")}`), 302);
  }
  const { state, cookie, challenge } = newState(p.id, uid, shop);
  const res = NextResponse.redirect(p.authorizeUrl({ state: state.s, redirectUri: appUrl(`/api/apps/${p.id}/callback`), codeChallenge: challenge, shop }), 302);
  res.cookies.set(OAUTH_COOKIE, cookie, { httpOnly: true, sameSite: "lax", secure: appUrl("/").startsWith("https:"), path: "/api/apps", maxAge: 600 });
  return res;
});
