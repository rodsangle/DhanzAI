import { z } from "zod";
export const Level = z.enum(["view", "comment", "edit"]);
export const SpaceBody = z.object({ name: z.string().max(200), everyone_level: Level.nullable().optional() });
export const SpacePatch = z.object({ name: z.string().max(200).optional(), everyone_level: Level.nullable().optional() });
export const Grant = z.object({ user_id: z.uuid(), level: Level });
