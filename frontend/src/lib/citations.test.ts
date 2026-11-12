import { describe, expect, it } from "vitest";
import { splitCitations } from "./citations";

describe("splitCitations", () => {
  it("turns citation markers into segments", () => {
    expect(splitCitations("Leave is 25 days [1][3].", 3)).toEqual([
      { kind: "text", text: "Leave is 25 days " },
      { kind: "cite", index: 1 },
      { kind: "cite", index: 3 },
      { kind: "text", text: "." },
    ]);
  });

  it("expands grouped citations", () => {
    expect(splitCitations("A [1, 2]", 2)).toEqual([
      { kind: "text", text: "A " },
      { kind: "cite", index: 1 },
      { kind: "cite", index: 2 },
    ]);
  });

  it("leaves out-of-range citations as text", () => {
    expect(splitCitations("See [7].", 3)).toEqual([{ kind: "text", text: "See [7]." }]);
  });
});
