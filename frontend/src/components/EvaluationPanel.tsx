import { Scale } from "lucide-react";
import type { Evaluation } from "../api/types";
import { CHECK_LABELS, formatMs, formatScore } from "../lib/format";
import { VerdictPill } from "./StatusPill";

const METRICS = ["faithfulness", "context_relevance", "answer_relevance", "toxicity"] as const;

/** Collapsible LLM-as-a-Judge verdict shown under every answer. */
export default function EvaluationPanel({ evaluation }: { evaluation: Evaluation }) {
  const failed = new Set<string>(evaluation.failed_checks);
  return (
    <details className="eval">
      <summary className="eval-summary">
        <Scale size={15} className="muted" />
        <VerdictPill passed={evaluation.passed} blocked={evaluation.blocked} />
        <span className="eval-scores">
          <span>Faithfulness {formatScore(evaluation.faithfulness)}</span>
          <span>Relevance {formatScore(evaluation.context_relevance)}</span>
          <span>Toxicity {formatScore(evaluation.toxicity)}</span>
        </span>
        <span className="muted" style={{ marginLeft: "auto", fontSize: 12 }}>
          Judge details
        </span>
      </summary>
      <div className="eval-body">
        {METRICS.map((metric) => {
          const value = evaluation[metric];
          return (
            <div className="meter" key={metric}>
              <span className="secondary">
                {CHECK_LABELS[metric]}
                {failed.has(metric) && <strong style={{ color: "var(--critical-ink)" }}> · failed</strong>}
              </span>
              <div className="meter-track" role="presentation">
                <div
                  className={`meter-fill ${failed.has(metric) ? "fail" : ""}`}
                  style={{ width: `${Math.round(value * 100)}%` }}
                />
              </div>
              <strong style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                {formatScore(value)}
              </strong>
            </div>
          );
        })}
        {Object.entries(evaluation.reasoning).map(([key, text]) => (
          <p className="reasoning" key={key}>
            <strong>{CHECK_LABELS[key] ?? key[0].toUpperCase() + key.slice(1)}:</strong> {text}
          </p>
        ))}
        {evaluation.unsupported_claims.length > 0 && (
          <div>
            <strong>Unsupported claims</strong>
            <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
              {evaluation.unsupported_claims.map((claim, i) => (
                <li key={i} className="secondary">
                  {claim}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="meta-row">
          Judged by {evaluation.judge_model} in {formatMs(evaluation.latency_ms)}
        </div>
      </div>
    </details>
  );
}
