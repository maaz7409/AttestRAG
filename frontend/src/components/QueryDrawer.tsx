import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { QueryDetail } from "../api/types";
import { CHECK_LABELS, formatDateTime, formatMs, formatScore } from "../lib/format";
import { StatusPill, VerdictPill } from "./StatusPill";

/** Full audit record for one query: answer, latency breakdown, sources, judge verdict. */
export default function QueryDrawer({ queryId, onClose }: { queryId: string; onClose: () => void }) {
  const [detail, setDetail] = useState<QueryDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getQuery(queryId).then(setDetail).catch((e: Error) => setError(e.message));
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [queryId, onClose]);

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} aria-label="Query details">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
          <h2 style={{ fontSize: 17 }}>Query details</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>
        {error && <div className="error-banner">{error}</div>}
        {!detail && !error && <div className="muted">Loading…</div>}
        {detail && (
          <>
            <section>
              <div className="meta-row">
                <StatusPill status={detail.status} />
                <span>{formatDateTime(detail.created_at)}</span>
                {detail.session_id && <span>· session {detail.session_id.slice(0, 8)}</span>}
              </div>
              <h3 style={{ fontSize: 15 }}>{detail.question}</h3>
              <p className="answer" style={{ margin: 0, fontSize: 14 }}>
                {detail.answer ?? <span className="muted">No answer recorded</span>}
              </p>
              {detail.error && <div className="error-banner">{detail.error}</div>}
            </section>

            <section>
              <h2>Latency</h2>
              <dl className="kv">
                <dt>Retrieval</dt>
                <dd>{formatMs(detail.retrieval_ms)}</dd>
                <dt>Generation</dt>
                <dd>{formatMs(detail.generation_ms)}</dd>
                <dt>Judge</dt>
                <dd>{formatMs(detail.evaluation_ms)}</dd>
                <dt>Time to first token</dt>
                <dd>{formatMs(detail.time_to_first_token_ms)}</dd>
                <dt>Total</dt>
                <dd>
                  <strong>{formatMs(detail.total_ms)}</strong>
                </dd>
                <dt>Model / mode</dt>
                <dd>
                  {detail.chat_model} · {detail.guardrail_mode}
                </dd>
              </dl>
            </section>

            {detail.evaluation && (
              <section>
                <h2 style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  Judge verdict <VerdictPill passed={detail.evaluation.passed} />
                </h2>
                <dl className="kv">
                  {(["faithfulness", "context_relevance", "answer_relevance", "toxicity"] as const).map(
                    (k) => (
                      <div key={k} style={{ display: "contents" }}>
                        <dt>{CHECK_LABELS[k]}</dt>
                        <dd>
                          {formatScore(detail.evaluation![k])}
                          {detail.evaluation!.failed_checks.includes(k as never) && (
                            <strong style={{ color: "var(--critical-ink)" }}> · failed</strong>
                          )}
                        </dd>
                      </div>
                    ),
                  )}
                  <dt>Judge model</dt>
                  <dd>{detail.evaluation.judge_model}</dd>
                </dl>
                {Object.entries(detail.evaluation.reasoning).map(([k, v]) => (
                  <p key={k} className="reasoning" style={{ fontSize: 13 }}>
                    <strong>{k[0].toUpperCase() + k.slice(1)}:</strong> {v}
                  </p>
                ))}
              </section>
            )}

            <section>
              <h2>Source attribution</h2>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th className="num">#</th>
                      <th>Document</th>
                      <th className="num">Page</th>
                      <th className="num">RRF</th>
                      <th>Cited</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.sources.map((s) => (
                      <tr key={s.chunk_id}>
                        <td className="num">{s.rank}</td>
                        <td className="wrap">{s.filename}</td>
                        <td className="num">{s.page_number}</td>
                        <td className="num">{s.fused_score.toFixed(4)}</td>
                        <td>{s.cited ? "Yes" : <span className="muted">No</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </aside>
    </div>
  );
}
