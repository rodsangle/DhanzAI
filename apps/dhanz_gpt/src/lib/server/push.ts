import "server-only";
import { sendNotification } from "web-push";
import { asService, asUser } from "./db";

/**
 * Browser push (the Web Push standard, signed with VAPID keys you generate yourself:
 * `npx web-push generate-vapid-keys`). Each browser that turns notifications on stores one
 * subscription. A push service answering 404 or 410 means the subscription is gone, so it's deleted.
 */
export function pushConfigured() {
  return !!(process.env.VAPID_PUBLIC_KEY && process.env.VAPID_PRIVATE_KEY);
}
export const vapidPublicKey = () => process.env.VAPID_PUBLIC_KEY ?? null;

/**
 * The server POSTs to whatever endpoint a browser hands over, so only the browsers' own push services
 * are accepted (Chrome/Edge via FCM, Firefox, Safari, Windows); anything else could aim the server at
 * an internal address. PUSH_ALLOWED_HOSTS adds hosts, for tests.
 */
const PUSH_HOSTS = [/^fcm\.googleapis\.com$/, /^([\w-]+\.)*push\.services\.mozilla\.com$/, /^web\.push\.apple\.com$/, /^([\w-]+\.)*notify\.windows\.com$/];
export function isPushEndpoint(raw: string) {
  try {
    const u = new URL(raw);
    if (u.protocol !== "https:") return false;
    const extra = (process.env.PUSH_ALLOWED_HOSTS ?? "").split(",").map((h) => h.trim()).filter(Boolean);
    return PUSH_HOSTS.some((r) => r.test(u.hostname)) || extra.includes(u.hostname);
  } catch {
    return false;
  }
}

export type PushSub = { endpoint: string; keys: { p256dh: string; auth: string } };

export async function saveSubscription(userId: string, sub: PushSub, userAgent: string | null) {
  await asUser(userId, (q) => q`
    insert into push_subscriptions (user_id, endpoint, p256dh, auth, user_agent)
    values (${userId}, ${sub.endpoint}, ${sub.keys.p256dh}, ${sub.keys.auth}, ${userAgent?.slice(0, 300) ?? null})
    on conflict (endpoint) do update set user_id = excluded.user_id, p256dh = excluded.p256dh, auth = excluded.auth, updated_at = now()`);
}

export async function removeSubscription(userId: string, endpoint: string) {
  await asUser(userId, (q) => q`delete from push_subscriptions where endpoint = ${endpoint}`);
}

export async function hasSubscription(userId: string, endpoint: string) {
  const rows = await asUser(userId, (q) => q`select 1 from push_subscriptions where endpoint = ${endpoint}`);
  return rows.length > 0;
}

/** Sends to every browser the person turned on. Returns how many accepted it. Never throws. */
export async function pushTo(userId: string, payload: { title: string; body: string; url: string; tag?: string }) {
  if (!pushConfigured()) return 0;
  const subs = await asService((q) => q<{ endpoint: string; p256dh: string; auth: string }[]>`
    select endpoint, p256dh, auth from push_subscriptions where user_id = ${userId}`);
  let sent = 0;
  for (const s of subs) {
    if (!isPushEndpoint(s.endpoint)) continue;
    try {
      await sendNotification({ endpoint: s.endpoint, keys: { p256dh: s.p256dh, auth: s.auth } }, JSON.stringify(payload), {
        vapidDetails: { subject: process.env.VAPID_SUBJECT || "mailto:gpt@dhanzai.com", publicKey: process.env.VAPID_PUBLIC_KEY!, privateKey: process.env.VAPID_PRIVATE_KEY! },
        TTL: 60 * 60 * 24,
        timeout: 10_000,
      });
      sent++;
    } catch (e) {
      const status = (e as { statusCode?: number }).statusCode;
      if (status === 404 || status === 410) await asService((q) => q`delete from push_subscriptions where endpoint = ${s.endpoint}`);
      else console.error("[push]", status ?? (e as Error).message);
    }
  }
  return sent;
}
