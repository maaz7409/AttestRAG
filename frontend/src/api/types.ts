// Types mirroring the FastAPI response models (backend/app/schemas/api.py).

export interface DocumentInfo {
  id: string;
  filename: string;
  size_bytes: number;
  num_pages: number;
  num_chunks: number;
  status: "processing" | "ready" | "failed";
  error: string | null;
  created_at: string;
}

export interface Source {
  index: number;
  chunk_id: string;
  document_id: string;
  filename: string;
  page_number: number;
  content: string;
  dense_score: number | null;
  sparse_score: number | null;
  fused_score: number;
  dense_rank: number | null;
  sparse_rank: number | null;
  cited: boolean;
}

export type CheckName = "faithfulness" | "context_relevance" | "toxicity";

export interface Evaluation {
  judge_model: string;
  faithfulness: number;
  context_relevance: number;
  answer_relevance: number;
  toxicity: number;
  passed: boolean;
  blocked: boolean;
  failed_checks: CheckName[];
  unsupported_claims: string[];
  reasoning: Record<string, string>;
  latency_ms: number;
}

export interface Latency {
  retrieval_ms: number;
  generation_ms: number;
  evaluation_ms: number;
  total_ms: number;
  time_to_first_token_ms: number | null;
}

export type QueryStatus = "answered" | "blocked" | "no_context" | "error";

/** Server-Sent Events emitted by POST /api/chat/stream. */
export type StreamEvent =
  | { type: "start"; query_id: string; guardrail_mode: "stream" | "strict" }
  | { type: "sources"; sources: Source[] }
  | { type: "token"; content: string }
  | ({ type: "evaluation" } & Evaluation)
  | { type: "blocked"; reasons: CheckName[]; message: string }
  | { type: "done"; query_id: string; status: QueryStatus; cited: number[]; latency: Latency }
  | { type: "error"; query_id?: string; message: string };

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  question: string;
  session_id?: string;
  document_ids?: string[];
  history?: ChatTurn[];
}

export interface QuerySummary {
  id: string;
  session_id: string | null;
  question: string;
  status: QueryStatus;
  total_ms: number;
  created_at: string;
  faithfulness: number | null;
  context_relevance: number | null;
  toxicity: number | null;
  passed: boolean | null;
}

export interface QueryDetail {
  id: string;
  session_id: string | null;
  question: string;
  answer: string | null;
  status: QueryStatus;
  chat_model: string;
  guardrail_mode: string;
  retrieval_ms: number;
  generation_ms: number;
  evaluation_ms: number;
  total_ms: number;
  time_to_first_token_ms: number | null;
  error: string | null;
  created_at: string;
  sources: Array<{
    chunk_id: string;
    document_id: string;
    filename: string;
    page_number: number;
    rank: number;
    dense_score: number | null;
    sparse_score: number | null;
    fused_score: number;
    cited: boolean;
  }>;
  evaluation: (Omit<Evaluation, "blocked" | "reasoning"> & { reasoning: Record<string, string> }) | null;
}

export interface CountItem {
  name: string;
  count: number;
}

export interface AnalyticsOverview {
  window_days: number;
  totals: {
    queries: number;
    answered: number;
    blocked: number;
    no_context: number;
    errors: number;
    documents: number;
    chunks: number;
  };
  latency: {
    avg_total_ms: number | null;
    p50_total_ms: number | null;
    p95_total_ms: number | null;
    avg_retrieval_ms: number | null;
    avg_generation_ms: number | null;
    avg_evaluation_ms: number | null;
    avg_ttft_ms: number | null;
  };
  quality: {
    evaluated: number;
    pass_rate: number | null;
    avg_faithfulness: number | null;
    avg_context_relevance: number | null;
    avg_answer_relevance: number | null;
    avg_toxicity: number | null;
  };
  timeseries: Array<{
    date: string;
    queries: number;
    blocked: number;
    avg_latency_ms: number | null;
    p95_latency_ms: number | null;
    avg_faithfulness: number | null;
    avg_context_relevance: number | null;
  }>;
  failed_checks: CountItem[];
  top_documents: CountItem[];
  score_distribution: Array<{
    bucket: string;
    faithfulness: number;
    context_relevance: number;
    answer_relevance: number;
  }>;
}

export interface ReadyStatus {
  status: "ok" | "degraded";
  checks: Record<string, string>;
  provider: string;
  guardrail_mode: string;
  judge_enabled: boolean;
  indexed_chunks: number;
}
