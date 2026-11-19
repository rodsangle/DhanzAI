import { NextResponse, type NextRequest } from "next/server";
import { createServerClient } from "@supabase/ssr";

const supabaseMode = () => (process.env.NEXT_PUBLIC_AUTH_MODE ?? (process.env.NEXT_PUBLIC_SUPABASE_URL ? "supabase" : "dev")) === "supabase";
// dev and dhanz modes share one session cookie; the API routes verify it.

function toLogin(req: NextRequest) {
  const url = new URL("/login", req.url);
  if (req.nextUrl.pathname !== "/") url.searchParams.set("next", req.nextUrl.pathname + req.nextUrl.search);
  return NextResponse.redirect(url);
}

// Refreshes the Supabase session cookie on navigation and sends signed-out visitors to /login.
// Only an optimistic gate: every API route checks the session itself.
export async function proxy(req: NextRequest) {
  if (!supabaseMode()) {
    return req.cookies.get("dg_uid") ? NextResponse.next() : toLogin(req);
  }
  let res = NextResponse.next({ request: req });
  const supabase = createServerClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!, {
    cookies: {
      getAll: () => req.cookies.getAll(),
      setAll: (list) => {
        for (const { name, value } of list) req.cookies.set(name, value);
        res = NextResponse.next({ request: req });
        for (const { name, value, options } of list) res.cookies.set(name, value, options);
      },
    },
  });
  const { data } = await supabase.auth.getUser();
  if (!data.user) return toLogin(req);
  return res;
}

export const config = {
  matcher: ["/((?!api|auth|login|s/|design|_next|favicon.ico|sw.js).*)"],
};
