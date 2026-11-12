import { BarChart3, FileText, MessageSquare, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { api } from "../api/client";
import type { ReadyStatus } from "../api/types";

const NAV = [
  { to: "/", label: "Ask", icon: MessageSquare, end: true },
  { to: "/documents", label: "Documents", icon: FileText, end: false },
  { to: "/analytics", label: "Analytics", icon: BarChart3, end: false },
];

export default function Layout() {
  const [ready, setReady] = useState<ReadyStatus | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const poll = () =>
      api
        .ready()
        .then((status) => !cancelled && (setReady(status), setOffline(false)))
        .catch(() => !cancelled && setOffline(true));
    poll();
    const timer = window.setInterval(poll, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const healthy = !offline && ready?.status === "ok";

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <ShieldCheck size={18} />
          </span>
          Attest RAG
        </div>
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className="nav-link">
            <Icon size={18} />
            <span>{label}</span>
          </NavLink>
        ))}
        <div className="sidebar-footer">
          <div className="health">
            <span className={`dot ${healthy ? "ok" : offline || ready ? "bad" : ""}`} />
            {offline ? "API unreachable" : healthy ? "All systems operational" : "Checking…"}
          </div>
          {ready && (
            <>
              <div>
                Provider: <strong>{ready.provider}</strong>
              </div>
              <div>
                Guardrails: <strong>{ready.judge_enabled ? ready.guardrail_mode : "off"}</strong>
              </div>
              <div>{ready.indexed_chunks.toLocaleString()} chunks indexed</div>
            </>
          )}
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
