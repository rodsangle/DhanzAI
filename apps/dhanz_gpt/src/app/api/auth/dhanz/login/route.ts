import { z } from "zod";
import { dhanzLogin } from "@/lib/server/dhanz-auth";
import { body, route } from "@/lib/server/http";
import { limitAttempts, requireDhanzMode, respond, visitor } from "../shared";

// S02 sign-in with a DHANZ AI account: email and password, passed once to the DHANZ API.
export const POST = route(async (req: Request) => {
  requireDhanzMode();
  const { ip, ua } = await visitor();
  limitAttempts(ip);
  const { email, password } = await body(req, z.object({ email: z.email().max(320), password: z.string().min(1).max(128) }));
  return respond(await dhanzLogin(email.trim(), password, ip, ua));
});
