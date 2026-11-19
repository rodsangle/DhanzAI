import { z } from "zod";
import { body, requireUser, route } from "@/lib/server/http";
import { hasSubscription, isPushEndpoint, pushConfigured, removeSubscription, saveSubscription, vapidPublicKey } from "@/lib/server/push";

const Sub = z.object({
  endpoint: z.url().max(2000).refine(isPushEndpoint, "That isn't a browser push service."),
  keys: z.object({ p256dh: z.string().min(20).max(200), auth: z.string().min(8).max(100) }),
});

// Browser push on this device: the public VAPID key, and saving or removing this browser's subscription.
export const GET = route(async (req: Request) => {
  const userId = await requireUser();
  const endpoint = new URL(req.url).searchParams.get("endpoint");
  return { configured: pushConfigured(), publicKey: vapidPublicKey(), subscribed: endpoint ? await hasSubscription(userId, endpoint) : false };
});
export const POST = route(async (req: Request) => {
  const userId = await requireUser();
  if (!pushConfigured()) return Response.json({ error: "Push notifications aren't set up for this workspace." }, { status: 409 });
  await saveSubscription(userId, await body(req, Sub), req.headers.get("user-agent"));
  return { ok: true };
});
export const DELETE = route(async (req: Request) => {
  const userId = await requireUser();
  await removeSubscription(userId, (await body(req, z.object({ endpoint: z.string().max(2000) }))).endpoint);
  return { ok: true };
});
