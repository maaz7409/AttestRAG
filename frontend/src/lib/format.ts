export const formatMs = (ms: number | null | undefined): string => {
  if (ms == null) return "–";
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`;
};

export const formatPct = (value: number | null | undefined, digits = 0): string =>
  value == null ? "–" : `${(value * 100).toFixed(digits)}%`;

export const formatScore = (value: number | null | undefined): string =>
  value == null ? "–" : value.toFixed(2);

export const formatBytes = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

export const formatDateTime = (iso: string): string =>
  new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

export const formatDay = (isoDate: string): string =>
  new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export const CHECK_LABELS: Record<string, string> = {
  faithfulness: "Faithfulness",
  context_relevance: "Context relevance",
  answer_relevance: "Answer relevance",
  toxicity: "Toxicity",
};
