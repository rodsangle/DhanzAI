// Space (S12) shapes shared by the server and the browser.

export type Level = "view" | "comment" | "edit";
export type SpaceSummary = {
  id: string;
  name: string;
  is_personal: boolean;
  is_owner: boolean;
  owner_name: string;
  everyone_level: Level | null;
  level: Level | null; // null: you only see pages someone shared inside it
};
export type PageNode = { id: string; space_id: string; parent_page_id: string | null; title: string; position: string; level: Level };
export type PageDoc = { type: "doc"; content?: unknown[] };
export type PageDetail = {
  page: {
    id: string; space_id: string; parent_page_id: string | null; title: string; doc: PageDoc; text: string; version: number;
    updated_at: string; updated_by_name: string | null; source_conversation_id: string | null;
  };
  space: { id: string; name: string; is_personal: boolean; is_owner: boolean };
  level: Level;
  breadcrumbs: { id: string; title: string }[];
  children: { id: string; title: string }[];
};
export type AccessEntry = { id: string; user_id: string; name: string; email: string; level: Level; inherited_from: string | null };
export type CommentRow = {
  id: string; page_id: string; parent_comment_id: string | null; author_id: string | null; author_name: string | null;
  quote: string | null; body: string; resolved_at: string | null; resolved_by_name: string | null; created_at: string; mine: boolean;
};

