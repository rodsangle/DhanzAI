import { z } from "zod";

/** Request body for creating or saving an assistant (limits are enforced again in the data layer). */
export const AssistantBody = z.object({
  name: z.string().max(200),
  description: z.string().max(1000).optional(),
  instructions: z.string().max(25000).optional(),
  starters: z.array(z.string().max(500)).max(10).optional(),
  recommended_model: z.string().max(60).nullish(),
  capabilities: z.array(z.enum(["web_search", "image_generation"])).optional(),
  visibility: z.enum(["private", "workspace"]).optional(),
  file_ids: z.array(z.uuid()).max(50).optional(),
});
