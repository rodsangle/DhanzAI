"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { components } from "./markdown";

const remarkPlugins = [remarkGfm, [remarkMath, { singleDollarTextMath: false }]] as const;
const rehypePlugins = [[rehypeKatex, { throwOnError: false, strict: "ignore", output: "htmlAndMathml" }]] as const;

/** Markdown with math (loaded on demand by ./markdown). The text is already normalized to $$ … $$. */
export default function MarkdownMath({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={remarkPlugins as unknown as never} rehypePlugins={rehypePlugins as unknown as never} components={components}>
      {text}
    </ReactMarkdown>
  );
}
