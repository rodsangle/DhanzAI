// Stand-in for the Anthropic Messages API (SSE) and OpenAI Images API, for adapter tests. Logs request bodies.
import http from "node:http";
import fs from "node:fs";
import crypto from "node:crypto";
const LOG = "/tmp/mock-requests.jsonl";
fs.writeFileSync(LOG, "");
const PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
const words = "Mock answer from the stand-in API. It streams in small pieces so the app can show progress, then finishes cleanly with usage.".split(" ");
http.createServer(async (req, res) => {
  let raw = "";
  for await (const c of req) raw += c;
  if (req.url.startsWith("/__") || /^\/(google|slack|shop)\//.test(req.url)) return apps(req, res, raw);
  if (req.url.startsWith("/v1/audio/transcriptions")) return transcription(req, res, raw);
  if (req.url.startsWith("/v1/images/edits")) return imageEdit(req, res, raw);
  if (req.url.startsWith("/v1/audio/speech")) return speech(req, res, raw);
  if (req.url.startsWith("/dhanz/")) return dhanz(req, res, raw);
  const body = raw ? JSON.parse(raw) : {};
  fs.appendFileSync(LOG, JSON.stringify({ path: req.url, headers: req.headers, body }) + "\n");
  const lastUser = JSON.stringify(body.messages?.at?.(-1) ?? "");
  if (req.url.startsWith("/v1/messages")) {
    if (body.stream && lastUser.includes("MOCK_ERROR_529")) {
      res.writeHead(529, { "content-type": "application/json" });
      return res.end(JSON.stringify({ type: "error", error: { type: "overloaded_error", message: "Overloaded" } }));
    }
    const sysText = JSON.stringify(body.system ?? "");
    const hasSearch = (body.tools ?? []).some((t) => t.name === "web_search");
    if (lastUser.includes("MOCK_NOSEARCH_ORG") && hasSearch) {
      res.writeHead(400, { "content-type": "application/json" });
      return res.end(JSON.stringify({ type: "error", error: { type: "invalid_request_error", message: "Web search is not enabled for this organization." } }));
    }
    if (!body.stream && sysText.includes("short memory") && JSON.stringify(body.messages).includes("MOCK_MEMORY_BUSY")) {
      res.writeHead(529, { "content-type": "application/json" });
      return res.end(JSON.stringify({ type: "error", error: { type: "overloaded_error", message: "Overloaded" } }));
    }
    if (!body.stream && sysText.includes("short memory")) {
      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify({ id: "msg_m", type: "message", role: "assistant", model: body.model, content: [{ type: "text", text: "- Mock memory: runs RODRECH drops." }], stop_reason: "end_turn", stop_sequence: null, usage: { input_tokens: 9, output_tokens: 8 } }));
    }
    const last = body.messages?.at?.(-1);
    const toolResult = Array.isArray(last?.content) ? last.content.find((b) => b.type === "tool_result") : null;
    if (body.stream && (body.tools ?? []).some((t) => t.name === "slack_search") && (lastUser.includes("MOCK_TOOL") || toolResult)) {
      res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
      const send = (type, data) => res.write(`event: ${type}\ndata: ${JSON.stringify({ type, ...data })}\n\n`);
      send("message_start", { message: { id: "msg_t", type: "message", role: "assistant", model: body.model, content: [], stop_reason: null, stop_sequence: null, usage: { input_tokens: 30, output_tokens: 1 } } });
      if (toolResult) {
        send("content_block_start", { index: 0, content_block: { type: "text", text: "" } });
        send("content_block_delta", { index: 0, delta: { type: "text_delta", text: `From Slack: ${String(toolResult.content).includes("Friday noon") ? "the drop moved to Friday noon." : "nothing found."}` } });
        send("content_block_stop", { index: 0 });
        send("message_delta", { delta: { stop_reason: "end_turn", stop_sequence: null }, usage: { output_tokens: 9 } });
      } else {
        send("content_block_start", { index: 0, content_block: { type: "text", text: "" } });
        send("content_block_delta", { index: 0, delta: { type: "text_delta", text: "Checking Slack. " } });
        send("content_block_stop", { index: 0 });
        send("content_block_start", { index: 1, content_block: { type: "tool_use", id: "toolu_mock1", name: "slack_search", input: {} } });
        send("content_block_delta", { index: 1, delta: { type: "input_json_delta", partial_json: '{"query": "drop' } });
        send("content_block_delta", { index: 1, delta: { type: "input_json_delta", partial_json: ' date"}' } });
        send("content_block_stop", { index: 1 });
        send("message_delta", { delta: { stop_reason: "tool_use", stop_sequence: null }, usage: { output_tokens: 12 } });
      }
      send("message_stop", {});
      return res.end();
    }
    if (body.stream && hasSearch && (lastUser.includes("MOCK_SEARCH") || lastUser.includes("MOCK_PAUSE") || body.messages.at(-1).role === "assistant")) {
      res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
      const send = (type, data) => res.write(`event: ${type}\ndata: ${JSON.stringify({ type, ...data })}\n\n`);
      const continuing = body.messages.at(-1).role === "assistant";
      const pause = lastUser.includes("MOCK_PAUSE") && !continuing;
      send("message_start", { message: { id: "msg_s", type: "message", role: "assistant", model: body.model, content: [], stop_reason: null, stop_sequence: null, usage: { input_tokens: 50, output_tokens: 1 } } });
      let i = 0;
      if (!continuing) {
        send("content_block_start", { index: i, content_block: { type: "text", text: "" } });
        send("content_block_delta", { index: i, delta: { type: "text_delta", text: "Let me look that up. " } });
        send("content_block_stop", { index: i++ });
        send("content_block_start", { index: i, content_block: { type: "server_tool_use", id: "srvtoolu_1", name: "web_search", input: {} } });
        send("content_block_delta", { index: i, delta: { type: "input_json_delta", partial_json: '{"query": "fitted cap ' } });
        send("content_block_delta", { index: i, delta: { type: "input_json_delta", partial_json: 'trends"}' } });
        send("content_block_stop", { index: i++ });
        send("content_block_start", { index: i, content_block: { type: "web_search_tool_result", tool_use_id: "srvtoolu_1", content: [
          { type: "web_search_result", url: "https://news.example.org/caps", title: "Caps are back", encrypted_content: "ENC1", page_age: "1 day ago" },
          { type: "web_search_result", url: "https://shop.example.net/fitted", title: "Fitted guide", encrypted_content: "ENC2", page_age: null },
        ] } });
        send("content_block_stop", { index: i++ });
      }
      if (pause) {
        send("message_delta", { delta: { stop_reason: "pause_turn", stop_sequence: null }, usage: { output_tokens: 12, server_tool_use: { web_search_requests: 1 } } });
        send("message_stop", {});
        return res.end();
      }
      const cited = (idx, text, cites) => {
        send("content_block_start", { index: idx, content_block: { type: "text", text: "", citations: [] } });
        for (const c of cites) send("content_block_delta", { index: idx, delta: { type: "citations_delta", citation: { type: "web_search_result_location", url: c[0], title: c[1], encrypted_index: "EI", cited_text: "..." } } });
        send("content_block_delta", { index: idx, delta: { type: "text_delta", text } });
        send("content_block_stop", { index: idx });
      };
      cited(i++, "Fitted caps are trending again", [["https://news.example.org/caps", "Caps are back"]]);
      send("content_block_start", { index: i, content_block: { type: "text", text: "" } });
      send("content_block_delta", { index: i, delta: { type: "text_delta", text: ", and " } });
      send("content_block_stop", { index: i++ });
      cited(i++, "deep crowns sell best", [["https://shop.example.net/fitted", "Fitted guide"], ["https://news.example.org/caps", "Caps are back"]]);
      send("message_delta", { delta: { stop_reason: "end_turn", stop_sequence: null }, usage: { output_tokens: 30, server_tool_use: { web_search_requests: continuing ? 0 : 1 } } });
      send("message_stop", {});
      return res.end();
    }
    if (!body.stream) {
      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify({ id: "msg_t", type: "message", role: "assistant", model: body.model, content: [{ type: "text", text: "Mock Title Here" }], stop_reason: "end_turn", stop_sequence: null, usage: { input_tokens: 5, output_tokens: 3 } }));
    }
    const slow = lastUser.includes("SLOW");
    res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
    const send = (type, data) => res.write(`event: ${type}\ndata: ${JSON.stringify({ type, ...data })}\n\n`);
    send("message_start", { message: { id: "msg_1", type: "message", role: "assistant", model: body.model, content: [], stop_reason: null, stop_sequence: null, usage: { input_tokens: 42, output_tokens: 1 } } });
    send("content_block_start", { index: 0, content_block: { type: "thinking", thinking: "", signature: "" } });
    send("content_block_delta", { index: 0, delta: { type: "thinking_delta", thinking: "internal reasoning that must not be shown" } });
    send("content_block_stop", { index: 0 });
    send("content_block_start", { index: 1, content_block: { type: "text", text: "" } });
    const n = slow ? words.length * 4 : words.length;
    for (let i = 0; i < n; i++) {
      if (res.destroyed) return;
      send("content_block_delta", { index: 1, delta: { type: "text_delta", text: (i ? " " : "") + words[i % words.length] } });
      await new Promise((r) => setTimeout(r, slow ? 150 : 20));
    }
    send("content_block_stop", { index: 1 });
    send("message_delta", { delta: { stop_reason: "end_turn", stop_sequence: null }, usage: { output_tokens: n } });
    send("message_stop", {});
    return res.end();
  }
  if (req.url.startsWith("/v1/images/generations")) {
    if ((body.prompt ?? "").includes("BLOCKME")) {
      res.writeHead(400, { "content-type": "application/json" });
      return res.end(JSON.stringify({ error: { code: "moderation_blocked", message: "Request was rejected by the safety system." } }));
    }
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(JSON.stringify({ created: 1, data: [{ b64_json: PNG }] }));
  }
  res.writeHead(404).end();
}).listen(4010, () => console.log("mock on 4010"));

