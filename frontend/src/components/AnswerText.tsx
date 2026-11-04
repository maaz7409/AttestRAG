import { useMemo } from "react";
import { splitCitations } from "../lib/citations";

interface Props {
  text: string;
  sourceCount: number;
  activeSource: number | null;
  streaming: boolean;
  onCite: (index: number) => void;
}

/** Renders an answer with [n] markers turned into clickable citation chips. */
export default function AnswerText({ text, sourceCount, activeSource, streaming, onCite }: Props) {
  const segments = useMemo(() => splitCitations(text, sourceCount), [text, sourceCount]);
  return (
    <div className="answer">
      {segments.map((segment, i) =>
        segment.kind === "text" ? (
          <span key={i}>{segment.text}</span>
        ) : (
          <button
            key={i}
            type="button"
            className={`cite ${activeSource === segment.index ? "active" : ""}`}
            onClick={() => onCite(segment.index)}
            aria-label={`Show source ${segment.index}`}
          >
            {segment.index}
          </button>
        ),
      )}
      {streaming && <span className="cursor" aria-hidden />}
    </div>
  );
}
