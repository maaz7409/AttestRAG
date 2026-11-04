import { CheckCircle2, FileUp, Loader2, Trash2, XCircle } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { DocumentInfo } from "../api/types";
import { formatBytes, formatDateTime } from "../lib/format";

interface UploadItem {
  id: string;
  name: string;
  state: "uploading" | "done" | "error";
  message?: string;
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(
    () =>
      api
        .listDocuments()
        .then((docs) => {
          setDocuments(docs);
          setError(null);
        })
        .catch((e: Error) => setError(e.message)),
    [],
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  const upload = async (files: FileList | File[]) => {
    const pdfs = Array.from(files);
    // Sequential uploads keep embedding-API usage predictable for large batches.
    for (const file of pdfs) {
      const id = crypto.randomUUID();
      setUploads((u) => [{ id, name: file.name, state: "uploading" }, ...u]);
      try {
        const doc = await api.uploadDocument(file);
        setUploads((u) =>
          u.map((x) =>
            x.id === id
              ? { ...x, state: "done", message: `${doc.num_pages} pages · ${doc.num_chunks} chunks` }
              : x,
          ),
        );
      } catch (e) {
        setUploads((u) =>
          u.map((x) =>
            x.id === id
              ? { ...x, state: "error", message: e instanceof Error ? e.message : "Upload failed" }
              : x,
          ),
        );
      }
      refresh();
    }
  };

  const remove = async (doc: DocumentInfo) => {
    if (!window.confirm(`Delete "${doc.filename}" and remove it from the search index?`)) return;
    try {
      await api.deleteDocument(doc.id);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  };

  const totalChunks = documents?.reduce((sum, d) => sum + d.num_chunks, 0) ?? 0;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Documents</h1>
          <p>
            PDFs are split into page-aware chunks, embedded into Qdrant and indexed for BM25 keyword
            search.
          </p>
        </div>
        {documents && (
          <span className="secondary">
            {documents.length} documents · {totalChunks.toLocaleString()} chunks
          </span>
        )}
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div
        className={`dropzone ${dragging ? "drag" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          upload(e.dataTransfer.files);
        }}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
      >
        <div className="empty-icon">
          <FileUp size={24} />
        </div>
        <strong style={{ color: "var(--text-primary)" }}>Drop PDFs here or click to browse</strong>
        <span className="muted">Text-based PDFs up to 25 MB each</span>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files) upload(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {uploads.length > 0 && (
        <div className="uploads">
          {uploads.slice(0, 6).map((u) => (
            <div className="upload-row" key={u.id}>
              {u.state === "uploading" && <Loader2 size={16} className="spin muted" />}
              {u.state === "done" && <CheckCircle2 size={16} color="var(--good)" />}
              {u.state === "error" && <XCircle size={16} color="var(--critical)" />}
              <strong>{u.name}</strong>
              <span className={u.state === "error" ? "" : "muted"} style={u.state === "error" ? { color: "var(--critical-ink)" } : undefined}>
                {u.state === "uploading" ? "Parsing, chunking and embedding…" : u.message}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="card table-wrap" style={{ marginTop: 20 }}>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Status</th>
              <th className="num">Pages</th>
              <th className="num">Chunks</th>
              <th className="num">Size</th>
              <th>Added</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {documents === null && (
              <tr>
                <td colSpan={7} className="muted">
                  Loading…
                </td>
              </tr>
            )}
            {documents?.length === 0 && (
              <tr>
                <td colSpan={7} className="muted">
                  No documents yet. Upload your first PDF above.
                </td>
              </tr>
            )}
            {documents?.map((doc) => (
              <tr key={doc.id}>
                <td className="wrap">
                  <strong>{doc.filename}</strong>
                  {doc.error && <div style={{ color: "var(--critical-ink)", fontSize: 12 }}>{doc.error}</div>}
                </td>
                <td>
                  <span
                    className={`pill ${doc.status === "ready" ? "pill-good" : doc.status === "failed" ? "pill-critical" : "pill-neutral"}`}
                  >
                    {doc.status === "ready" ? <CheckCircle2 size={12} /> : doc.status === "failed" ? <XCircle size={12} /> : <Loader2 size={12} className="spin" />}
                    {doc.status[0].toUpperCase() + doc.status.slice(1)}
                  </span>
                </td>
                <td className="num">{doc.num_pages}</td>
                <td className="num">{doc.num_chunks}</td>
                <td className="num">{formatBytes(doc.size_bytes)}</td>
                <td className="secondary">{formatDateTime(doc.created_at)}</td>
                <td className="num">
                  <button className="icon-btn" onClick={() => remove(doc)} aria-label={`Delete ${doc.filename}`}>
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
