import { describe, expect, it } from "vitest";
import type { Source } from "../api/types";
import { applyEvent, type AssistantMessage } from "./useChat";

const source: Source = {
  index: 1,
  chunk_id: "c1",
  document_id: "d1",
  filename: "handbook.pdf",
  page_number: 2,
  content: "Employees get 25 days.",
  dense_score: 0.8,
  sparse_score: 3.1,
  fused_score: 0.03,
  dense_rank: 1,
  sparse_rank: 1,
  cited: false,
};

const empty: AssistantMessage = {
  id: "a",
  role: "assistant",
  content: "",
  phase: "retrieving",
  sources: [],
};

describe("applyEvent", () => {
  it("accumulates a streamed answer and marks cited sources", () => {
    let m = applyEvent(empty, { type: "start", query_id: "q", guardrail_mode: "stream" });
    m = applyEvent(m, { type: "sources", sources: [source] });
    expect(m.phase).toBe("generating");
    m = applyEvent(m, { type: "token", content: "25 days " });
    m = applyEvent(m, { type: "token", content: "[1]." });
    m = applyEvent(m, {
      type: "done",
      query_id: "q",
      status: "answered",
      cited: [1],
      latency: { retrieval_ms: 5, generation_ms: 50, evaluation_ms: 20, total_ms: 80, time_to_first_token_ms: 12 },
    });
    expect(m.content).toBe("25 days [1].");
    expect(m.phase).toBe("done");
    expect(m.sources[0].cited).toBe(true);
  });

  it("retracts the streamed answer when the judge blocks it", () => {
    let m: AssistantMessage = { ...empty, content: "Pirates founded the company." };
    m = applyEvent(m, { type: "blocked", reasons: ["faithfulness"], message: "Withheld" });
    expect(m.content).toBe("");
    expect(m.blocked?.retracted).toBe("Pirates founded the company.");
  });

  it("shows a judging phase in strict mode", () => {
    let m = applyEvent(empty, { type: "start", query_id: "q", guardrail_mode: "strict" });
    m = applyEvent(m, { type: "sources", sources: [source] });
    expect(m.phase).toBe("judging");
  });
});
