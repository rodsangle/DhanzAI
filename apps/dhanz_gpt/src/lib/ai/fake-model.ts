import "server-only";

/**
 * FAKE MODEL. Deterministic, offline stand-in for the Claude API so every UI state can be built and
 * tested without keys or cost. It reads the same context the real prompt builder will send
 * (project instructions, custom instructions, thread, attachments), so the screens behave the same.
 * /replica-backend replaces `planResponse` + the streaming loop with the Vercel AI SDK + Anthropic.
 *
 * Dev hooks: a message containing "/fail" errors mid-stream; "/slow" streams 4x slower.
 */

export interface ModelContext {
  prompt: string;
  history: { role: "user" | "assistant"; text: string }[];
  projectName?: string;
  projectInstructions?: string;
  aboutYou?: string;
  responseStyle?: string;
  attachments: { name: string; mime: string; text?: string | null }[];
  projectFiles: { name: string }[];
  projectExcerpt?: { name: string; content: string } | null;
  assistantName?: string | null;
  appNote?: string | null;
  memory?: string | null;
  webSearch?: "auto" | "forced" | "off";
  pastChats?: { title: string }[];
  model: string;
  forceImage?: boolean;
}

export interface Plan {
  text: string;
  image?: { prompt: string };
  failAfterChars?: number;
  delayMs: number;
  search?: { query: string; sources: { title: string; url: string }[] };
}

const NEEDS_WEB = /\b(latest|news|search|look up|lookup|current(ly)?|today|this week|trending|price of|who won|right now)\b/i;

/** Demo web search: a cited answer from labelled sample pages on example.com (a domain reserved for examples). */
function demoSearch(prompt: string): Plan["search"] & { text: string } {
  const topic = prompt.replace(/^(search( the web)?( for)?|look up)\s*/i, "").replace(/[?.!]+$/, "").trim() || "headwear trends";
  const slug = topic.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "results";
  const sources = [
    { title: `Sample result: ${topic}`, url: `https://example.com/demo/${slug}` },
    { title: "Sample result: streetwear headwear report", url: "https://example.com/demo/headwear-report" },
  ];
  const text =
    `Here's what the search turned up on **${topic}** (demo results, not real pages):\n\n` +
    `- Structured six-panel caps keep leading new drops, with washed and earth tones on the rise. [[1]](${sources[0].url})\n` +
    `- Small-batch releases with clear drop times sell through faster than open-ended restocks. [[2]](${sources[1].url})\n\n` +
    "Connect a Claude API key to search the real web.";
  return { query: topic, sources, text };
}

const has = (s: string, ...words: string[]) => words.some((w) => s.includes(w));

function hashOf(s: string) {
  let h = 2166136261;
  for (const ch of s) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return h >>> 0;
}

function pick<T>(xs: T[], seed: number) {
  return xs[seed % xs.length];
}

function subjectOf(prompt: string) {
  const m = prompt.match(/\b(snapback|fitted|beanie|cap|hoodie|tee|drop|lookbook|hang tag|collection)s?\b/i);
  return m ? m[1].toLowerCase() : "drop";
}

