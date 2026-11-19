import { getMessage } from "@/lib/data";
import { sseFor } from "@/lib/ai/generation";
import { idParam, requireUser, route } from "@/lib/server/http";

// Catch-up stream for a reloaded page or another tab.
export const GET = route(async (_req: Request, { params }: { params: Promise<{ id: string }> }) =>
  sseFor(await getMessage(await requireUser(), idParam((await params).id))),
);
