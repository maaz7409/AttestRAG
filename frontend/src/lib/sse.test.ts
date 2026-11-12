import { describe, expect, it } from "vitest";
import { createSSEParser, type SSEMessage } from "./sse";

describe("createSSEParser", () => {
  it("parses events split across arbitrary chunk boundaries", () => {
    const messages: SSEMessage[] = [];
    const parser = createSSEParser((m) => messages.push(m));
    const stream = 'event: token\ndata: {"content":"Hel"}\n\nevent: token\ndata: {"content":"lo"}\n\n';
    for (const char of stream) parser.feed(char);
    expect(messages).toEqual([
      { event: "token", data: '{"content":"Hel"}' },
      { event: "token", data: '{"content":"lo"}' },
    ]);
  });

  it("handles CRLF, comments, multi-line data and a trailing event", () => {
    const messages: SSEMessage[] = [];
    const parser = createSSEParser((m) => messages.push(m));
    parser.feed(": keep-alive\r\n\r\ndata: line1\r\ndata: line2\r\n\r\nevent: done\ndata: {}");
    parser.flush();
    expect(messages).toEqual([
      { event: "message", data: "line1\nline2" },
      { event: "done", data: "{}" },
    ]);
  });
});
