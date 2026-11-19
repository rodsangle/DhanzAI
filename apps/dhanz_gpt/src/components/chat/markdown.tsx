"use client";

import { lazy, memo, Suspense } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock } from "./message";

export const components: Components = {
  pre: ({ children }) => <>{children}</>,
  code({ className, children }) {
    const lang = /language-(\w+)/.exec(className ?? "")?.[1];
    const text = String(children ?? "");
    if (lang || text.includes("\n")) return <CodeBlock language={lang ?? "text"} code={text.replace(/\n$/, "")} />;
    return <code className="rounded-sm bg-surface-muted px-1 py-0.5 font-mono text-[0.9em]">{children}</code>;
  },
  a: ({ href, children }) => {
    // Web citations arrive as [[n]](url): show them as small numbered links that match the Sources list.
    const cite = typeof children === "string" ? /^\[(\d+)\]$/.exec(children) : null;
    if (cite && href) {
      let host = href;
      try {
        host = new URL(href).hostname.replace(/^www\./, "");
      } catch {}
      return (
        <a
          href={href}
          target="_blank"
          rel="noreferrer noopener"
          aria-label={`Source ${cite[1]}: ${host}`}
          title={host}
          className="mx-0.5 inline-flex h-4 min-w-4 -translate-y-1 items-center justify-center rounded-sm bg-surface-muted px-1 align-baseline text-[0.7rem] font-medium leading-none text-muted no-underline! hover:bg-surface-active hover:text-fg"
        >
          {cite[1]}
        </a>
      );
    }
    return (
      <a href={href} target="_blank" rel="noreferrer noopener" className="text-accent-text underline underline-offset-2">
        {children}
      </a>
    );
  },
  table: ({ children }) => (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border-b border-border bg-surface-muted px-3 py-2 text-left font-semibold">{children}</th>,
  td: ({ children }) => <td className="border-b border-border px-3 py-2 align-top">{children}</td>,
  h1: ({ children }) => <h2 className="text-xl font-semibold">{children}</h2>,
  h2: ({ children }) => <h3 className="text-lg font-semibold">{children}</h3>,
  h3: ({ children }) => <h4 className="text-base font-semibold">{children}</h4>,
  ul: ({ children }) => <ul className="list-disc space-y-1 pl-6">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal space-y-1 pl-6">{children}</ol>,
  blockquote: ({ children }) => <blockquote className="border-l-[3px] border-border-strong pl-4 text-muted">{children}</blockquote>,
  hr: () => <hr className="border-border" />,
  img: ({ src, alt }) => (typeof src === "string" ? <img src={src} alt={alt ?? ""} className="rounded-lg" /> : null),
};

/**
 * Models write math as \( … \) and \[ … \] as often as $$ … $$. remark-math only
 * knows dollars, so convert the bracket forms first. Code spans and fences are
 * left alone. Single-dollar math stays off so "$20 and $30" stays a price.
 */
export function normalizeMath(src: string): string {
  return src
    .split(/(```[\s\S]*?(?:```|$)|`[^`\n]*`)/g)
    .map((part, i) =>
      i % 2 === 1
        ? part
        : part
            .replace(/\\\[([\s\S]+?)\\\]/g, (_, m: string) => `\n$$\n${m.trim()}\n$$\n`)
            .replace(/\\\(([\s\S]+?)\\\)/g, (_, m: string) => `$$${m.trim()}$$`),
    )
    .join("");
}

const plugins = [remarkGfm];

/** The plain renderer: GFM, code and tables. Also shown while the math renderer loads. */
function Plain({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={plugins} components={components}>
      {text}
    </ReactMarkdown>
  );
}

// KaTeX is large, so it loads only for answers that contain math.
const WithMath = lazy(() => import("./markdown-math"));

export const Markdown = memo(function Markdown({ text }: { text: string }) {
  const src = normalizeMath(text);
  return (
    <div className="flex flex-col gap-4 [&>p]:leading-7 [&_.katex-display]:overflow-x-auto [&_.katex-display]:py-1">
      {src.includes("$$") ? (
        <Suspense fallback={<Plain text={src} />}>
          <WithMath text={src} />
        </Suspense>
      ) : (
        <Plain text={src} />
      )}
    </div>
  );
});
