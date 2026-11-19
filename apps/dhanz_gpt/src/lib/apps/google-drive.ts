import "server-only";
import { AppError, call, str, testBase, type AppProvider } from "./types";

/**
 * Google Drive through the Drive API v3 with the person's own Google sign-in (OAuth 2.0, PKCE,
 * offline access). Scopes: drive.readonly to search and read, drive.file to create Docs (only
 * files this app makes), plus openid/email to show which account is connected.
 */
const base = () => {
  const t = testBase();
  return {
    authorize: t ? `${t}/google/o/oauth2/v2/auth` : "https://accounts.google.com/o/oauth2/v2/auth",
    token: t ? `${t}/google/token` : "https://oauth2.googleapis.com/token",
    revoke: t ? `${t}/google/revoke` : "https://oauth2.googleapis.com/revoke",
    userinfo: t ? `${t}/google/userinfo` : "https://openidconnect.googleapis.com/v1/userinfo",
    api: t ? `${t}/google` : "https://www.googleapis.com",
  };
};
const SCOPES = ["openid", "email", "https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/drive.file"];
const READABLE: Record<string, string> = {
  "application/vnd.google-apps.document": "text/plain",
  "application/vnd.google-apps.spreadsheet": "text/csv",
  "application/vnd.google-apps.presentation": "text/plain",
};
const q = (s: string) => s.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
const auth = (token: string) => ({ Authorization: `Bearer ${token}` });

async function tokenRequest(body: Record<string, string>) {
  const res = await call(base().token, {
    what: "Google",
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: process.env.GOOGLE_CLIENT_ID!, client_secret: process.env.GOOGLE_CLIENT_SECRET!, ...body }),
  });
  const j = (await res.json()) as { access_token: string; refresh_token?: string; expires_in?: number; scope?: string };
  return { access_token: j.access_token, refresh_token: j.refresh_token ?? null, expires_in: j.expires_in ?? null, scopes: (j.scope ?? "").split(" ").filter(Boolean) };
}

export const googleDrive: AppProvider = {
  id: "google_drive",
  name: "Google Drive",
  mentions: ["Google Drive", "Drive"],
  description: "Find and read Docs, Sheets and files in your Drive, and save new Docs.",
  can: ["Search your Drive", "Read Docs, Sheets, Slides and text files", "Create a Google Doc (asks first)"],
  configured: () => !!(process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET),
  authorizeUrl: ({ state, redirectUri, codeChallenge }) =>
    `${base().authorize}?${new URLSearchParams({
      client_id: process.env.GOOGLE_CLIENT_ID!, redirect_uri: redirectUri, response_type: "code", scope: SCOPES.join(" "),
      access_type: "offline", prompt: "consent", include_granted_scopes: "true", state, code_challenge: codeChallenge, code_challenge_method: "S256",
    })}`,
  async exchange({ code, redirectUri, codeVerifier }) {
    const tokens = await tokenRequest({ grant_type: "authorization_code", code, redirect_uri: redirectUri, code_verifier: codeVerifier });
    const me = (await (await call(base().userinfo, { what: "Google", headers: auth(tokens.access_token) })).json()) as { sub: string; email?: string };
    return { tokens, account: { id: me.sub, label: me.email ?? "Google account" } };
  },
  refresh: (refreshToken) => tokenRequest({ grant_type: "refresh_token", refresh_token: refreshToken }),
  async revoke(token) {
    await fetch(`${base().revoke}?${new URLSearchParams({ token })}`, { method: "POST", signal: AbortSignal.timeout(10_000) }).catch(() => {});
  },
  tools: [
    {
      name: "drive_search",
      description: "Search the person's Google Drive by words in file names and contents. Returns up to 10 files with id, name, type and link.",
      input_schema: { type: "object", properties: { query: { type: "string", description: "Words to look for" } }, required: ["query"] },
      importance: "read",
      describe: (i) => `Searched Google Drive for “${str(i.query, 80)}”`,
      preview: (i) => [{ label: "Search for", value: str(i.query, 200) }],
      async run({ token }, i) {
        const words = str(i.query, 200).trim();
        if (!words) throw new AppError("Say what to search for.", 400);
        const params = new URLSearchParams({
          q: `(name contains '${q(words)}' or fullText contains '${q(words)}') and trashed = false`,
          fields: "files(id,name,mimeType,modifiedTime,webViewLink)",
          pageSize: "10",
          supportsAllDrives: "true",
          includeItemsFromAllDrives: "true",
        });
        const j = (await (await call(`${base().api}/drive/v3/files?${params}`, { what: "Google Drive", headers: auth(token) })).json()) as { files: unknown[] };
        return { result: JSON.stringify(j.files ?? []), summary: `${j.files?.length ?? 0} files found` };
      },
    },
    {
      name: "drive_read_file",
      description: "Read the text of one Google Drive file by id: Docs and Slides as text, Sheets as CSV, plain text files as they are.",
      input_schema: { type: "object", properties: { file_id: { type: "string" } }, required: ["file_id"] },
      importance: "read",
      describe: (i) => `Read a file from Google Drive (${str(i.file_id, 40)})`,
      preview: (i) => [{ label: "File", value: str(i.file_id, 100) }],
      async run({ token }, i) {
        const id = encodeURIComponent(str(i.file_id, 200));
        const meta = (await (await call(`${base().api}/drive/v3/files/${id}?fields=id,name,mimeType,size&supportsAllDrives=true`, { what: "Google Drive", headers: auth(token) })).json()) as { name: string; mimeType: string };
        const exportAs = READABLE[meta.mimeType];
        let text: string;
        if (exportAs) text = await (await call(`${base().api}/drive/v3/files/${id}/export?mimeType=${encodeURIComponent(exportAs)}`, { what: "Google Drive", headers: auth(token) })).text();
        else if (/^text\/|json|csv|xml/.test(meta.mimeType)) text = await (await call(`${base().api}/drive/v3/files/${id}?alt=media`, { what: "Google Drive", headers: auth(token) })).text();
        else return { result: JSON.stringify({ name: meta.name, error: `Can't read ${meta.mimeType} files as text.` }), summary: `Couldn't read ${meta.name}` };
        return { result: JSON.stringify({ name: meta.name, text: text.slice(0, 60_000), truncated: text.length > 60_000 }), summary: `Read ${meta.name}` };
      },
    },
    {
      name: "drive_create_doc",
      description: "Create a new Google Doc in the person's Drive with a title and plain-text content. Returns its link.",
      input_schema: { type: "object", properties: { title: { type: "string" }, content: { type: "string" } }, required: ["title", "content"] },
      importance: "change",
      describe: (i) => `Created a Google Doc, “${str(i.title, 80)}”`,
      preview: (i) => [{ label: "Title", value: str(i.title, 200) }, { label: "Content", value: str(i.content, 600) }],
      async run({ token }, i) {
        const boundary = `dhanz-gpt-${Date.now().toString(36)}`;
        const meta = JSON.stringify({ name: str(i.title, 200) || "Untitled", mimeType: "application/vnd.google-apps.document" });
        const body = `--${boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${meta}\r\n--${boundary}\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\n${str(i.content, 200_000)}\r\n--${boundary}--`;
        const j = (await (await call(`${base().api}/upload/drive/v3/files?uploadType=multipart&fields=id,name,webViewLink&supportsAllDrives=true`, {
          what: "Google Drive", method: "POST", headers: { ...auth(token), "Content-Type": `multipart/related; boundary=${boundary}` }, body,
        })).json()) as { id: string; name: string; webViewLink?: string };
        return { result: JSON.stringify(j), summary: `Created ${j.name}` };
      },
    },
  ],
};
