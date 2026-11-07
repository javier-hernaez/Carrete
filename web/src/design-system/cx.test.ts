import { describe, expect, it } from "vitest";

import { cx } from "./cx";

describe("cx", () => {
  it("une las clases válidas", () => {
    expect(cx("a", false, undefined, null, "b")).toBe("a b");
    expect(cx()).toBe("");
  });
});
