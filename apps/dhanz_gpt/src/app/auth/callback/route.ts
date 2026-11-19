import { NextResponse, type NextRequest } from "next/server";
import { supabaseServer } from "@/lib/server/auth";
import { safeNext as safePath } from "@/lib/safe-next";

// OAuth return: swap the code for a session cookie, then go where the user was headed.
export async function GET(req: NextRequest) {
  const url = req.nextUrl;
  const safeNext = safePath(url.searchParams.get("next"));
  const err = url.searchParams.get("error_description") ?? url.searchParams.get("error");
  if (err) {
    const reason = /database error saving new user|signup_domain_not_allowed/i.test(err) ? "domain" : "failed";
    return NextResponse.redirect(new URL(`/login?error=${reason}`, req.url));
  }
  const code = url.searchParams.get("code");
  if (!code) return NextResponse.redirect(new URL("/login?error=failed", req.url));
  const { error } = await (await supabaseServer()).auth.exchangeCodeForSession(code);
  if (error) return NextResponse.redirect(new URL("/login?error=failed", req.url));
  return NextResponse.redirect(new URL(safeNext, req.url));
}
