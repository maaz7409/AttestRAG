import { createSSEParser } from "../lib/sse";
import type {
  AnalyticsOverview,
  ChatRequest,
  DocumentInfo,
  QueryDetail,
  QuerySummary,
  ReadyStatus,
  StreamEvent,
} from "./types";

const BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "") + "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail || `Request failed (${response.status})`);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export const api = {
  ready: () => request<ReadyStatus>("/ready"),
  listDocuments: () => request<DocumentInfo[]>("/documents"),
  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentInfo>("/documents", { method: "POST", body: form });
  },
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),
  listQueries: (limit = 25, offset = 0, status?: string) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (status) params.set("status", status);
    return request<{ items: QuerySummary[]; total: number }>(`/queries?${params}`);
  },
  getQuery: (id: string) => request<QueryDetail>(`/queries/${id}`),
  analytics: (days: number) => request<AnalyticsOverview>(`/analytics/overview?days=${days}`),
};

/** POST a question and invoke `onEvent` for every SSE event as it arrives. */
export async function streamChat(
  body: ChatRequest,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new ApiError(response.status, `Chat request failed (${response.status})`);
  }

  const parser = createSSEParser((message) => onEvent(JSON.parse(message.data) as StreamEvent));
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    parser.feed(value);
  }
  parser.flush();
}
