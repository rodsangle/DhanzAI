import { z } from "zod";

const time = z.string().regex(/^\d{1,2}:\d{2}$/);

/** Request body for creating or saving a scheduled task (checked again in the data layer). */
export const TaskBody = z.object({
  title: z.string().max(400),
  prompt: z.string().max(20000),
  timezone: z.string().max(80),
  notify: z.array(z.enum(["push", "email"])).max(2),
  model: z.string().max(60).nullish(),
  schedule: z.discriminatedUnion("kind", [
    z.object({ kind: z.literal("once"), date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/), time }),
    z.object({ kind: z.literal("daily"), time }),
    z.object({ kind: z.literal("weekdays"), time }),
    z.object({ kind: z.literal("weekly"), days: z.array(z.number().int().min(0).max(6)).min(1).max(7), time }),
    z.object({ kind: z.literal("monthly"), day: z.number().int().min(1).max(28), time }),
  ]),
});
