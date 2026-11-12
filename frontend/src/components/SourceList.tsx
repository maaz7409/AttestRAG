import { FileText } from "lucide-react";
import type { Source } from "../api/types";

interface Props {
  sources: Source[];
  activeSource: number | null;
  onSelect: (index: number | null) => void;
}

/** Source attribution cards: one per retrieved chunk, cited ones highlighted. */
export default function SourceList({ sources, activeSource, onSelect }: Props) {
  if (!sources.length) return null;
  return (
    <div className="sources">
      {sources.map((source) => {
        const active = activeSource === source.index;
        return (
          <button
            key={source.chunk_id}
            id={`source-${source.chunk_id}`}
            type="button"
            className={`source ${source.cited ? "cited" : ""} ${active ? "active expanded" : ""}`}
            onClick={() => onSelect(active ? null : source.index)}
            title={active ? "Collapse" : "Expand passage"}
          >
            <div className="source-head">
              <span className="cite" aria-hidden>
                {source.index}
              </span>
              <FileText size={14} className="muted" />
              <span className="name">{source.filename}</span>
              <span className="muted" style={{ fontWeight: 400, marginLeft: "auto" }}>
                p.&nbsp;{source.page_number}
              </span>
            </div>
            <div className="source-snippet">{source.content}</div>
            <div className="source-scores">
              <span>RRF {source.fused_score.toFixed(4)}</span>
              <span>
                Dense {source.dense_rank ? `#${source.dense_rank}` : "–"}
                {source.dense_score != null && ` (${source.dense_score.toFixed(2)})`}
              </span>
              <span>
                BM25 {source.sparse_rank ? `#${source.sparse_rank}` : "–"}
                {source.sparse_score != null && ` (${source.sparse_score.toFixed(2)})`}
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