/* ---------------------------------------------------------------------------------------------
 * Stand-in DHANZ AI API (/dhanz/api/v1/...), with the real one's rules: refresh tokens rotate, and
 * presenting a used one ends the whole session family. Test hooks:
 *   POST /dhanz/__signout?email=…   end every session of that account (like "sign out everywhere")
 *   POST /dhanz/__expire            expire every access token (forces a refresh on the next check)
 *   GET  /dhanz/__log               calls seen (paths and outcomes only, never passwords)
 * ------------------------------------------------------------------------------------------- */
const dz = {
  users: {
    "ana@dhanzai.test": { id: "6c0a4d8e-1111-4a5b-9c1d-0000000000a1", password: "correct horse 1", name: "Ana Dhanz", mfa: null, verified: true },
    "tom@dhanzai.test": { id: "6c0a4d8e-2222-4a5b-9c1d-0000000000b2", password: "correct horse 2", name: "Tom Two-Step", mfa: "totp", verified: true },
    "eve@dhanzai.test": { id: "6c0a4d8e-3333-4a5b-9c1d-0000000000c3", password: "correct horse 3", name: "Eve Email", mfa: "email", verified: true },
    "new@dhanzai.test": { id: "6c0a4d8e-4444-4a5b-9c1d-0000000000d4", password: "correct horse 4", name: "Nia New", mfa: null, verified: false },
  },
  access: new Map(), refresh: new Map(), challenges: new Map(), log: [], n: 0,
};
function dzUser(u) {
  return { id: u.id, email: Object.keys(dz.users).find((k) => dz.users[k] === u), display_name: u.name, role: "user", preferred_model: null,
    routing_policy: "auto", auto_index_web: false, memory_enabled: true, email_verified: u.verified, mfa_enabled: !!u.mfa, mfa_method: u.mfa,
    has_password: true, created_at: "2026-11-01T00:00:00Z" };
}
function dzIssue(u, family = `fam-${++dz.n}`) {
  const access = `dz-at-${++dz.n}-${Math.random().toString(36).slice(2)}`;
  const refresh = `dz-rt-${++dz.n}-${Math.random().toString(36).slice(2)}`;
  dz.access.set(access, { user: u, exp: Date.now() + 15 * 60_000, family });
  dz.refresh.set(refresh, { user: u, family, revoked: false });
  return { access_token: access, refresh_token: refresh, token_type: "bearer", expires_in: 900, user: dzUser(u) };
}
function dzKillFamily(family) {
  for (const [, r] of dz.refresh) if (r.family === family) r.revoked = true;
  for (const [k, a] of dz.access) if (a.family === family) dz.access.delete(k);
}
function dhanz(req, res, raw) {
  const url = new URL(req.url, "http://x");
  const p = url.pathname.replace(/^\/dhanz/, "");
  let b = {};
  try { b = raw ? JSON.parse(raw) : {}; } catch { return json(res, 400, { detail: "bad json" }); }
  const note = (outcome) => dz.log.push({ path: p, outcome, xff: req.headers["x-forwarded-for"] ?? null });
  if (p === "/__log") return json(res, 200, { calls: dz.log });
  if (p === "/__expire") { for (const a of dz.access.values()) a.exp = 0; return json(res, 200, { ok: true }); }
  if (p === "/__signout") {
    const u = dz.users[url.searchParams.get("email")];
    for (const r of dz.refresh.values()) if (r.user === u) dzKillFamily(r.family);
    return json(res, 200, { ok: true });
  }
  if (p === "/api/v1/auth/login" && req.method === "POST") {
    const u = dz.users[String(b.email ?? "").toLowerCase()];
    if (!u || u.password !== b.password) { note("bad-password"); return json(res, 401, { detail: "Incorrect email or password." }); }
    if (u.mfa) {
      const token = `dz-mfa-${++dz.n}-${Math.random().toString(36).slice(2)}xxxxxxxx`;
      dz.challenges.set(token, u);
      note("challenge");
      return json(res, 200, { mfa_required: true, mfa_token: token, expires_in: 300, method: u.mfa, email_hint: u.mfa === "email" ? "e***@dhanzai.test" : null });
    }
    note("tokens");
    return json(res, 200, dzIssue(u));
  }
  if (p === "/api/v1/auth/mfa/verify" && req.method === "POST") {
    const u = dz.challenges.get(b.mfa_token);
    if (!u || b.code !== "123456") { note("bad-code"); return json(res, 401, { detail: "Invalid code." }); }
    dz.challenges.delete(b.mfa_token);
    note("tokens");
    return json(res, 200, dzIssue(u));
  }
  if (p === "/api/v1/auth/refresh" && req.method === "POST") {
    const r = dz.refresh.get(b.refresh_token);
    if (!r || r.revoked) { if (r) dzKillFamily(r.family); note("refresh-refused"); return json(res, 401, { detail: "Session expired. Please sign in again." }); }
    r.revoked = true;
    note("refreshed");
    return json(res, 200, dzIssue(r.user, r.family));
  }
  if (p === "/api/v1/auth/logout" && req.method === "POST") {
    const r = dz.refresh.get(b.refresh_token);
    if (r) dzKillFamily(r.family);
    note("logout");
    res.writeHead(204); return res.end();
  }
  if (p === "/api/v1/users/me" && req.method === "GET") {
    const a = dz.access.get((req.headers.authorization ?? "").replace(/^Bearer /, ""));
    if (!a || a.exp < Date.now()) { note("me-401"); return json(res, 401, { detail: "Not authenticated" }); }
    note("me");
    return json(res, 200, dzUser(a.user));
  }
  return json(res, 404, { detail: "Not Found" });
}

