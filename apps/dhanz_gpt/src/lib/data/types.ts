// Row types mirroring replica/schema.sql. The fake store and the future Supabase
// layer both return these shapes, so screens never change when the backend does.

export type UUID = string;
export type ISODate = string;

export type Role = "owner" | "admin" | "member";

export interface Profile {
  id: UUID;
  email: string;
  name: string;
  avatar_url: string | null;
  theme: "system" | "light" | "dark";
  locale: string;
}

export interface Membership {
  id: UUID;
  workspace_id: UUID;
  user_id: UUID;
  role: Role;
}

export interface Workspace {
  id: UUID;
  name: string;
  allowed_email_domain: string | null;
  settings: { public_links_allowed?: boolean };
}

export interface Project {
  id: UUID;
  workspace_id: UUID;
  owner_id: UUID;
  name: string;
  instructions: string;
  memory_mode: "default" | "project_only";
  archived_at: ISODate | null;
  created_at: ISODate;
  updated_at: ISODate;
}

export interface ProjectMember {
  id: UUID;
  project_id: UUID;
  user_id: UUID;
  role: "viewer" | "editor";
}

export type ContentBlock =
  | { type: "text"; text: string }
  | { type: "image"; file_id: UUID; alt: string }
  | { type: "file_ref"; file_id: UUID; name: string; mime: string }
  | { type: "citation"; title: string; url: string }
  | { type: "sources"; items: Source[] }
  /** App actions taken while answering ("Searched Google Drive for …"). */
  | { type: "tool_activity"; items: { app: string; text: string; ok: boolean }[] }
  /** An app action waiting for (or past) the person's go-ahead. */
  | { type: "approval"; approval_id: UUID; app: string; action: string; fields: { label: string; value: string }[]; status: "pending" | "approved" | "denied" | "expired" };

/** What an answer drew on, listed under it: saved memory, an earlier chat, or a web page. */
export type Source =
  | { kind: "memory" }
  | { kind: "chat"; conversation_id: UUID; title: string }
  | { kind: "web"; title: string; url: string };

export interface Memory {
  body: string;
  refreshed_at: ISODate | null;
  updated_at: ISODate | null;
}

export type MessageStatus = "streaming" | "complete" | "stopped" | "error";

export interface Message {
  id: UUID;
  conversation_id: UUID;
  parent_id: UUID | null;
  user_id: UUID | null;
  role: "user" | "assistant" | "tool" | "system";
  content: ContentBlock[];
  text: string;
  model: string | null;
  status: MessageStatus;
  error: string | null;
  feedback: -1 | 1 | null;
  created_at: ISODate;
  updated_at: ISODate;
}

export interface Conversation {
  id: UUID;
  workspace_id: UUID;
  user_id: UUID;
  project_id: UUID | null;
  assistant_id: UUID | null;
  title: string;
  model: string;
  kind: "chat" | "research" | "agent" | "task_run";
  is_temporary: boolean;
  archived_at: ISODate | null;
  current_leaf_id: UUID | null;
  last_message_at: ISODate;
  created_at: ISODate;
  updated_at: ISODate;
}

export interface FileRow {
  id: UUID;
  workspace_id: UUID;
  owner_id: UUID;
  name: string;
  mime: string;
  bytes: number;
  storage_path: string;
  source: "upload" | "generated" | "drive" | "agent" | "audio_transcript";
  status: "uploading" | "processing" | "ready" | "error";
  error: string | null;
  favorite: boolean;
  is_temporary: boolean;
  deleted_at: ISODate | null;
  /** Text read from the file at upload (text, PDF, DOCX); null if it has none. Never sent to the browser. */
  extracted_text?: string | null;
  /** Estimated tokens in extracted_text. */
  token_count?: number | null;
  created_at: ISODate;
  updated_at: ISODate;
}

export interface Personalization {
  user_id: UUID;
  about_you: string;
  response_style: string;
  personality: string;
  memory_enabled: boolean;
  reference_chat_history: boolean;
}

export interface SharedLink {
  id: UUID;
  owner_id: UUID;
  conversation_id: UUID | null;
  slug: string;
  snapshot: { title: string; messages: Pick<Message, "id" | "role" | "content" | "text">[]; shared_at: ISODate };
  visibility: "workspace" | "public";
  created_at: ISODate;
  updated_at: ISODate;
}

export interface ImageGeneration {
  id: UUID;
  user_id: UUID;
  conversation_id: UUID | null;
  message_id: UUID | null;
  prompt: string;
  aspect_ratio: string;
  output_file_id: UUID | null;
  provider: string;
  status: "queued" | "running" | "succeeded" | "failed" | "refused";
  created_at: ISODate;
}

export interface UsageEvent {
  id: UUID;
  user_id: UUID;
  metric: "message" | "image" | "voice_second";
  quantity: number;
  idempotency_key: string | null;
  created_at: ISODate;
}

/* ---------------------------------------------------------------- API views */

export interface ConversationListItem {
  id: UUID;
  title: string;
  project_id: UUID | null;
  last_message_at: ISODate;
  streaming: boolean;
  archived: boolean;
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: Message[];
  project: Pick<Project, "id" | "name"> | null;
  /** The assistant this chat runs with, if it still exists and the viewer can see it. */
  assistant: Pick<Assistant, "id" | "name" | "starters" | "capabilities"> | null;
  share: Pick<SharedLink, "slug" | "updated_at" | "visibility"> | null;
  can_edit: boolean;
}

export type AssistantCapability = "web_search" | "image_generation";

export interface Assistant {
  id: UUID;
  workspace_id: UUID;
  owner_id: UUID | null;
  name: string;
  description: string;
  instructions: string;
  starters: string[];
  recommended_model: string | null;
  capabilities: AssistantCapability[];
  visibility: "private" | "workspace";
  current_version: number;
  created_at: ISODate;
  updated_at: ISODate;
}

export interface AssistantListItem extends Pick<Assistant, "id" | "name" | "description" | "visibility" | "owner_id" | "updated_at"> {
  owner_name: string | null;
  can_edit: boolean;
}

export interface AssistantDetail extends Assistant {
  owner_name: string | null;
  files: Pick<FileRow, "id" | "name" | "mime" | "bytes">[];
  can_edit: boolean;
  versions: { version: number; created_at: ISODate; created_by_name: string | null }[];
}

export interface ProjectDetail {
  project: Project;
  conversations: ConversationListItem[];
  files: FileRow[];
  members: (ProjectMember & { name: string; email: string })[];
  can_edit: boolean;
  is_owner: boolean;
}

export interface SearchResult {
  kind: "chat" | "message" | "file" | "project" | "page";
  id: UUID;
  title: string;
  snippet?: string;
  href: string;
}

export const MODELS = [
  { id: "claude-sonnet-5-5", label: "Balanced", description: "Everyday writing, ideas and planning" },
  { id: "claude-opus-5-5", label: "Deep", description: "Thinks longer for hard problems" },
  { id: "claude-haiku-5-5", label: "Fast", description: "Quick answers and small edits" },
] as const;
export type ModelId = (typeof MODELS)[number]["id"];
export const DEFAULT_MODEL: ModelId = "claude-sonnet-5-5";

export const LIMITS = {
  fileBytes: 512 * 1024 * 1024,
  attachmentsPerMessage: 10,
  messagesPerDay: 500,
  imagesPerDay: 100,
  titleMax: 200,
  projectNameMax: 120,
  instructionsMax: 20000,
} as const;
