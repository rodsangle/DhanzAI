import "server-only";
import { googleDrive } from "./google-drive";
import { shopifyApp } from "./shopify";
import { slackApp } from "./slack";
import type { AppProvider, AppTool, Importance, PermissionLevel, ProviderId } from "./types";

export const PROVIDERS: AppProvider[] = [googleDrive, slackApp, shopifyApp];
export const provider = (id: string) => PROVIDERS.find((p) => p.id === id) ?? null;
export const toolOwner = (name: string): { provider: AppProvider; tool: AppTool } | null => {
  for (const p of PROVIDERS) {
    const tool = p.tools.find((t) => t.name === name);
    if (tool) return { provider: p, tool };
  }
  return null;
};

/** Apps named with @ in the person's messages ("@Google Drive", "@drive", "@Slack"). */
export function mentionedApps(texts: string[]): ProviderId[] {
  const out = new Set<ProviderId>();
  for (const p of PROVIDERS)
    for (const m of p.mentions) {
      const re = new RegExp(`(^|\\s)@${m.replace(/ /g, "\\s*")}(?![\\w-])`, "i");
      if (texts.some((t) => re.test(t))) out.add(p.id);
    }
  return [...out];
}

/** Whether an action needs the person's go-ahead, given the connection's permission level. */
export function needsApproval(level: PermissionLevel, importance: Importance, alwaysAllowed: string[], tool: string) {
  if (alwaysAllowed.includes(tool)) return false;
  if (level === "never_ask") return false;
  if (level === "always_ask") return true;
  if (level === "any_changes") return importance !== "read";
  return importance === "important";
}
