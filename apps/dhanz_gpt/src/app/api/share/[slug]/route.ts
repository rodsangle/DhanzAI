import { deleteShare, getShare, HttpError } from "@/lib/data";
import { currentUserId, requireUser, route } from "@/lib/server/http";

type Ctx = { params: Promise<{ slug: string }> };
const slugOk = (s: string) => {
  if (!/^[0-9a-f]{32}$/.test(s)) throw new HttpError(404, "This link was deleted or never existed.");
  return s;
};

export const GET = route(async (_req: Request, { params }: Ctx) => getShare(await currentUserId(), slugOk((await params).slug)));

export const DELETE = route(async (_req: Request, { params }: Ctx) => {
  await deleteShare(await requireUser(), slugOk((await params).slug));
  return { ok: true };
});
