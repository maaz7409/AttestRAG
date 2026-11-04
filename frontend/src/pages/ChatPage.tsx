import { Filter, Loader2, RotateCcw, Send, ShieldAlert, Sparkles, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { DocumentInfo } from "../api/types";
import AnswerText from "../components/AnswerText";
import EvaluationPanel from "../components/EvaluationPanel";
import SourceList from "../components/SourceList";
import { StatusPill } from "../components/StatusPill";
import { formatMs } from "../lib/format";
import { type AssistantMessage, useChat } from "../lib/useChat";

const SUGGESTIONS = [
  "Summarize the key points of these documents",
  "What are the main obligations or requirements?",
  "Are there any deadlines or dates I should know about?",
];

function AssistantBubble({ message }: { message: AssistantMessage }) {
  const [activeSource, setActiveSource] = useState<number | null>(null);

  const selectSource = (index: number | null) => {
    setActiveSource(index);
    const source = message.sources.find((s) => s.index === index);
    if (source) {
      document
        .getElementById(`source-${source.chunk_id}`)
        ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  };

  const waiting = message.phase !== "done" && !message.content;
  const phaseLabel =
    message.phase === "retrieving"
      ? "Searching documents (dense + BM25)…"
      : message.phase === "judging"
        ? "Generating and verifying the answer…"
        : "Generating…";

  return (
    <div className="msg-assistant">
      {waiting && !message.blocked && (
        <div className="thinking">
          <Loader2 size={16} className="spin" />
          {phaseLabel}
        </div>
      )}

      {message.blocked ? (
        <div>
          <div className="blocked-box" role="alert">
            <ShieldAlert size={18} style={{ flex: "none", marginTop: 2 }} />
            <div>{message.blocked.message}</div>
          </div>
          {message.blocked.retracted && (
            <details className="retracted muted">
              <summary>Show retracted draft (for review)</summary>
              <p>{message.blocked.retracted}</p>
            </details>
          )}
        </div>
      ) : (
        message.content && (
          <AnswerText
            text={message.content}
            sourceCount={message.sources.length}
            activeSource={activeSource}
            streaming={message.phase !== "done"}
            onCite={selectSource}
          />
        )
      )}

      {message.error && (
        <div className="error-banner" role="alert">
          {message.error}
        </div>
      )}

      {message.evaluation && <EvaluationPanel evaluation={message.evaluation} />}

      {message.phase !== "retrieving" && (
        <SourceList
          sources={message.sources}
          activeSource={activeSource}
          onSelect={selectSource}
        />
      )}

      {message.phase === "done" && message.status && (
        <div className="meta-row">
          <StatusPill status={message.status} />
          {message.latency && (
            <>
              <span>Total {formatMs(message.latency.total_ms)}</span>
              <span>· Retrieval {formatMs(message.latency.retrieval_ms)}</span>
              <span>· Generation {formatMs(message.latency.generation_ms)}</span>
              {message.latency.evaluation_ms > 0 && (
                <span>· Judge {formatMs(message.latency.evaluation_ms)}</span>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ScopePicker({
  documents,
  selected,
  onChange,
}: {
  documents: DocumentInfo[];
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const toggle = (id: string) =>
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);

  return (
    <div className="scope" ref={ref}>
      <button className="btn" type="button" onClick={() => setOpen((o) => !o)}>
        <Filter size={15} />
        {selected.length ? `${selected.length} of ${documents.length} documents` : "All documents"}
      </button>
      {open && (
        <div className="scope-menu card">
          {documents.length === 0 && <div className="muted scope-item">No documents yet</div>}
          {documents.map((doc) => (
            <label className="scope-item" key={doc.id}>
              <input
                type="checkbox"
                checked={selected.includes(doc.id)}
                onChange={() => toggle(doc.id)}
              />
              <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{doc.filename}</span>
            </label>
          ))}
          {selected.length > 0 && (
            <button className="btn btn-ghost" style={{ width: "100%" }} onClick={() => onChange([])}>
              Search all documents
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default function ChatPage() {
  const { messages, busy, send, stop, reset } = useChat();
  const [input, setInput] = useState("");
  const [documents, setDocuments] = useState<DocumentInfo[] | null>(null);
  const [scope, setScope] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    api
      .listDocuments()
      .then((docs) => setDocuments(docs.filter((d) => d.status === "ready")))
      .catch(() => setDocuments([]));
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [input]);

  const submit = (text = input) => {
    if (!text.trim() || busy) return;
    send(text, scope);
    setInput("");
  };

  const noDocuments = documents !== null && documents.length === 0;

  return (
    <div className="chat">
      <div className="chat-header">
        <div>
          <h1>Ask your documents</h1>
          <p className="secondary" style={{ margin: "2px 0 0" }}>
            Answers are grounded in your PDFs, cited, and verified by an LLM judge.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {documents && documents.length > 0 && (
            <ScopePicker documents={documents} selected={scope} onChange={setScope} />
          )}
          {messages.length > 0 && (
            <button className="btn" onClick={reset} type="button">
              <RotateCcw size={15} /> New chat
            </button>
          )}
        </div>
      </div>

      <div className="chat-scroll" ref={scrollRef}>
        {messages.length === 0 ? (
          <div className="empty">
            <div className="empty-icon">
              <Sparkles size={24} />
            </div>
            <h2>What would you like to know?</h2>
            {noDocuments ? (
              <p>
                No documents indexed yet. <Link to="/documents">Upload a PDF</Link> to get started.
              </p>
            ) : (
              <>
                <p>Ask a question in plain language. Every claim links back to its source page.</p>
                <div className="suggestions">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} className="suggestion" onClick={() => submit(s)} type="button">
                      {s}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        ) : (
          <div className="messages">
            {messages.map((m) =>
              m.role === "user" ? (
                <div key={m.id} className="msg-user">
                  {m.content}
                </div>
              ) : (
                <AssistantBubble key={m.id} message={m} />
              ),
            )}
          </div>
        )}
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <div className="composer-box">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            placeholder="Ask a question about your documents…"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            maxLength={2000}
            aria-label="Question"
          />
          {busy ? (
            <button className="btn" type="button" onClick={stop}>
              <Square size={14} /> Stop
            </button>
          ) : (
            <button className="btn btn-primary" type="submit" disabled={!input.trim()}>
              <Send size={15} /> Ask
            </button>
          )}
        </div>
        <div className="composer-hint">
          Enter to send · Shift+Enter for a new line
          {scope.length > 0 && ` · Searching ${scope.length} selected document(s)`}
        </div>
      </form>
    </div>
  );
}
