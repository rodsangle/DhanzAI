import "server-only";
import { NextResponse } from "next/server";
import { z } from "zod";
import { HttpError } from "@/lib/data/errors";

export { currentUserId, requireUser, DEV_COOKIE as SESSION_COOKIE } from "./auth";

/** Wrap a handler: maps HttpError to JSON `{ error }` with its status; anything else is a logged 500 without details. */
export function route<A extends unknown[]>(fn: (...args: A) => Promise<Response | unknown>) {
  return async (...args: A): Promise<Response> => {
    try {
      const out = await fn(...args);
      if (out instanceof Response) return out;
      return NextResponse.json(out ?? { ok: true });
    } catch (e) {
      if (e instanceof HttpError) return NextResponse.json({ ...(e.data ?? {}), error: e.message }, { status: e.status });
      console.error("[api]", (e as Error)?.message ?? e);
      return NextResponse.json({ error: "Something went wrong on our side. Try again." }, { status: 500 });
    }
  };
}

/** Parse and validate a JSON body against a zod schema. */
export async function body<S extends z.ZodType>(req: Request, schema: S): Promise<z.infer<S>> {
  let raw: unknown;
  try {
    raw = await req.json();
  } catch {
    throw new HttpError(400, "The request body isn't valid JSON.");
  }
  const parsed = schema.safeParse(raw);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    throw new HttpError(400, `Invalid ${issue?.path.join(".") || "request"}: ${issue?.message ?? "check the input"}`);
  }
  return parsed.data;
}

export const zId = z.uuid();
/** Route params: a malformed id is a 404, not a 500. */
export function idParam(v: string) {
  if (!zId.safeParse(v).success) throw new HttpError(404, "Not found");
  return v;
}
