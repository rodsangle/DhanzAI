/**
 * The product's name in one place.
 * Dhanz GPT is a DHANZ AI product (renamed 2026-11-19 from the RODRECH-internal "Flatbill").
 * To rename: change it here and in public/sw.js, then run the sweep in replica/brand.md.
 */
export const BRAND = {
  name: "Dhanz GPT",
  company: "DHANZ AI",
  full: "Dhanz GPT by DHANZ AI",
  tagline: "Chat, pages and projects from DHANZ AI",
  from: "Dhanz GPT <gpt@dhanzai.com>",
  /** Who "everyone" means in sharing options: the people in the signed-in person's workspace. */
  everyone: "Everyone in your workspace",
} as const;
