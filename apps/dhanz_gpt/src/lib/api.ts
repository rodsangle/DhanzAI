"use client";

import type {
  AssistantCapability, AssistantDetail, Memory,
  ConversationDetail, ConversationListItem, FileRow, ImageGeneration, Message, Personalization, Profile, ProjectDetail,
  SearchResult, Workspace,
} from "@/lib/data/types";
import type { TaskItem } from "@/lib/data/tasks";
import type { Schedule } from "@/lib/schedule";

export type TaskInputClient = { title: string; prompt: string; schedule: Schedule; timezone: string; notify: ("push" | "email")[]; model?: string | null };

export type AssistantInput = {
  name: string; description?: string; instructions?: string; starters?: string[];
  recommended_model?: string | null; capabilities?: AssistantCapability[]; visibility?: "private" | "workspace"; file_ids?: string[];
};

/** Typed client for /api. Screens call only these; the backend swap changes the routes' insides, not this file. */

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: init?.json !== undefined ? { "Content-Type": "application/json", ...init?.headers } : init?.headers,
    body: init?.json !== undefined ? JSON.stringify(init.json) : init?.body,
  });
  if (!res.ok) {
    let msg = "Something went wrong. Try again.";
    try {
      msg = ((await res.json()) as { error?: string }).error ?? msg;
    } catch {}
    if (res.status === 401 && typeof window !== "undefined" && !location.pathname.startsWith("/login")) {
      location.href = `/login?next=${encodeURIComponent(location.pathname)}`;
    }
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}

export const fetcher = <T,>(path: string) => req<T>(path);

export type Me = {
  profile: Profile;
  workspace: Workspace;
  role: string;
  usage: { messages: number; images: number; limits: { messages: number; images: number } };
  features: { webSearch: "auto" | "manual" | "off"; email: boolean; push: boolean; dictation: boolean };
  unseen_task_runs: number;
};

