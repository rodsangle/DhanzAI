import { search } from "@/lib/data";
import { requireUser, route } from "@/lib/server/http";

export const GET = route(async (req: Request) => search(await requireUser(), new URL(req.url).searchParams.get("q") ?? ""));
