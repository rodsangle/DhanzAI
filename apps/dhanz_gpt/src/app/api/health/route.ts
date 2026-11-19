import { NextResponse } from "next/server";
import { asService } from "@/lib/server/db";
import { authMode } from "@/lib/server/auth";

// For the deploy script and monitoring: is the app up, can it reach its database, and which sign-in mode.
export async function GET() {
  try {
    const [{ n }] = await asService((q) => q<{ n: number }[]>`select count(*)::int as n from schema_migrations`);
    return NextResponse.json({ ok: true, migrations: n, auth: authMode() }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ ok: false }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
