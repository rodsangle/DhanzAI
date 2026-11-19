import { test, expect } from "@playwright/test";
import { normalizeMath } from "../src/components/chat/markdown";

// F01-H6 (unit): bracket math becomes dollar math, prices and code stay as they are.
test("F01-H6 normalizeMath converts \\( \\) and \\[ \\] but not prices or code", () => {
  expect(normalizeMath("a \\(x^2\\) b")).toBe("a $$x^2$$ b");
  expect(normalizeMath("\\[ \\frac{a}{b} \\]")).toBe("\n$$\n\\frac{a}{b}\n$$\n");
  expect(normalizeMath("caps are $20 and $30")).toBe("caps are $20 and $30");
  expect(normalizeMath("`\\(not math\\)`")).toBe("`\\(not math\\)`");
  expect(normalizeMath("```\n\\[x\\]\n```")).toBe("```\n\\[x\\]\n```");
});
