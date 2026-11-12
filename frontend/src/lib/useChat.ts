import { useCallback, useRef, useState } from "react";
import { streamChat } from "../api/client";
import type { CheckName, Evaluation, Latency, QueryStatus, Source, StreamEvent } from "../api/types";

export interface UserMessage {
  id: string;
  role: "user";
  content: string;
}

export interface AssistantMessage {
  id: string;
  role: "assistant";
  content: string;
  phase: "retrieving" | "generating" | "judging" | "done";
  guardrailMode?: "stream" | "strict";
  sources: Source[];
  evaluation?: Evaluation;
  blocked?: { reasons: CheckName[]; message: string; retracted: string };
  status?: QueryStatus;
  latency?: Latency;
  queryId?: string;
  error?: string;
}

export type Message = UserMessage | AssistantMessage;

function sessionId(): string {
  const KEY = "attest-rag.session";
  try {
    const existing = sessionStorage.getItem(KEY);
    if (existing) return existing;
    const fresh = crypto.randomUUID();
    sessionStorage.setItem(KEY, fresh);
    return fresh;
  } catch {
    return crypto.randomUUID();
  }
}

/** Reducer applying one SSE event to the in-progress assistant message. */
export function applyEvent(message: AssistantMessage, event: StreamEvent): AssistantMessage {
  switch (event.type) {
    case "start":
      return { ...message, queryId: event.query_id, guardrailMode: event.guardrail_mode };
    case "sources":
      return {
        ...message,
        sources: event.sources,
        phase: message.guardrailMode === "strict" ? "judging" : "generating",
      };
    case "token":
      return { ...message, content: message.content + event.content, phase: "generating" };
    case "evaluation": {
      const { type: _type, ...evaluation } = event;
      void _type;
      return { ...message, evaluation };
    }
    case "blocked":
      return {
        ...message,
        blocked: { reasons: event.reasons, message: event.message, retracted: message.content },
        content: "",
      };
    case "done": {
      const cited = new Set(event.cited);
      return {
        ...message,
        phase: "done",
        status: event.status,
        latency: event.latency,
        queryId: event.query_id,
        sources: message.sources.map((s) => ({ ...s, cited: cited.has(s.index) })),
      };
    }
    case "error":
      return { ...message, phase: "done", status: "error", error: event.message };
  }
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const session = useRef(sessionId());

  const send = useCallback(
    async (question: string, documentIds: string[]) => {
      const text = question.trim();
      if (!text || busy) return;

      const history = messages
        .filter((m) => m.role === "user" || (m.phase === "done" && !m.blocked && !m.error))
        .slice(-6)
        .map((m) => ({ role: m.role, content: m.content }));

      const assistantId = crypto.randomUUID();
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "user", content: text },
        { id: assistantId, role: "assistant", content: "", phase: "retrieving", sources: [] },
      ]);
      setBusy(true);

      const update = (fn: (m: AssistantMessage) => AssistantMessage) =>
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId && m.role === "assistant" ? fn(m) : m)),
        );

      const controller = new AbortController();
      abortRef.current = controller;
      try {
        await streamChat(
          {
            question: text,
            session_id: session.current,
            document_ids: documentIds.length ? documentIds : undefined,
            history,
          },
          (event) => update((m) => applyEvent(m, event)),
          controller.signal,
        );
        update((m) =>
          m.phase === "done" ? m : { ...m, phase: "done", status: m.status ?? "answered" },
        );
      } catch (err) {
        const aborted = controller.signal.aborted;
        update((m) => ({
          ...m,
          phase: "done",
          status: "error",
          error: aborted ? "Stopped." : err instanceof Error ? err.message : "Request failed",
        }));
      } finally {
        abortRef.current = null;
        setBusy(false);
      }
    },
    [busy, messages],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);
  const reset = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
  }, []);

  return { messages, busy, send, stop, reset };
}
