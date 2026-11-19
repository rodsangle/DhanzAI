import { NextResponse } from "next/server";
import { z } from "zod";
import { devSignIn, HttpError } from "@/lib/data";
import { authMode, DEV_COOKIE, DEV_SESSION_COOKIE, isLocalRequest, startDevSession } from "@/lib/server/auth";
import { body, route } from "@/lib/server/http";

// Demo sign-in: NEXT_PUBLIC_AUTH_MODE=dev and localhost only. Production uses Google through Supabase Auth.
export const POST = route(async (req: Request) => {
  if (authMode() !== "dev" || !(await isLocalRequest())) throw new HttpError(404, "Not found");
  const { email } = await body(req, z.object({ email: z.string().max(320) }));
  const profile = await devSignIn(email);
  const fwd = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  const ip = fwd && /^[0-9a-f.:]+$/i.test(fwd) ? fwd : "127.0.0.1";
  const sid = await startDevSession(profile.id, req.headers.get("user-agent"), ip);
  const res = NextResponse.json({ ok: true, name: profile.name });
  const opts = { httpOnly: true, sameSite: "lax" as const, path: "/", maxAge: 60 * 60 * 24 * 30 };
  res.cookies.set(DEV_COOKIE, profile.id, opts);
  res.cookies.set(DEV_SESSION_COOKIE, sid, opts);
  return res;
});
