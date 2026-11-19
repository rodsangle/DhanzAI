import { shareConversation } from "@/lib/data";
import { idParam, requireUser, route } from "@/lib/server/http";

export const POST = route(async (_req: Request, { params }: { params: Promise<{ id: string }> }) =>
  shareConversation(await requireUser(), idParam((await params).id)),
);
