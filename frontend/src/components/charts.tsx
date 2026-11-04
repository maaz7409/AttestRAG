import type { ReactNode } from "react";

/** Series colors come from CSS tokens so light/dark mode swap in one place. */
export const SERIES = {
  s1: "var(--series-1)",
  s2: "var(--series-2)",
  s3: "var(--series-3)",
  critical: "var(--critical)",
};

export const AXIS = {
  stroke: "var(--axis)",
  tick: { fill: "var(--text-muted)", fontSize: 11 },
  tickLine: false,
};

export const GRID = { stroke: "var(--grid)", strokeDasharray: "0", vertical: false };

export function ChartCard({
  title,
  subtitle,
  legend,
  children,
}: {
  title: string;
  subtitle?: string;
  legend?: Array<{ label: string; color: string; box?: boolean }>;
  children: ReactNode;
}) {
  return (
    <section className="card chart-card">
      <header>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </header>
      <div className="chart-body">{children}</div>
      {legend && legend.length > 1 && (
        <div className="legend">
          {legend.map((item) => (
            <span key={item.label}>
              <span
                className={`legend-key ${item.box ? "box" : ""}`}
                style={{ background: item.color }}
              />
              {item.label}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

interface TooltipEntry {
  name?: unknown;
  value?: unknown;
  color?: string;
  dataKey?: unknown;
}

/** Shared tooltip: values lead, labels follow, keyed by a short line of the series color. */
export function ChartTooltip({
  active,
  payload,
  label,
  formatLabel,
  formatValue,
}: {
  active?: boolean;
  payload?: readonly TooltipEntry[];
  label?: string | number;
  formatLabel?: (label: string) => string;
  formatValue?: (value: number, key: string) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      <div className="tooltip-title">{formatLabel ? formatLabel(String(label)) : label}</div>
      {payload.map((entry) => {
        const raw = Array.isArray(entry.value) ? entry.value[0] : entry.value;
        const value =
          raw == null || raw === ""
            ? "–"
            : formatValue
              ? formatValue(Number(raw), String(entry.dataKey))
              : typeof raw === "number"
                ? raw.toLocaleString()
                : String(raw);
        return (
          <div className="tooltip-row" key={String(entry.dataKey)}>
            <span className="legend-key" style={{ background: entry.color }} />
            <strong>{value}</strong>
            <span>{String(entry.name ?? "")}</span>
          </div>
        );
      })}
    </div>
  );
}

export function StatTile({ label, value, sub }: { label: string; value: string; sub?: ReactNode }) {
  return (
    <div className="card tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {sub && <div className="tile-sub">{sub}</div>}
    </div>
  );
}