/* Stand-in for the speech-to-text endpoint: checks it got a multipart form with a model and a file. */
/** OpenAI image edits: multipart with model, prompt, size and one `image` or several `image[]` parts. */
function imageEdit(req, res, raw) {
  const field = (name) => new RegExp(`name="${name}"\\r\\n\\r\\n([^\\r]*)`).exec(raw)?.[1];
  const images = [...raw.matchAll(/name="(image(?:\[\])?)"; filename="([^"]+)"\r\nContent-Type: ([^\r]+)/g)].map((m) => ({ field: m[1], filename: m[2], type: m[3] }));
  fs.appendFileSync(LOG, JSON.stringify({ path: "/v1/images/edits", body: { model: field("model"), prompt: field("prompt"), size: field("size"), images }, headers: { authorization: req.headers.authorization } }) + "\n");
  if (!(req.headers["content-type"] ?? "").startsWith("multipart/form-data") || !images.length || !field("prompt")) {
    res.writeHead(400, { "content-type": "application/json" });
    return res.end(JSON.stringify({ error: { message: "Expected a multipart form with prompt and image." } }));
  }
  res.writeHead(200, { "content-type": "application/json" });
  return res.end(JSON.stringify({ created: 1, data: [{ b64_json: PNG }] }));
}

/** OpenAI speech: JSON in, audio bytes out. */
function speech(req, res, raw) {
  const body = raw ? JSON.parse(raw) : {};
  fs.appendFileSync(LOG, JSON.stringify({ path: "/v1/audio/speech", body, headers: { authorization: req.headers.authorization } }) + "\n");
  if (!body.model || !body.voice || !body.input) {
    res.writeHead(400, { "content-type": "application/json" });
    return res.end(JSON.stringify({ error: { message: "model, voice and input are required" } }));
  }
  res.writeHead(200, { "content-type": "audio/mpeg" });
  return res.end(Buffer.from("ID3mock-audio-" + body.input.length));
}

