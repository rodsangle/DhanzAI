import "server-only";
import { AppError, call, str, testBase, type AppProvider } from "./types";

/**
 * Slack through the Web API with a user token from OAuth v2 (user scopes), so search and posts
 * act as the person and only see what they can see. search.messages needs a user token.
 */
const base = () => {
  const t = testBase();
  return { authorize: t ? `${t}/slack/oauth/v2/authorize` : "https://slack.com/oauth/v2/authorize", api: t ? `${t}/slack/api` : "https://slack.com/api" };
};
const USER_SCOPES = ["search:read", "channels:read", "channels:history", "chat:write"];

async function slack<T = Record<string, unknown>>(method: string, token: string, params: Record<string, string>, post = false): Promise<T> {
  const res = post
    ? await call(`${base().api}/${method}`, { what: "Slack", method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams(params) })
    : await call(`${base().api}/${method}?${new URLSearchParams(params)}`, { what: "Slack", headers: { Authorization: `Bearer ${token}` } });
  const j = (await res.json()) as Record<string, unknown> & { ok: boolean; error?: string };
  if (!j.ok) {
    if (j.error === "invalid_auth" || j.error === "token_revoked" || j.error === "account_inactive") throw new AppError("Slack said the connection isn't allowed anymore. Reconnect it in Apps.", 401);
    if (j.error === "channel_not_found" || j.error === "not_in_channel") throw new AppError("That Slack channel wasn't found, or you're not in it.", 400);
    throw new AppError(`Slack returned an error (${j.error}).`);
  }
  return j as unknown as T;
}

/** "#drops", "drops" or a channel id → channel id. */
async function channelId(token: string, channel: string) {
  const name = channel.trim().replace(/^#/, "");
  if (/^[CG][A-Z0-9]{6,}$/.test(name)) return name;
  let cursor = "";
  for (let i = 0; i < 10; i++) {
    type Page = { channels: { id: string; name: string }[]; response_metadata?: { next_cursor?: string } };
    const j = await slack<Page>("conversations.list", token, { limit: "200", exclude_archived: "true", types: "public_channel", ...(cursor ? { cursor } : {}) });
    const hit = j.channels.find((c) => c.name === name);
    if (hit) return hit.id;
    cursor = j.response_metadata?.next_cursor ?? "";
    if (!cursor) break;
  }
  throw new AppError(`There's no #${name} channel you can see.`, 400);
}

export const slackApp: AppProvider = {
  id: "slack",
  name: "Slack",
  mentions: ["Slack"],
  description: "Search Slack, read channels, and post messages as you.",
  can: ["Search messages you can see", "Read a channel's recent messages", "Post a message as you (asks first)"],
  configured: () => !!(process.env.SLACK_CLIENT_ID && process.env.SLACK_CLIENT_SECRET),
  authorizeUrl: ({ state, redirectUri }) =>
    `${base().authorize}?${new URLSearchParams({ client_id: process.env.SLACK_CLIENT_ID!, user_scope: USER_SCOPES.join(","), redirect_uri: redirectUri, state })}`,
  async exchange({ code, redirectUri }) {
    const res = await call(`${base().api}/oauth.v2.access`, {
      what: "Slack", method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ client_id: process.env.SLACK_CLIENT_ID!, client_secret: process.env.SLACK_CLIENT_SECRET!, code, redirect_uri: redirectUri }),
    });
    const j = (await res.json()) as { ok: boolean; error?: string; authed_user?: { id: string; access_token: string; scope: string }; team?: { id: string; name: string } };
    if (!j.ok || !j.authed_user?.access_token) throw new AppError(`Slack didn't connect (${j.error ?? "no user token"}).`, 400);
    return {
      tokens: { access_token: j.authed_user.access_token, scopes: j.authed_user.scope.split(",") },
      account: { id: `${j.team?.id}:${j.authed_user.id}`, label: j.team?.name ?? "Slack workspace" },
    };
  },
  async revoke(token) {
    await slack("auth.revoke", token, {}, true).catch(() => {});
  },
  tools: [
    {
      name: "slack_search",
      description: "Search Slack messages the person can see. Supports Slack search syntax like in:#channel and from:@name. Returns up to 10 matches.",
      input_schema: { type: "object", properties: { query: { type: "string" } }, required: ["query"] },
      importance: "read",
      describe: (i) => `Searched Slack for “${str(i.query, 80)}”`,
      preview: (i) => [{ label: "Search for", value: str(i.query, 200) }],
      async run({ token }, i) {
        type Match = { text: string; username?: string; channel?: { name?: string }; permalink?: string; ts: string };
        const j = await slack<{ messages: { matches: Match[] } }>("search.messages", token, { query: str(i.query, 300), count: "10", sort: "timestamp" });
        const matches = (j.messages?.matches ?? []).map((m) => ({ text: m.text.slice(0, 600), from: m.username, channel: m.channel?.name, link: m.permalink, ts: m.ts }));
        return { result: JSON.stringify(matches), summary: `${matches.length} messages found` };
      },
    },
    {
      name: "slack_read_channel",
      description: "Read the most recent messages in a Slack channel the person is in, by name (like #drops) or id.",
      input_schema: { type: "object", properties: { channel: { type: "string" }, limit: { type: "number", description: "Up to 50" } }, required: ["channel"] },
      importance: "read",
      describe: (i) => `Read #${str(i.channel, 60).replace(/^#/, "")} in Slack`,
      preview: (i) => [{ label: "Channel", value: str(i.channel, 100) }],
      async run({ token }, i) {
        const id = await channelId(token, str(i.channel, 100));
        const limit = Math.min(50, Math.max(1, Number(i.limit) || 20));
        const j = await slack<{ messages: { text: string; user?: string; ts: string }[] }>("conversations.history", token, { channel: id, limit: String(limit) });
        return { result: JSON.stringify(j.messages.map((m) => ({ text: m.text.slice(0, 600), user: m.user, ts: m.ts }))), summary: `Read ${j.messages.length} messages` };
      },
    },
    {
      name: "slack_post_message",
      description: "Post a message to a Slack channel as the person. Only when they asked for it. The message is sent exactly as given.",
      input_schema: { type: "object", properties: { channel: { type: "string" }, text: { type: "string" } }, required: ["channel", "text"] },
      importance: "important",
      describe: (i) => `Posted in #${str(i.channel, 60).replace(/^#/, "")} on Slack`,
      preview: (i) => [{ label: "Channel", value: `#${str(i.channel, 100).replace(/^#/, "")}` }, { label: "Message", value: str(i.text, 2000) }],
      async run({ token }, i) {
        const id = await channelId(token, str(i.channel, 100));
        const j = await slack<{ ts: string; channel: string }>("chat.postMessage", token, { channel: id, text: str(i.text, 4000) }, true);
        return { result: JSON.stringify({ ok: true, channel: j.channel, ts: j.ts }), summary: "Message posted" };
      },
    },
  ],
};
