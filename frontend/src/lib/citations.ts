export type Segment = { kind: "text"; text: string } | { kind: "cite"; index: number };

const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

/**
 * Split an answer like "Leave is 25 days [1][3]." into text and citation segments
 * so citations can be rendered as interactive chips. Indices outside
 * 1..maxIndex (hallucinated citations) are left as plain text.
 */
export function splitCitations(text: string, maxIndex: number): Segment[] {
  const segments: Segment[] = [];
  let last = 0;
  for (const match of text.matchAll(CITATION)) {
    const indices = match[1].split(",").map((n) => Number.parseInt(n.trim(), 10));
    if (!indices.every((n) => n >= 1 && n <= maxIndex)) continue;
    const start = match.index ?? 0;
    if (start > last) segments.push({ kind: "text", text: text.slice(last, start) });
    for (const index of indices) segments.push({ kind: "cite", index });
    last = start + match[0].length;
  }
  if (last < text.length) segments.push({ kind: "text", text: text.slice(last) });
  return segments;
}