function transcription(req, res, raw) {
  const field = (name) => new RegExp(`name="${name}"\\r\\n\\r\\n([^\\r]*)`).exec(raw)?.[1];
  const file = /name="file"; filename="([^"]+)"\r\nContent-Type: ([^\r]+)/.exec(raw);
  appLog.push({ path: "/v1/audio/transcriptions", model: field("model"), prompt: field("prompt"), filename: file?.[1], type: file?.[2], auth: req.headers.authorization ?? null });
  if (!(req.headers["content-type"] ?? "").startsWith("multipart/form-data") || !field("model") || !file) {
    res.writeHead(400, { "content-type": "application/json" });
    return res.end(JSON.stringify({ error: { message: "Expected a multipart form with model and file." } }));
  }
  res.writeHead(200, { "content-type": "application/json" });
  return res.end(JSON.stringify({ text: "Drop the black fitted on Friday at noon.", languages: [{ code: "en" }] }));
}

/* ---------------------------------------------------------------------------------------------
 * Stand-ins for Google (OAuth + Drive v3), Slack (OAuth v2 + Web API) and Shopify (OAuth + Admin
 * GraphQL), for the app-connection tests. They check what the real services check where it matters
 * for security: PKCE (Google), HMAC-signed callbacks (Shopify), bearer tokens on every API call.
 * GET /__log lists app API calls; POST /__reset clears state.
 */
