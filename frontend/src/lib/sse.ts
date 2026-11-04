/**
 * Minimal, incremental Server-Sent Events parser.
 *
 * `EventSource` only supports GET, but the chat endpoint is a POST with a JSON
 * body, so we read the response stream ourselves and feed it here chunk by chunk.
 * Chunks can split anywhere (even mid-line), so we buffer until a blank line
 * terminates each event, per the SSE spec.
 */
export interface SSEMessage {
  event: string;
  data: string;
}

export function createSSEParser(onMessage: (message: SSEMessage) => void) {
  let buffer = "";

  function dispatch(block: string) {
    let event = "message";
    const data: string[] = [];
    for (const rawLine of block.split("\n")) {
      const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
      if (!line || line.startsWith(":")) continue; // comment / keep-alive
      const colon = line.indexOf(":");
      const field = colon === -1 ? line : line.slice(0, colon);
      let value = colon === -1 ? "" : line.slice(colon + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "event") event = value;
      else if (field === "data") data.push(value);
    }
    if (data.length) onMessage({ event, data: data.join("\n") });
  }

  return {
    feed(chunk: string) {
      buffer += chunk.replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        dispatch(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");
      }
    },
    flush() {
      if (buffer.trim()) dispatch(buffer);
      buffer = "";
    },
  };
}