export function planResponse(ctx: ModelContext): Plan {
  const p = ctx.prompt.toLowerCase();
  const seed = hashOf(ctx.prompt + ctx.history.length);
  const lower = /lowercase/i.test((ctx.projectInstructions ?? "") + " " + (ctx.responseStyle ?? ""));
  const direct = /direct|short|concise|options/i.test(ctx.responseStyle ?? "");
  const subject = subjectOf(ctx.prompt);
  const delayMs = (ctx.model.includes("haiku") ? 12 : ctx.model.includes("opus") ? 34 : 22) * (p.includes("/slow") ? 4 : 1);
  let text: string;
  let image: Plan["image"];

  const searched = ctx.webSearch === "forced" || (ctx.webSearch === "auto" && NEEDS_WEB.test(p)) ? demoSearch(ctx.prompt) : null;
  if (searched) {
    text = searched.text;
  } else if (ctx.forceImage || /^(create|make|draw|generate|design)\b.*\b(image|picture|poster|graphic|mockup|logo|illustration|art)\b/.test(p) || p.startsWith("/image")) {
    const imgPrompt = ctx.prompt.replace(/^\/image\s*/i, "");
    image = { prompt: imgPrompt };
    text =
      `Here's a first pass at **${imgPrompt.slice(0, 80)}**.\n\n` +
      "This is a placeholder render from the demo image generator. Once an image model is connected, the same request returns a real image. " +
      "Tell me what to change: colours, layout, or the text on it.";
  } else if (has(p, "caption", "tagline", "instagram", "tiktok", "post copy", "hashtag")) {
    const lines = [
      `built for the block. the ${subject} lands friday.`,
      `no notes. just the ${subject}. friday 12pm.`,
      `the ${subject} you've been waiting on drops friday.`,
      `heads up. fw26 ${subject}s, limited run.`,
      `same crown, new season. ${subject} out friday.`,
    ];
    const opts = [0, 1, 2].map((i) => pick(lines, seed + i * 7));
    text = `Three options:\n\n${opts.map((o) => `- ${o}`).join("\n")}\n\n` + (direct ? "Want story-length versions?" : "Option two is the punchiest for stories. Want versions with a call to action, or a longer one for the feed?");
  } else if (has(p, "hang tag", "tag copy", "label copy")) {
    text =
      "Options that fit a 2-inch card:\n\n" +
      `1. **Crown, earned.**  \n   Heavyweight ${subject}, made for every day.\n` +
      "2. **Built quiet.**  \n   Tonal details. Nothing extra.\n" +
      "3. **Wear it out.**  \n   Cut for a clean fit that holds its shape.\n\n" +
      "Each headline is under six words and each line under twelve.";
  } else if (has(p, "margin", "markup", "formula")) {
    text =
      "Gross margin is price minus unit cost, over price:\n\n" +
      "$$\n\\text{margin} = \\frac{P - C}{P}\n$$\n\n" +
      "For a cap that sells at $45 and costs $12 to make, that's \\(\\frac{45 - 12}{45} \\approx 73\\%\\).\n\n" +
      "Keystone pricing (\\(P = 2C\\)) always lands at 50%.";
  } else if (has(p, "table", "compare", "vs", "versus", "breakdown")) {
    text =
      "## Quick comparison\n\n| Option | Strength | Watch out for |\n| --- | --- | --- |\n" +
      "| Friday noon drop | Lunch-break traffic | Competes with other drops |\n" +
      "| Sunday evening drop | Relaxed browsing | Lower urgency |\n" +
      "| Thursday 6pm | Early-weekend buzz | Shipping cut-off questions |\n\n" +
      "If the goal is sell-through in 24 hours, Friday noon is the safer bet.";
  } else if (has(p, "json", "code", "script", "csv", "html", "sql", "python", "javascript")) {
    text =
      "Here's a starting point:\n\n```json\n{\n  \"product\": \"FW26 Snapback\",\n  \"colorways\": [\"black\", \"bone\", \"olive\"],\n  \"drop_at\": \"2026-11-20T12:00:00-05:00\",\n  \"units\": 250\n}\n```\n\n" +
      "Swap the units and time for the real numbers before you import it.";
  } else if (has(p, "email", "outreach", "dm", "message to")) {
    text =
      "**Subject:** FW26 is almost here\n\nHey,\n\nWe're dropping our FW26 headwear on Friday and wanted you to see it first. " +
      "If you're up for it, we'd like to send you a cap before launch.\n\nWhat's the best address to ship to?\n\n— RODRECH";
  } else if (has(p, "plan", "checklist", "steps", "schedule", "timeline", "launch")) {
    text =
      "## Plan\n\n1. **Lock the product list.** Final colourways, sizes and units.\n2. **Assets.** Lookbook selects, product shots, story frames.\n" +
      "3. **Copy.** Product pages, email, captions, hang tags.\n4. **Store setup.** Pages live but hidden, inventory synced.\n" +
      "5. **Launch day.** Email at 11:55, stories at noon, support ready for sizing questions.\n\nWant this as a dated checklist?";
  } else {
    const opener = pick(["Here's how I'd approach it.", "Good question. Here's my take.", "Here's a quick answer."], seed);
    text =
      `${opener}\n\n` +
      `- **The short version:** ${ctx.prompt.length > 140 ? "there are a few moving parts, so I've split them up below." : "it depends on what you want people to do next."}\n` +
      "- **What to try first:** keep it simple, test one change at a time, and look at the numbers after a week.\n" +
      "- **What I'd skip:** anything that needs a big budget before you know it works.\n\n" +
      "Tell me more about the goal and I'll make this specific.";
  }

  const notes: string[] = [];
  if (ctx.attachments.length) {
    const read = ctx.attachments.map((a) => {
      const words = a.text ? a.text.trim().split(/\s+/).filter(Boolean).length : 0;
      const first = a.text?.split("\n").find((l) => l.trim() && !/^\[Page \d+\]$/.test(l.trim()))?.trim().slice(0, 90);
      return a.text
        ? `**${a.name}** (${words.toLocaleString()} words). It starts: "${first}"`
        : `**${a.name}**. I can see it's attached, but the demo layer can't read ${a.mime.split("/")[1] ?? "this"} files yet`;
    });
    notes.push(`I looked at ${ctx.attachments.length === 1 ? "your file" : `${ctx.attachments.length} files`}:\n\n${read.map((r) => `- ${r}`).join("\n")}`);
  }
  if (ctx.assistantName) notes.push(`_Answering as ${ctx.assistantName}._`);
  if (ctx.appNote) notes.push(`_${ctx.appNote.split(". ")[0]}. Connect it in Apps first._`);
  if (ctx.projectFiles.length) notes.push(`_Project files in context: ${ctx.projectFiles.map((f) => f.name).join(", ")}._`);
  if (ctx.projectExcerpt) {
    // Quote the line sharing the most words with the question.
    const words = new Set(p.match(/[a-z0-9]{4,}/g) ?? []);
    const score = (l: string) => (l.toLowerCase().match(/[a-z0-9]{4,}/g) ?? []).filter((w) => words.has(w)).length;
    const lines = ctx.projectExcerpt.content.split("\n").filter((l) => l.trim() && !/^\[Page \d+\]/.test(l));
    const line = lines.reduce((best, l) => (score(l) > score(best) ? l : best), lines[0] ?? "").trim().slice(0, 120);
    notes.push(`The most relevant part of **${ctx.projectExcerpt.name}** says: "${line}"`);
  }
  if (notes.length) text = `${notes.join("\n\n")}\n\n${text}`;
  // What memory contributed goes last, so it never changes how an answer opens.
  const recalled: string[] = [];
  if (ctx.memory) recalled.push(`_From memory: ${ctx.memory.split("\n")[0].replace(/^-\s*/, "")}_`);
  if (ctx.pastChats?.length) recalled.push(`_Building on your earlier chat "${ctx.pastChats[0].title}"._`);
  if (recalled.length) text = `${text}\n\n${recalled.join("\n\n")}`;

  if (lower) {
    // Honour a "lowercase" brand rule, but leave code blocks and tables alone.
    let inFence = false;
    text = text
      .split("\n")
      .map((line) => {
        if (line.startsWith("```")) inFence = !inFence;
        return inFence || line.startsWith("```") || line.startsWith("|") ? line : line.toLowerCase();
      })
      .join("\n");
  }

  return {
    text, image, delayMs,
    failAfterChars: p.includes("/fail") ? Math.floor(text.length / 3) : undefined,
    search: searched ? { query: searched.query, sources: searched.sources } : undefined,
  };
}