export const api = {
  me: () => req<Me>("/api/me"),
  signIn: (email: string) => req<{ ok: true; name: string }>("/api/auth/dev-login", { method: "POST", json: { email } }),
  signOut: (everywhere = false) => req(`/api/auth/signout${everywhere ? "?scope=global" : ""}`, { method: "POST" }),
  deleteAccount: () => req("/api/account", { method: "DELETE", json: { confirm: "DELETE" } }),

  conversations: (archived = false) => req<ConversationListItem[]>(`/api/conversations${archived ? "?archived=1" : ""}`),
  conversation: (id: string) => req<ConversationDetail>(`/api/conversations/${id}`),
  updateConversation: (id: string, patch: { title?: string; archived?: boolean; project_id?: string | null; current_leaf_id?: string; model?: string }) =>
    req(`/api/conversations/${id}`, { method: "PATCH", json: patch }),
  deleteConversation: (id: string) => req(`/api/conversations/${id}`, { method: "DELETE" }),
  share: (id: string) => req<{ slug: string; updated_at: string; visibility: string }>(`/api/conversations/${id}/share`, { method: "POST" }),
  deleteShare: (slug: string) => req(`/api/share/${slug}`, { method: "DELETE" }),

  message: (id: string) => req<Message>(`/api/messages/${id}`),
  feedback: (id: string, feedback: -1 | 1 | null) => req(`/api/messages/${id}`, { method: "PATCH", json: { feedback } }),
  stop: (id: string) => req(`/api/messages/${id}/stop`, { method: "POST" }),

  projects: () => req<{ id: string; name: string; shared: boolean }[]>("/api/projects"),
  project: (id: string) => req<ProjectDetail>(`/api/projects/${id}`),
  createProject: (name: string, instructions = "") => req<{ id: string }>("/api/projects", { method: "POST", json: { name, instructions } }),
  updateProject: (id: string, patch: { name?: string; instructions?: string }) => req(`/api/projects/${id}`, { method: "PATCH", json: patch }),
  deleteProject: (id: string) => req(`/api/projects/${id}`, { method: "DELETE" }),
  addProjectFile: (id: string, file_id: string) => req(`/api/projects/${id}/files`, { method: "POST", json: { file_id } }),
  removeProjectFile: (id: string, file_id: string) => req(`/api/projects/${id}/files?file_id=${file_id}`, { method: "DELETE" }),
  setProjectMember: (id: string, user_id: string, role: "viewer" | "editor" | null) =>
    req(`/api/projects/${id}/members`, { method: "POST", json: { user_id, role } }),
  members: () => req<(Profile & { role: string })[]>("/api/members"),

  files: (trashed = false) => req<FileRow[]>(`/api/files${trashed ? "?trashed=1" : ""}`),
  trashFile: (id: string, trashed: boolean) => req(`/api/files/${id}`, { method: "PATCH", json: { trashed } }),
  search: (q: string) => req<SearchResult[]>(`/api/search?q=${encodeURIComponent(q)}`),
  personalization: () => req<Personalization>("/api/personalization"),
  savePersonalization: (p: Partial<Personalization>) => req<Personalization>("/api/personalization", { method: "PUT", json: p }),
  requestExport: () => req<{ id: string; status: "queued" | "running" | "ready" | "failed" | "expired"; created_at: string; expires_at: string | null }>("/api/account/export", { method: "POST" }),
  deleteAllChats: () => req<{ deleted: number }>("/api/conversations/delete-all", { method: "POST", json: { confirm: true } }),
  createAssistant: (a: AssistantInput) => req<AssistantDetail>("/api/assistants", { method: "POST", json: a }),
  updateAssistant: (id: string, a: AssistantInput) => req<AssistantDetail>(`/api/assistants/${id}`, { method: "PUT", json: a }),
  restoreAssistant: (id: string, version: number) => req<AssistantDetail>(`/api/assistants/${id}/restore`, { method: "POST", json: { version } }),
  deleteAssistant: (id: string) => req(`/api/assistants/${id}`, { method: "DELETE" }),
  createTask: (t: TaskInputClient) => req<TaskItem>("/api/tasks", { method: "POST", json: t }),
  updateTask: (id: string, t: TaskInputClient) => req<TaskItem>(`/api/tasks/${id}`, { method: "PUT", json: t }),
  pauseTask: (id: string, paused: boolean) => req<TaskItem>(`/api/tasks/${id}/pause`, { method: "POST", json: { paused } }),
  runTask: (id: string) => req<{ run_id: string }>(`/api/tasks/${id}/run`, { method: "POST" }),
  deleteTask: (id: string) => req(`/api/tasks/${id}`, { method: "DELETE" }),
  markTasksSeen: () => req("/api/tasks/seen", { method: "POST" }),
  setAppPermission: (id: string, permission_level: string) => req(`/api/apps/connections/${id}`, { method: "PATCH", json: { permission_level } }),
  disconnectApp: (id: string) => req(`/api/apps/connections/${id}`, { method: "DELETE" }),
  memory: () => req<Memory>("/api/memory"),
  saveMemory: (body: string) => req<Memory>("/api/memory", { method: "PUT", json: { body } }),
  refreshMemory: () => req<Memory>("/api/memory/refresh", { method: "POST" }),
  deleteMemory: () => req("/api/memory", { method: "DELETE" }),
  updateProfile: (p: { theme?: "system" | "light" | "dark"; locale?: string }) => req<Profile>("/api/profile", { method: "PATCH", json: p }),
  images: () => req<ImageGeneration[]>("/api/images"),
  shares: () => req<{ slug: string; title: string; updated_at: string; conversation_id: string }[]>("/api/shares"),
};

export const fileUrl = (id: string, inline = true) => `/api/files/${id}/download${inline ? "?inline=1" : ""}`;

/** Three-step upload with progress: reserve → PUT bytes → complete. */
export async function uploadFile(file: File, onProgress: (pct: number) => void, opts: { temporary?: boolean } = {}) {
  const { file: row, upload_url, upload_mode } = await req<{ file: FileRow; upload_url: string; upload_mode: "raw" | "supabase-form" }>("/api/files", {
    method: "POST",
    json: { name: file.name, mime: file.type, bytes: file.size, temporary: opts.temporary },
  });
  await new Promise<void>((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("PUT", upload_url);
    x.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    x.onload = () => (x.status < 300 ? resolve() : reject(new ApiError(x.status, "Upload failed. Try again.")));
    x.onerror = () => reject(new ApiError(0, "Upload failed. Check your connection."));
    if (upload_mode === "supabase-form") {
      // Same request supabase-js uploadToSignedUrl makes: multipart form, file under an empty field name.
      const form = new FormData();
      form.append("cacheControl", "3600");
      form.append("", file);
      x.setRequestHeader("x-upsert", "false");
      x.send(form);
    } else {
      x.send(file);
    }
  });
  return req<FileRow>(`/api/files/${row.id}/complete`, { method: "POST" });
}
