import { describe, expect, it } from "vitest";
import { translateUiCopy } from "./ui-copy";

describe("offline UI copy translation", () => {
  const catalog = { "AUTO ROUTING": "自动路由", "Save": "保存", "/newbot": "incorrect translation" };

  it("translates exact labels while preserving whitespace", () => {
    expect(translateUiCopy("  AUTO ROUTING  ", catalog)).toBe("  自动路由  ");
    expect(translateUiCopy("Save", catalog)).toBe("保存");
  });

  it("never translates commands or unlisted content", () => {
    expect(translateUiCopy("/newbot", catalog)).toBe("/newbot");
    expect(translateUiCopy("A user's private message", catalog)).toBe("A user's private message");
  });
});
