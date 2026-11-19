"use client";

import { BRAND } from "@/lib/brand";
import {
  ArrowUp, AudioLines, Check, ChevronDown, FileText, Lightbulb, Loader2, Globe, ImageIcon, ImagePlus, Library, Paperclip, Plus, RectangleHorizontal,
  RectangleVertical, Square, SquareDashed, Telescope, X,
} from "lucide-react";
import { IMAGE_SIZES, type ImageSize } from "@/lib/data/types";
import { forwardRef, useId, useImperativeHandle, useLayoutEffect, useRef, useState, type ChangeEvent, type ClipboardEvent, type KeyboardEvent } from "react";
import { cn, focusRing } from "@/lib/cn";
import { IconButton } from "@/components/ui/button";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/overlays";
import type { DictationState } from "@/lib/dictation";

export type DictationControls = { state: DictationState; start: () => void; stop: () => void; cancel: () => void };

const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

export type Attachment = {
  id: string;
  name: string;
  kind: "image" | "document" | "audio" | "paste";
  status: "uploading" | "ready" | "error";
  progress?: number;
  meta?: string;
  error?: string;
  fileId?: string;
  previewUrl?: string;
};

export const LONG_PASTE_CHARS = 5000;

export function AttachmentChip({ a, onRemove }: { a: Attachment; onRemove?: () => void }) {
  const Icon = a.kind === "audio" ? AudioLines : FileText;
  const state = a.status === "uploading" ? `uploading ${a.progress ?? 0}%` : a.status === "error" ? "failed" : "ready";
  return (
    <li
      className={cn(
        "group relative flex h-12 max-w-60 items-center gap-2.5 rounded-md bg-surface-muted pl-2 pr-3",
        a.status === "error" && "outline outline-1 outline-danger",
      )}
    >
      <span aria-hidden className="flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-sm bg-surface-active text-muted">
        {a.status === "uploading" ? (
          <svg viewBox="0 0 20 20" className="size-5 -rotate-90">
            <circle cx="10" cy="10" r="8" fill="none" stroke="var(--border-strong)" strokeWidth="2.5" />
            <circle
              cx="10" cy="10" r="8" fill="none" stroke="var(--accent)" strokeWidth="2.5"
              strokeDasharray={50.3} strokeDashoffset={50.3 * (1 - (a.progress ?? 0) / 100)} strokeLinecap="round"
            />
          </svg>
        ) : a.previewUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={a.previewUrl} alt="" className="size-full object-cover" />
        ) : (
          <Icon className="size-4" />
        )}
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-sm text-fg">{a.name}</span>
        <span className={cn("truncate text-xs", a.status === "error" ? "text-danger-text" : "text-muted")}>
          {a.status === "error" ? a.error ?? "Upload failed" : a.meta}
        </span>
      </span>
      <span className="sr-only">, {state}</span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${a.name}`}
          className={cn(
            "absolute -right-1.5 -top-1.5 flex size-5 items-center justify-center rounded-full bg-fg text-bg",
            "opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100",
            focusRing,
          )}
        >
          <X className="size-3" />
        </button>
      )}
    </li>
  );
}

export type ComposerHandle = { focus: () => void };

/** A "/" command: a tool to turn on, or an assistant or project to open. */
export type SlashCommand = {
  id: string;
  label: string;
  group: "Tools" | "Assistants" | "Projects";
  hint?: string;
  run: () => void;
};

/** Does the label match what was typed after "/"? Any word may start the match. */
export function matchesCommand(label: string, query: string) {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const l = label.toLowerCase();
  return l.startsWith(q) || l.split(/\s+/).some((w) => w.startsWith(q));
}

export const Composer = forwardRef<ComposerHandle, {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop?: () => void;
  attachments?: Attachment[];
  onAddFiles?: (files: File[]) => void;
  onRemoveAttachment?: (id: string) => void;
  streaming?: boolean;
  disabled?: boolean;
  disabledReason?: string;
  placeholder?: string;
  variant?: "home" | "thread";
  imageMode?: boolean;
  onImageMode?: (on: boolean) => void;
  /** Absent = not chosen yet (shown as Square, the default for new images). */
  imageSize?: ImageSize;
  onImageSize?: (size: ImageSize) => void;
  /** Think longer for the next message. Absent hides it. */
  think?: boolean;
  onThink?: (on: boolean) => void;
  onAddFromLibrary?: () => void;
  /** Apps offered after @ (connected ones are usable; others get a "connect it first" answer). */
  mentionApps?: { label: string; connected: boolean }[];
  /** Offered after "/" at the start of the message. */
  commands?: SlashCommand[];
  /** null hides search (turned off for the workspace). */
  searchMode?: boolean | null;
  onSearchMode?: (on: boolean) => void;
  /** null or absent hides Dictate (no speech service set up). */
  dictation?: DictationControls | null;
  onLastMessageEdit?: () => void;
}>(function Composer(
  {
    value, onChange, onSend, onStop, attachments = [], onAddFiles, onRemoveAttachment, streaming, disabled, disabledReason,
    placeholder = "Ask, draft, or paste copy to edit", variant = "thread", imageMode, onImageMode, imageSize = "square", onImageSize, think, onThink, searchMode, onSearchMode, onAddFromLibrary, mentionApps = [], commands = [], dictation, onLastMessageEdit,
  },
  ref,
) {
  const id = useId();
  const ta = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  useImperativeHandle(ref, () => ({ focus: () => ta.current?.focus() }), []);

  const uploading = attachments.some((a) => a.status === "uploading");
  const hasError = attachments.some((a) => a.status === "error");
  const canSend = !disabled && !streaming && !uploading && !hasError && (value.trim().length > 0 || attachments.length > 0);

  useLayoutEffect(() => {
    const el = ta.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 12 * 24)}px`;
  }, [value]);

  // Suggestions: "@" offers apps anywhere; "/" at the start of the message offers commands.
  // Arrows move, Enter or Tab picks, Escape closes.
  type Option = { key: string; label: string; aside?: string; group?: string; pick: () => void };
  const [suggest, setSuggest] = useState<{ kind: "mention" | "command"; start: number; query: string; active: number } | null>(null);
  const options: Option[] = !suggest
    ? []
    : suggest.kind === "mention"
      ? mentionApps
          .filter((a) => a.label.toLowerCase().startsWith(suggest.query.toLowerCase()))
          .map((a) => ({ key: a.label, label: `@${a.label}`, aside: a.connected ? undefined : "Not connected", pick: () => pickMention(a.label) }))
      : commands
          .filter((c) => matchesCommand(c.label, suggest.query) || (!!c.hint?.startsWith("/") && matchesCommand(c.hint.slice(1), suggest.query)))
          .slice(0, 8)
          .map((c) => ({ key: c.id, label: c.label, aside: c.hint, group: c.group, pick: () => pickCommand(c) }));
  const listId = `${id}-suggest`;
  function onTextChange(e: ChangeEvent<HTMLTextAreaElement>) {
    onChange(e.target.value);
    const caret = e.target.selectionStart ?? e.target.value.length;
    const upto = e.target.value.slice(0, caret);
    const slash = /^\/([^\n/]{0,30})$/.exec(upto);
    const at = /(^|\s)@([A-Za-z][A-Za-z ]{0,19})?$/.exec(upto);
    if (slash && commands.length) setSuggest({ kind: "command", start: 0, query: slash[1], active: 0 });
    else if (at && mentionApps.length) setSuggest({ kind: "mention", start: caret - (at[2]?.length ?? 0) - 1, query: at[2] ?? "", active: 0 });
    else setSuggest(null);
  }
  function placeCaret(pos: number) {
    requestAnimationFrame(() => {
      ta.current?.focus();
      ta.current?.setSelectionRange(pos, pos);
    });
  }
  function pickMention(label: string) {
    if (!suggest) return;
    const caret = ta.current?.selectionStart ?? value.length;
    const before = `${value.slice(0, suggest.start)}@${label} `;
    onChange(before + value.slice(caret));
    setSuggest(null);
    placeCaret(before.length);
  }
  function pickCommand(c: SlashCommand) {
    const caret = ta.current?.selectionStart ?? value.length;
    // The "/query" is the command, not part of the message.
    onChange(value.slice(caret).replace(/^\s+/, ""));
    setSuggest(null);
    c.run();
    placeCaret(0);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (suggest && options.length) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const step = e.key === "ArrowDown" ? 1 : -1;
        setSuggest({ ...suggest, active: (suggest.active + step + options.length) % options.length });
        return;
      }
      if ((e.key === "Enter" && !e.shiftKey) || e.key === "Tab") {
        e.preventDefault();
        options[Math.min(suggest.active, options.length - 1)].pick();
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setSuggest(null);
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (canSend) onSend();
    } else if (e.key === "Escape" && streaming) {
      e.preventDefault();
      onStop?.();
    } else if (e.key === "ArrowUp" && !value && onLastMessageEdit) {
      e.preventDefault();
      onLastMessageEdit();
    }
  }

  function onPaste(e: ClipboardEvent<HTMLTextAreaElement>) {
    if (!onAddFiles) return;
    const files = Array.from(e.clipboardData.files);
    if (files.length) {
      e.preventDefault();
      onAddFiles(files);
      return;
    }
    const text = e.clipboardData.getData("text/plain");
    if (text.length > LONG_PASTE_CHARS) {
      e.preventDefault();
      onAddFiles([new File([text], "Pasted text.txt", { type: "text/plain" })]);
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSend) onSend();
      }}
      className={cn(
        "mx-auto flex w-full max-w-[var(--composer-max-width)] flex-col gap-2 rounded-xl border border-border-input bg-surface-raised p-3 shadow-sm",
        "has-[textarea:focus-visible]:outline-2 has-[textarea:focus-visible]:outline-offset-1 has-[textarea:focus-visible]:outline-focus has-[textarea:focus-visible]:outline-solid",
        variant === "home" && "min-h-28",
        disabled && "opacity-60",
      )}
    >
      {attachments.length > 0 && (
        <ul aria-label="Attachments" className="flex flex-wrap gap-2 pt-1">
          {attachments.map((a) => (
            <AttachmentChip key={a.id} a={a} onRemove={onRemoveAttachment ? () => onRemoveAttachment(a.id) : undefined} />
          ))}
        </ul>
      )}
      {suggest && options.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          aria-label={suggest.kind === "mention" ? "Apps" : "Commands"}
          className="flex max-h-72 flex-col gap-0.5 overflow-y-auto rounded-lg border border-border bg-surface-raised p-1 shadow-sm"
        >
          {options.map((o, i) => (
            <li
              key={o.key}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === suggest.active}
              onMouseDown={(e) => e.preventDefault()}
              onClick={o.pick}
              className={cn("flex cursor-pointer items-center justify-between gap-3 rounded-md px-2.5 py-1.5 text-sm", i === suggest.active && "bg-surface-active")}
            >
              <span className="min-w-0 truncate">{o.label}</span>
              {o.aside && <span className="shrink-0 text-xs text-muted">{o.aside}</span>}
            </li>
          ))}
        </ul>
      )}
      <label htmlFor={id} className="sr-only">Message {BRAND.name}</label>
      <textarea
        ref={ta}
        id={id}
        rows={1}
        value={value}
        disabled={disabled}
        onChange={onTextChange}
        onKeyDown={onKeyDown}
        onBlur={() => setSuggest(null)}
        aria-autocomplete={mentionApps.length || commands.length ? "list" : undefined}
        aria-controls={suggest && options.length ? listId : undefined}
        aria-activedescendant={suggest && options.length ? `${listId}-${suggest.active}` : undefined}
        onPaste={onPaste}
        placeholder={disabled && disabledReason ? disabledReason : placeholder}
        className="max-h-72 w-full resize-none bg-transparent px-1 text-base leading-6 text-fg outline-hidden placeholder:text-subtle"
      />
      <input
        ref={fileInput}
        type="file"
        multiple
        hidden
        tabIndex={-1}
        aria-hidden
        onChange={(e) => {
          if (e.target.files?.length) onAddFiles?.(Array.from(e.target.files));
          e.target.value = "";
        }}
      />
      <div className="flex items-center gap-1">
        <Menu>
          <MenuTrigger asChild>
            <IconButton label="Add files and tools" disabled={disabled}>
              <Plus />
            </IconButton>
          </MenuTrigger>
          <MenuContent>
            <MenuItem icon={<Paperclip />} onSelect={() => fileInput.current?.click()}>Add photos and files</MenuItem>
            {onAddFromLibrary && <MenuItem icon={<Library />} onSelect={onAddFromLibrary}>Add from Library</MenuItem>}
            <MenuSeparator />
            {onImageMode && <MenuItem icon={<ImagePlus />} onSelect={() => onImageMode(!imageMode)}>{imageMode ? "Stop creating an image" : "Create an image"}</MenuItem>}
            {searchMode !== null && (
              <MenuItem icon={<Globe />} onSelect={() => onSearchMode?.(!searchMode)}>{searchMode ? "Stop searching the web" : "Search the web"}</MenuItem>
            )}
            {onThink && !imageMode && (
              <MenuItem icon={<Lightbulb />} onSelect={() => onThink(!think)} description={think ? undefined : "More reasoning for hard questions"}>
                {think ? "Stop thinking longer" : "Think longer"}
              </MenuItem>
            )}
            <MenuItem icon={<Telescope />} disabled description="Arrives in a later release">Deep research</MenuItem>
          </MenuContent>
        </Menu>
        {imageMode && (
          <button
            type="button"
            onClick={() => onImageMode?.(false)}
            className={cn("flex h-8 items-center gap-1.5 rounded-full bg-info-subtle px-3 text-sm text-info-text [&_svg]:size-4", focusRing)}
            aria-label="Image mode on. Turn off"
          >
            <ImageIcon aria-hidden /> Image <X aria-hidden className="size-3.5!" />
          </button>
        )}
        {imageMode && onImageSize && (
          <Menu>
            <MenuTrigger asChild>
              <button
                type="button"
                className={cn("flex h-8 items-center gap-1 rounded-full px-2.5 text-sm text-muted hover:bg-surface-hover [&_svg]:size-4", focusRing)}
                aria-label={`Image shape: ${IMAGE_SIZES.find((x) => x.id === imageSize)?.label}. Change`}
              >
                {sizeIcon(imageSize)} {IMAGE_SIZES.find((x) => x.id === imageSize)?.label} <ChevronDown aria-hidden className="size-3.5!" />
              </button>
            </MenuTrigger>
            <MenuContent>
              {IMAGE_SIZES.map((x) => (
                <MenuItem key={x.id} icon={x.id === imageSize ? <Check /> : sizeIcon(x.id)} onSelect={() => onImageSize(x.id)}>
                  {x.label}
                </MenuItem>
              ))}
            </MenuContent>
          </Menu>
        )}
        {think && !imageMode && (
          <button
            type="button"
            onClick={() => onThink?.(false)}
            className={cn("flex h-8 items-center gap-1.5 rounded-full bg-info-subtle px-3 text-sm text-info-text [&_svg]:size-4", focusRing)}
            aria-label="Think longer on. Turn off"
          >
            <Lightbulb aria-hidden /> Think <X aria-hidden className="size-3.5!" />
          </button>
        )}
        {searchMode && (
          <button
            type="button"
            onClick={() => onSearchMode?.(false)}
            className={cn("flex h-8 items-center gap-1.5 rounded-full bg-info-subtle px-3 text-sm text-info-text [&_svg]:size-4", focusRing)}
            aria-label="Web search on. Turn off"
          >
            <Globe aria-hidden /> Search <X aria-hidden className="size-3.5!" />
          </button>
        )}
        <div className="flex-1" />
        {dictation && dictation.state.phase === "recording" ? (
          <div role="group" aria-label="Dictation" className="flex items-center gap-2">
            <IconButton label="Cancel dictation" onClick={dictation.cancel}>
              <X />
            </IconButton>
            <span aria-hidden className="flex h-4 w-16 items-center gap-0.5">
              {[0.5, 0.8, 1, 0.8, 0.6, 0.9, 0.7, 0.5].map((k, i) => (
                <span
                  key={i}
                  className="w-1 rounded-full bg-accent transition-[height] duration-150"
                  style={{ height: `${Math.max(12, Math.min(100, (dictation.state.phase === "recording" ? dictation.state.level : 0) * 260 * k))}%` }}
                />
              ))}
            </span>
            <span className="w-10 text-sm tabular-nums text-muted">
              <span className="sr-only">Recording, </span>{clock(dictation.state.seconds)}
            </span>
            <IconButton label="Finish dictation" variant="solid" onClick={dictation.stop}>
              <Check />
            </IconButton>
          </div>
        ) : dictation && dictation.state.phase === "transcribing" ? (
          <span role="status" className="flex items-center gap-1.5 px-2 text-sm text-muted">
            <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" /> Turning speech into text…
          </span>
        ) : dictation ? (
          <IconButton label="Dictate" disabled={disabled || dictation.state.phase === "starting"} onClick={dictation.start}>
            <AudioLines />
          </IconButton>
        ) : null}
        {dictation?.state.phase === "recording" ? null : streaming ? (
          <IconButton label="Stop answering" variant="solid" onClick={onStop}>
            <Square className="fill-current" />
          </IconButton>
        ) : (
          <IconButton label="Send message" variant="solid" type="submit" disabled={!canSend}>
            <ArrowUp />
          </IconButton>
        )}
      </div>
    </form>
  );
});

function sizeIcon(size: ImageSize) {
  return size === "landscape" ? <RectangleHorizontal aria-hidden /> : size === "portrait" ? <RectangleVertical aria-hidden /> : <SquareDashed aria-hidden />;
}
