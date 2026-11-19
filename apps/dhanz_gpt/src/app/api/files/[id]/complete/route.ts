import { completeUpload } from "@/lib/data";
import { idParam, requireUser, route } from "@/lib/server/http";

// Step 3: confirm the object arrived with the right size, then read text formats.
export const POST = route(async (_req: Request, { params }: { params: Promise<{ id: string }> }) =>
  completeUpload(await requireUser(), idParam((await params).id)),
);
