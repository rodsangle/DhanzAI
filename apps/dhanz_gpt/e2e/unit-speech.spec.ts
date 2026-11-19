import { test, expect } from "@playwright/test";
import { MAX_SPEECH_PARTS, speakable, speechParts } from "../src/lib/speech-text";

// Read aloud (unit): what gets spoken, and how long answers are split for the voice service.
test("RA-U1 markdown becomes plain speech; prices and paragraphs survive", () => {
  const md = [
    "## Launch plan",
    "",
    "- **Friday**: post at noon, see [the brief](https://example.com/brief) [[1]](https://example.com/a)",
    "- Budget: $5 a day, $10 on weekends",
    "",
    "| Day | Post |",
    "| --- | --- |",
    "| Fri | Teaser |",
    "",
    "```js",
    "console.log('no')",
    "```",
    "Use `npm run build` first.",
  ].join("\n");
  const out = speakable(md);
  expect(out).toContain("Launch plan");
  expect(out).toContain("Friday: post at noon, see the brief");
  expect(out).not.toContain("https://");
  expect(out).not.toContain("[[1]]");
  expect(out).toContain("$5 a day, $10 on weekends");
  expect(out).not.toContain("---");
  expect(out).toContain("Day, Post");
  expect(out).toContain("(code omitted)");
  expect(out).toContain("Use npm run build first.");
  expect(out.split(/\n\n/).length).toBeGreaterThan(2);
});

test("RA-U2 long answers split at paragraph, sentence and word boundaries, under the limit", () => {
  const para = (n: number, w = "word") => Array.from({ length: n }, (_, i) => `${w}${i}`).join(" ") + ".";
  const short = speechParts("One.\n\nTwo.");
  expect(short).toEqual(["One.\n\nTwo."]);

  const many = speechParts(Array.from({ length: 20 }, () => para(80)).join("\n\n"));
  expect(many.length).toBeGreaterThan(1);
  for (const p of many) expect(p.length).toBeLessThanOrEqual(3000);
  expect(many.join("\n\n").replace(/\s+/g, " ")).toBe(Array.from({ length: 20 }, () => para(80)).join(" ").replace(/\s+/g, " "));

  const sentences = Array.from({ length: 60 }, (_, i) => `Sentence number ${i} is here to make this paragraph long.`).join(" ");
  const bySentence = speechParts(sentences);
  expect(bySentence.length).toBeGreaterThan(1);
  for (const p of bySentence) expect(p.endsWith(".")).toBeTruthy();

  const noStops = speechParts("x".repeat(10) + " " + "y ".repeat(4000));
  for (const p of noStops) expect(p.length).toBeLessThanOrEqual(3000);

  expect(speechParts(Array.from({ length: 200 }, () => para(100)).join("\n\n")).length).toBe(MAX_SPEECH_PARTS);
});
