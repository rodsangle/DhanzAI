import "server-only";
import { BRAND } from "@/lib/brand";
import fs from "node:fs/promises";
import path from "node:path";

/**
 * Transactional email. EMAIL_PROVIDER:
 * - "resend": Resend's REST API (POST https://api.resend.com/emails) with RESEND_API_KEY, from EMAIL_FROM
 *   on a domain verified in Resend. Each send carries an Idempotency-Key, so a retried job sends once.
 * - "outbox": appended to .data/outbox.jsonl (development and tests).
 * - "off": nothing is sent; the app still shows everything in-app.
 * Default: "resend" when RESEND_API_KEY is set, else "outbox" in development, "off" otherwise.
 */
export function emailProvider(): "resend" | "outbox" | "off" {
  const p = process.env.EMAIL_PROVIDER;
  if (p === "resend" || p === "outbox" || p === "off") return p;
  if (process.env.RESEND_API_KEY) return "resend";
  return process.env.NEXT_PUBLIC_AUTH_MODE === "dev" ? "outbox" : "off";
}

/** Absolute link into the app for emails (APP_URL, e.g. https://gpt.dhanzai.com). */
export function appUrl(pathname: string) {
  const base = (process.env.APP_URL || "http://localhost:3000").replace(/\/+$/, "");
  return `${base}${pathname}`;
}

export type Email = { to: string; subject: string; text: string; html: string; idempotencyKey: string };

export const OUTBOX = path.join(process.cwd(), ".data", "outbox.jsonl");

/** Sends one email. Returns false (never throws) when it couldn't be sent, so callers carry on. */
export async function sendEmail(e: Email): Promise<boolean> {
  const provider = emailProvider();
  if (provider === "off") return false;
  if (provider === "outbox") {
    await fs.mkdir(path.dirname(OUTBOX), { recursive: true });
    await fs.appendFile(OUTBOX, JSON.stringify({ ...e, at: new Date().toISOString() }) + "\n");
    return true;
  }
  try {
    const res = await fetch(`${process.env.RESEND_BASE_URL || "https://api.resend.com"}/emails`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
        "Content-Type": "application/json",
        "Idempotency-Key": e.idempotencyKey.slice(0, 256),
      },
      body: JSON.stringify({ from: process.env.EMAIL_FROM || BRAND.from, to: [e.to], subject: e.subject, text: e.text, html: e.html }),
      signal: AbortSignal.timeout(15_000),
    });
    if (!res.ok) console.error("[email] resend", res.status, (await res.text()).slice(0, 200));
    return res.ok;
  } catch (err) {
    console.error("[email] resend", (err as Error).message);
    return false;
  }
}

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

/** One plain, readable layout for every email: a heading, a few lines, one button. Colours mirror the brand tokens (email clients can't read CSS variables). */
export function layout(o: { heading: string; lines: string[]; button?: { label: string; href: string }; footer?: string }) {
  const text = [o.heading, "", ...o.lines, ...(o.button ? ["", `${o.button.label}: ${o.button.href}`] : []), "", o.footer ?? BRAND.full].join("\n");
  const html =
    `<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:520px;margin:0 auto;padding:24px;color:#1a1714;background:#fbf9f5">` +
    `<h1 style="font-size:20px;margin:0 0 16px">${esc(o.heading)}</h1>` +
    o.lines.map((l) => `<p style="font-size:15px;line-height:1.5;margin:0 0 12px">${esc(l)}</p>`).join("") +
    (o.button ? `<p style="margin:20px 0"><a href="${esc(o.button.href)}" style="background:#a93f14;color:#fffdf9;padding:10px 16px;border-radius:8px;text-decoration:none;font-size:14px">${esc(o.button.label)}</a></p>` : "") +
    `<p style="font-size:12px;color:#5e554a;margin-top:24px">${esc(o.footer ?? BRAND.full)}</p></div>`;
  return { text, html };
}
