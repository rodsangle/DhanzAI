import { test, expect } from "@playwright/test";
import { safeNext } from "../src/lib/safe-next";

// X-6: the one redirect check shared by /login and /auth/callback (the callback's success path needs a live OAuth code).
test("X-6 safeNext only allows same-site paths", () => {
  const bad = ["//evil.example", "/\\evil.example", "/\t/evil.example", "/\n/evil.example", "https://evil.example", "javascript:alert(1)", "evil.example", "", null, undefined, "/\\/evil.example"];
  for (const v of bad) expect(safeNext(v), JSON.stringify(v)).toBe("/");
  expect(safeNext("/c/123?x=1#y")).toBe("/c/123?x=1#y");
  expect(safeNext("/s/abc")).toBe("/s/abc");
  expect(safeNext("/library", "/home")).toBe("/library");
  expect(safeNext("//x", "/home")).toBe("/home");
});
