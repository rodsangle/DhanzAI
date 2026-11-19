import { listImages } from "@/lib/data";
import { requireUser, route } from "@/lib/server/http";

export const GET = route(async () => listImages(await requireUser()));
