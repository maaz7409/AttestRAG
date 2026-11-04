import { AlertTriangle, CheckCircle2, CircleSlash, XCircle } from "lucide-react";
import type { QueryStatus } from "../api/types";

const STATUS: Record<QueryStatus, { label: string; tone: string; Icon: typeof CheckCircle2 }> = {
  answered: { label: "Answered", tone: "pill-good", Icon: CheckCircle2 },
  blocked: { label: "Blocked", tone: "pill-critical", Icon: XCircle },
  no_context: { label: "No context", tone: "pill-neutral", Icon: CircleSlash },
  error: { label: "Error", tone: "pill-warning", Icon: AlertTriangle },
};

export function StatusPill({ status }: { status: QueryStatus }) {
  const { label, tone, Icon } = STATUS[status] ?? STATUS.error;
  return (
    <span className={`pill ${tone}`}>
      <Icon size={12} />
      {label}
    </span>
  );
}

export function VerdictPill({ passed, blocked }: { passed: boolean | null; blocked?: boolean }) {
  if (passed == null) return <span className="pill pill-neutral">Not evaluated</span>;
  if (blocked)
    return (
      <span className="pill pill-critical">
        <XCircle size={12} /> Blocked
      </span>
    );
  return passed ? (
    <span className="pill pill-good">
      <CheckCircle2 size={12} /> Verified
    </span>
  ) : (
    <span className="pill pill-warning">
      <AlertTriangle size={12} /> Flagged
    </span>
  );
}