const appLog = [];
const state = { pkce: new Map(), slackPosts: [], driveDocs: [], shopify: { 101: "<p>Old copy</p>" }, revoked: [] };
const SHOP_SECRET = process.env.MOCK_SHOPIFY_SECRET || "shpss_test";
const json = (res, code, body) => { res.writeHead(code, { "content-type": "application/json" }); res.end(JSON.stringify(body)); };
const redirect = (res, to) => { res.writeHead(302, { location: to }); res.end(); };
const form = (raw) => Object.fromEntries(new URLSearchParams(raw));

function apps(req, res, raw) {
  const url = new URL(req.url, "http://localhost:4010");
  const p = url.pathname;
  const auth = req.headers.authorization || "";
  if (p === "/__health") return json(res, 200, { ok: true });
  if (p === "/__log") return json(res, 200, { calls: appLog, slackPosts: state.slackPosts, driveDocs: state.driveDocs, shopify: state.shopify, revoked: state.revoked });
  if (p === "/__reset") { appLog.length = 0; state.slackPosts.length = 0; state.driveDocs.length = 0; state.revoked.length = 0; state.shopify = { 101: "<p>Old copy</p>" }; return json(res, 200, { ok: true }); }
  appLog.push({ path: p, query: url.search, auth: auth || req.headers["x-shopify-access-token"] || null, body: raw.slice(0, 2000) });

  // Google
  if (p === "/google/o/oauth2/v2/auth") {
    const code = `gcode-${crypto.randomBytes(6).toString("hex")}`;
    state.pkce.set(code, url.searchParams.get("code_challenge"));
    if (url.searchParams.get("code_challenge_method") !== "S256" || !url.searchParams.get("scope")?.includes("drive.readonly")) return json(res, 400, { error: "bad request" });
    return redirect(res, `${url.searchParams.get("redirect_uri")}?${new URLSearchParams({ code, state: url.searchParams.get("state") })}`);
  }
  if (p === "/google/token") {
    const f = form(raw);
    if (f.client_secret !== "test-google-secret") return json(res, 401, { error: "invalid_client" });
    if (f.grant_type === "refresh_token") return f.refresh_token === "g-rt-1" ? json(res, 200, { access_token: "g-at-2", expires_in: 3600, scope: "openid email drive.readonly drive.file" }) : json(res, 400, { error: "invalid_grant" });
    const challenge = state.pkce.get(f.code);
    const ok = challenge && crypto.createHash("sha256").update(f.code_verifier || "").digest("base64url") === challenge;
    if (!ok) return json(res, 400, { error: "invalid_grant" });
    state.pkce.delete(f.code);
    return json(res, 200, { access_token: "g-at-1", refresh_token: "g-rt-1", expires_in: 3600, scope: "openid email https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/drive.file" });
  }
  if (p === "/google/revoke") { state.revoked.push(`google:${url.searchParams.get("token")}`); return json(res, 200, {}); }
  if (p.startsWith("/google/") && !["Bearer g-at-1", "Bearer g-at-2"].includes(auth)) return json(res, 401, { error: { code: 401 } });
  if (p === "/google/userinfo") return json(res, 200, { sub: "g-123", email: "dante@rodrech.com" });
  const files = [
    { id: "doc-lookbook", name: "FW26 lookbook brief", mimeType: "application/vnd.google-apps.document", webViewLink: "https://docs.google.com/document/d/doc-lookbook" },
    { id: "sheet-sizes", name: "Size chart", mimeType: "application/vnd.google-apps.spreadsheet", webViewLink: "https://docs.google.com/spreadsheets/d/sheet-sizes" },
  ];
  if (p === "/google/drive/v3/files") {
    const q = (url.searchParams.get("q") || "").toLowerCase();
    return json(res, 200, { files: files.filter((f) => f.name.toLowerCase().split(" ").some((w) => w.length > 2 && q.includes(w))) });
  }
  if (p === "/google/drive/v3/files/doc-lookbook") return json(res, 200, files[0]);
  if (p === "/google/drive/v3/files/doc-lookbook/export") { res.writeHead(200, { "content-type": "text/plain" }); return res.end("FW26 lookbook brief: shoot on the roof at golden hour with the olive and bone caps."); }
  if (p === "/google/upload/drive/v3/files") {
    const title = /"name":"([^"]+)"/.exec(raw)?.[1];
    state.driveDocs.push({ title, body: raw });
    return json(res, 200, { id: "doc-new", name: title, webViewLink: "https://docs.google.com/document/d/doc-new" });
  }

  // Slack
  if (p === "/slack/oauth/v2/authorize") {
    if (!url.searchParams.get("user_scope")?.includes("search:read")) return json(res, 400, { error: "bad scope" });
    return redirect(res, `${url.searchParams.get("redirect_uri")}?${new URLSearchParams({ code: "scode", state: url.searchParams.get("state") })}`);
  }
  if (p === "/slack/api/oauth.v2.access") {
    const f = form(raw);
    if (f.code !== "scode" || f.client_secret !== "test-slack-secret") return json(res, 200, { ok: false, error: "invalid_code" });
    return json(res, 200, { ok: true, authed_user: { id: "U1", access_token: "xoxp-test", scope: "search:read,channels:read,channels:history,chat:write" }, team: { id: "T1", name: "RODRECH" } });
  }
  if (p.startsWith("/slack/api/") && auth !== "Bearer xoxp-test") return json(res, 200, { ok: false, error: "invalid_auth" });
  if (p === "/slack/api/auth.revoke") { state.revoked.push("slack"); return json(res, 200, { ok: true, revoked: true }); }
  if (p === "/slack/api/conversations.list") return json(res, 200, { ok: true, channels: [{ id: "C0DROPS1", name: "drops" }, { id: "C0GENRL1", name: "general" }] });
  if (p === "/slack/api/search.messages") return json(res, 200, { ok: true, messages: { matches: [{ text: "Drop moved to Friday noon", username: "maya", channel: { name: "drops" }, permalink: "https://rodrech.slack.com/archives/C0DROPS1/p1", ts: "1" }] } });
  if (p === "/slack/api/conversations.history") return json(res, 200, { ok: true, messages: [{ text: "Samples arrive Tuesday", user: "U2", ts: "2" }] });
  if (p === "/slack/api/chat.postMessage") { const f = form(raw); state.slackPosts.push(f); return json(res, 200, { ok: true, channel: f.channel, ts: "3" }); }

  // Shopify
  if (p === "/shop/admin/oauth/authorize") {
    const params = { code: "shcode", shop: "rodrech-test.myshopify.com", state: url.searchParams.get("state"), timestamp: String(Math.floor(Date.now() / 1000)) };
    if (url.searchParams.get("tamper") === "1") params.shop = "evil.myshopify.com";
    const msg = Object.keys(params).sort().map((k) => `${k}=${params[k]}`).join("&");
    const hmac = crypto.createHmac("sha256", SHOP_SECRET).update(msg).digest("hex");
    return redirect(res, `${url.searchParams.get("redirect_uri")}?${new URLSearchParams({ ...params, hmac })}`);
  }
  if (p === "/shop/admin/oauth/access_token") {
    const b = JSON.parse(raw || "{}");
    if (b.code !== "shcode" || b.client_secret !== SHOP_SECRET) return json(res, 400, { error: "invalid" });
    return json(res, 200, { access_token: "shpat_test", scope: "read_products,write_products" });
  }
  if (p.startsWith("/shop/admin/api/") && p.endsWith("/graphql.json")) {
    if (req.headers["x-shopify-access-token"] !== "shpat_test") return json(res, 401, { errors: "Invalid API key or access token" });
    const b = JSON.parse(raw || "{}");
    if (b.query.includes("productUpdate")) {
      const id = b.variables.product.id.split("/").pop();
      state.shopify[id] = b.variables.product.descriptionHtml;
      return json(res, 200, { data: { productUpdate: { product: { id: b.variables.product.id, title: "Olive fitted" }, userErrors: [] } } });
    }
    return json(res, 200, { data: { products: { nodes: [{ id: "gid://shopify/Product/101", title: "Olive fitted", handle: "olive-fitted", status: "ACTIVE", totalInventory: 40, descriptionHtml: state.shopify[101] }] } } });
  }
  return json(res, 404, { error: "not found" });
}