/** Split into word-ish tokens that keep whitespace, so streamed text re-joins exactly. */
export function tokenize(text: string) {
  return text.match(/\s*\S+|\s+/g) ?? [];
}

export function titleFor(prompt: string) {
  const clean = prompt.replace(/^\/\w+\s*/, "").replace(/[\r\n]+/g, " ").trim();
  const words = clean.split(/\s+/).slice(0, 7).join(" ");
  const t = words.replace(/[.?!,:;]+$/, "");
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : "New chat";
}

/** Placeholder "image model": an abstract SVG seeded by the prompt. Clearly labelled, never passed off as real. */
export function placeholderImage(prompt: string, shape: "square" | "landscape" | "portrait" = "square", edit = false) {
  const [w, hgt] = shape === "landscape" ? [1536, 1024] : shape === "portrait" ? [1024, 1536] : [1024, 1024];
  const h = hashOf(prompt);
  const hue = h % 360;
  const hue2 = (hue + 40 + (h % 90)) % 360;
  const shapes = Array.from({ length: 6 }, (_, i) => {
    const x = ((h >> (i * 3)) % 900 + 50) * (w / 1024);
    const y = ((h >> (i * 2 + 5)) % 900 + 50) * (hgt / 1024);
    const r = 60 + ((h >> i) % 180);
    return `<circle cx="${x}" cy="${y}" r="${r}" fill="hsl(${(hue + i * 25) % 360} 45% ${30 + i * 6}%)" fill-opacity=".55"/>`;
  }).join("");
  const label = prompt.replace(/[<>&"]/g, "").slice(0, 60);
  return Buffer.from(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${hgt}" width="${w}" height="${hgt}">` +
      `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="hsl(${hue} 30% 14%)"/><stop offset="1" stop-color="hsl(${hue2} 40% 30%)"/></linearGradient></defs>` +
      `<rect width="${w}" height="${hgt}" fill="url(#g)"/>${shapes}` +
      `<text x="48" y="${hgt - 64}" font-family="Inter, sans-serif" font-size="30" fill="#fff" fill-opacity=".85">${label}</text>` +
      `<text x="48" y="80" font-family="Inter, sans-serif" font-size="22" letter-spacing="4" fill="#fff" fill-opacity=".6">${edit ? "PLACEHOLDER EDIT" : "PLACEHOLDER RENDER"} · ${shape.toUpperCase()}</text>` +
      `</svg>`,
  );
}
