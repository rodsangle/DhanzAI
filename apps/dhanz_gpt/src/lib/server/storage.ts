import "server-only";
import fs from "node:fs";
import path from "node:path";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/**
 * File bytes. Two drivers behind one interface:
 * - "supabase": private bucket `files`. Browsers upload straight to Storage with a signed upload URL
 *   (FormData PUT, the same request supabase-js `uploadToSignedUrl` makes) and download through
 *   short-lived signed URLs on the Supabase storage domain, a separate origin from the app.
 * - "local": disk under .data/blobs, for development and tests. Uploads go through /api/files/:id/upload.
 */

export const BUCKET = "files";
export type UploadTarget = { url: string; mode: "raw" | "supabase-form" };

export function storageDriver(): "local" | "supabase" {
  const d = process.env.STORAGE_DRIVER ?? (process.env.SUPABASE_SERVICE_ROLE_KEY ? "supabase" : "local");
  if (d !== "local" && d !== "supabase") throw new Error(`Unknown STORAGE_DRIVER ${d}`);
  return d;
}

let admin: SupabaseClient | null = null;
export function supabaseAdmin() {
  if (!admin) {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
    if (!url || !key) throw new Error("NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.");
    admin = createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
  }
  return admin;
}

const LOCAL_DIR = path.join(process.cwd(), ".data", "blobs");
const localPath = (p: string) => {
  const full = path.join(LOCAL_DIR, p);
  if (!full.startsWith(LOCAL_DIR + path.sep)) throw new Error("bad storage path");
  return full;
};

export async function uploadTarget(fileId: string, storagePath: string): Promise<UploadTarget> {
  if (storageDriver() === "local") return { url: `/api/files/${fileId}/upload`, mode: "raw" };
  const { data, error } = await supabaseAdmin().storage.from(BUCKET).createSignedUploadUrl(storagePath);
  if (error || !data) throw new Error(`Couldn't create an upload URL: ${error?.message}`);
  return { url: data.signedUrl, mode: "supabase-form" };
}

export async function putObject(storagePath: string, bytes: Buffer, contentType: string) {
  if (storageDriver() === "local") {
    fs.mkdirSync(path.dirname(localPath(storagePath)), { recursive: true });
    fs.writeFileSync(localPath(storagePath), bytes);
    return;
  }
  const { error } = await supabaseAdmin().storage.from(BUCKET).upload(storagePath, bytes, { contentType, upsert: false });
  if (error) throw new Error(`Upload failed: ${error.message}`);
}

/** Size in bytes, or null if the object isn't there. */
export async function statObject(storagePath: string): Promise<number | null> {
  if (storageDriver() === "local") {
    try {
      return fs.statSync(localPath(storagePath)).size;
    } catch {
      return null;
    }
  }
  const { data, error } = await supabaseAdmin().storage.from(BUCKET).info(storagePath);
  if (error || !data) return null;
  const size = (data as { size?: number; metadata?: { size?: number } }).size ?? (data as { metadata?: { size?: number } }).metadata?.size;
  return typeof size === "number" ? size : null;
}

export async function readObject(storagePath: string): Promise<Buffer | null> {
  if (storageDriver() === "local") {
    try {
      return fs.readFileSync(localPath(storagePath));
    } catch {
      return null;
    }
  }
  const { data, error } = await supabaseAdmin().storage.from(BUCKET).download(storagePath);
  if (error || !data) return null;
  return Buffer.from(await data.arrayBuffer());
}

/** A short-lived URL on the storage domain (supabase driver only). */
export async function signedDownloadUrl(storagePath: string, filename: string, inline: boolean) {
  const { data, error } = await supabaseAdmin()
    .storage.from(BUCKET)
    .createSignedUrl(storagePath, 60, inline ? undefined : { download: filename });
  if (error || !data) throw new Error(`Couldn't sign the download: ${error?.message}`);
  return data.signedUrl;
}

export async function removeObjects(paths: string[]) {
  if (!paths.length) return;
  if (storageDriver() === "local") {
    for (const p of paths) fs.rmSync(localPath(p), { force: true });
    return;
  }
  for (let i = 0; i < paths.length; i += 100) {
    const { error } = await supabaseAdmin().storage.from(BUCKET).remove(paths.slice(i, i + 100));
    if (error) throw new Error(`Couldn't delete files: ${error.message}`);
  }
}
