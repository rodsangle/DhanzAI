import { z } from "zod";
import { dhanzVerify } from "@/lib/server/dhanz-auth";
import { body, route } from "@/lib/server/http";
import { limitAttempts, requireDhanzMode, respond, visitor } from "../shared";

// S02 the second step: the authenticator or emailed code (or a recovery code) for the challenge.
export const POST = route(async (req: Request) => {
  requireDhanzMode();
  const { ip, ua } = await visitor();
  limitAttempts(ip);
  const { mfa_token, code } = await body(req, z.object({ mfa_token: z.string().min(20).max(2000), code: z.string().min(6).max(20) }));
  return respond(await dhanzVerify(mfa_token, code, ip, ua));
});
