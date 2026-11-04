import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type { AnalyticsOverview, QuerySummary } from "../api/types";
import { AXIS, ChartCard, ChartTooltip, GRID, SERIES, StatTile } from "../components/charts";
import QueryDrawer from "../components/QueryDrawer";
import { StatusPill, VerdictPill } from "../components/StatusPill";
import {
  CHECK_LABELS,
  formatDateTime,
  formatDay,
  formatMs,
  formatPct,
  formatScore,
} from "../lib/format";

const WINDOWS = [7, 14, 30];
const STATUS_FILTERS = [
  { value: "", label: "All" },
  { value: "answered", label: "Answered" },
  { value: "blocked", label: "Blocked" },
  { value: "no_context", label: "No context" },
];
const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0];
const HBAR_RADIUS: [number, number, number, number] = [0, 4, 4, 0];
const CURSOR = { fill: "var(--surface-3)", opacity: 0.6 };

export default function AnalyticsPage() {
  const [days, setDays] = useState(14);
  const [data, setData] = useState<AnalyticsOverview | null>(null);
  const [queries, setQueries] = useState<{ items: QuerySummary[]; total: number } | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([api.analytics(days), api.listQueries(15, 0, statusFilter || undefined)])
      .then(([overview, recent]) => {
        setData(overview);
        setQueries(recent);
        setError(null);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [days, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const closeDrawer = useCallback(() => setSelected(null), []);

  const series = data?.timeseries.map((p) => ({ ...p, delivered: p.queries - p.blocked })) ?? [];
  const breakdown = data
    ? [
        { stage: "Retrieval", ms: data.latency.avg_retrieval_ms ?? 0 },
        { stage: "Generation", ms: data.latency.avg_generation_ms ?? 0 },
        { stage: "Judge", ms: data.latency.avg_evaluation_ms ?? 0 },
      ]
    : [];
  const failed = data?.failed_checks.map((c) => ({ ...c, label: CHECK_LABELS[c.name] ?? c.name })) ?? [];

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Analytics</h1>
          <p>Query volume, latency and LLM-as-a-Judge quality scores from the PostgreSQL query trail.</p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <div className="segmented" role="tablist" aria-label="Time window">
            {WINDOWS.map((w) => (
              <button key={w} className={w === days ? "active" : ""} onClick={() => setDays(w)}>
                {w}d
              </button>
            ))}
          </div>
          <button className="btn" onClick={load} disabled={loading} aria-label="Refresh">
            <RefreshCw size={15} className={loading ? "spin" : ""} />
          </button>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {data && (
        <>
          <div className="tiles">
            <StatTile
              label="Queries"
              value={data.totals.queries.toLocaleString()}
              sub={`${data.totals.documents} docs · ${data.totals.chunks.toLocaleString()} chunks`}
            />
            <StatTile
              label="Judge pass rate"
              value={formatPct(data.quality.pass_rate)}
              sub={`${data.quality.evaluated} answers evaluated`}
            />
            <StatTile
              label="Avg faithfulness"
              value={formatScore(data.quality.avg_faithfulness)}
              sub={`Context relevance ${formatScore(data.quality.avg_context_relevance)}`}
            />
            <StatTile
              label="p95 latency"
              value={formatMs(data.latency.p95_total_ms)}
              sub={`p50 ${formatMs(data.latency.p50_total_ms)} · TTFT ${formatMs(data.latency.avg_ttft_ms)}`}
            />
            <StatTile
              label="Blocked answers"
              value={data.totals.blocked.toLocaleString()}
              sub={`${data.totals.no_context} without context · ${data.totals.errors} errors`}
            />
          </div>

          <div className="charts">
            <ChartCard
              title="Query volume"
              subtitle="Questions per day; blocked = withheld by the judge"
              legend={[
                { label: "Delivered", color: SERIES.s1, box: true },
                { label: "Blocked", color: SERIES.critical, box: true },
              ]}
            >
              <ResponsiveContainer>
                <BarChart data={series} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
                  <CartesianGrid {...GRID} />
                  <XAxis dataKey="date" tickFormatter={formatDay} {...AXIS} minTickGap={16} />
                  <YAxis allowDecimals={false} {...AXIS} axisLine={false} />
                  <Tooltip
                    cursor={CURSOR}
                    content={(props) => <ChartTooltip {...props} formatLabel={formatDay} />}
                  />
                  <Bar dataKey="delivered" name="Delivered" stackId="q" fill={SERIES.s1} />
                  <Bar
                    dataKey="blocked"
                    name="Blocked"
                    stackId="q"
                    fill={SERIES.critical}
                    radius={BAR_RADIUS}
                  />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard
              title="End-to-end latency"
              subtitle="Average and 95th percentile per day"
              legend={[
                { label: "Average", color: SERIES.s1 },
                { label: "p95", color: SERIES.s2 },
              ]}
            >
              <ResponsiveContainer>
                <LineChart data={series} margin={{ top: 4, right: 8, left: -4, bottom: 0 }}>
                  <CartesianGrid {...GRID} />
                  <XAxis dataKey="date" tickFormatter={formatDay} {...AXIS} minTickGap={16} />
                  <YAxis tickFormatter={(v) => formatMs(v)} {...AXIS} axisLine={false} width={56} />
                  <Tooltip
                    content={(props) => (
                      <ChartTooltip {...props} formatLabel={formatDay} formatValue={(v) => formatMs(v)} />
                    )}
                  />
                  <Line
                    type="monotone"
                    dataKey="avg_latency_ms"
                    name="Average"
                    stroke={SERIES.s1}
                    strokeWidth={2}
                    dot={{ r: 4, fill: SERIES.s1, stroke: "var(--surface-2)", strokeWidth: 2 }}
                    activeDot={{ r: 5, stroke: "var(--surface-2)", strokeWidth: 2 }}
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="p95_latency_ms"
                    name="p95"
                    stroke={SERIES.s2}
                    strokeWidth={2}
                    dot={{ r: 4, fill: SERIES.s2, stroke: "var(--surface-2)", strokeWidth: 2 }}
                    activeDot={{ r: 5, stroke: "var(--surface-2)", strokeWidth: 2 }}
                    connectNulls
                  />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard
              title="Answer quality over time"
              subtitle="Daily average judge scores (0 – 1)"
              legend={[
                { label: "Faithfulness", color: SERIES.s1 },
                { label: "Context relevance", color: SERIES.s2 },
              ]}
            >
              <ResponsiveContainer>
                <LineChart data={series} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                  <CartesianGrid {...GRID} />
                  <XAxis dataKey="date" tickFormatter={formatDay} {...AXIS} minTickGap={16} />
                  <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} {...AXIS} axisLine={false} />
                  <Tooltip
                    content={(props) => (
                      <ChartTooltip {...props} formatLabel={formatDay} formatValue={(v) => v.toFixed(2)} />
                    )}
                  />
                  <Line
                    type="monotone"
                    dataKey="avg_faithfulness"
                    name="Faithfulness"
                    stroke={SERIES.s1}
                    strokeWidth={2}
                    dot={{ r: 4, fill: SERIES.s1, stroke: "var(--surface-2)", strokeWidth: 2 }}
                    activeDot={{ r: 5, stroke: "var(--surface-2)", strokeWidth: 2 }}
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="avg_context_relevance"
                    name="Context relevance"
                    stroke={SERIES.s2}
                    strokeWidth={2}
                    dot={{ r: 4, fill: SERIES.s2, stroke: "var(--surface-2)", strokeWidth: 2 }}
                    activeDot={{ r: 5, stroke: "var(--surface-2)", strokeWidth: 2 }}
                    connectNulls
                  />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Latency breakdown" subtitle="Average time spent per pipeline stage">
              <ResponsiveContainer>
                <BarChart
                  data={breakdown}
                  layout="vertical"
                  margin={{ top: 4, right: 16, left: 8, bottom: 0 }}
                >
                  <CartesianGrid {...GRID} vertical horizontal={false} />
                  <XAxis type="number" tickFormatter={(v) => formatMs(v)} {...AXIS} />
                  <YAxis type="category" dataKey="stage" width={96} {...AXIS} axisLine={false} />
                  <Tooltip
                    cursor={CURSOR}
                    content={(props) => <ChartTooltip {...props} formatValue={(v) => formatMs(v)} />}
                  />
                  <Bar dataKey="ms" name="Average" fill={SERIES.s1} radius={HBAR_RADIUS} barSize={18} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard
              title="Judge score distribution"
              subtitle="Number of answers per score bucket"
              legend={[
                { label: "Faithfulness", color: SERIES.s1, box: true },
                { label: "Context relevance", color: SERIES.s2, box: true },
                { label: "Answer relevance", color: SERIES.s3, box: true },
              ]}
            >
              <ResponsiveContainer>
                <BarChart
                  data={data.score_distribution}
                  margin={{ top: 4, right: 4, left: -16, bottom: 0 }}
                  barGap={2}
                >
                  <CartesianGrid {...GRID} />
                  <XAxis dataKey="bucket" {...AXIS} />
                  <YAxis allowDecimals={false} {...AXIS} axisLine={false} />
                  <Tooltip
                    cursor={CURSOR}
                    content={(props) => <ChartTooltip {...props} formatLabel={(l) => `Score ${l}`} />}
                  />
                  <Bar dataKey="faithfulness" name="Faithfulness" fill={SERIES.s1} radius={BAR_RADIUS} />
                  <Bar
                    dataKey="context_relevance"
                    name="Context relevance"
                    fill={SERIES.s2}
                    radius={BAR_RADIUS}
                  />
                  <Bar
                    dataKey="answer_relevance"
                    name="Answer relevance"
                    fill={SERIES.s3}
                    radius={BAR_RADIUS}
                  />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Most cited documents" subtitle="Citations in delivered answers">
              {data.top_documents.length === 0 ? (
                <div className="empty">No citations yet</div>
              ) : (
                <ResponsiveContainer>
                  <BarChart
                    data={data.top_documents}
                    layout="vertical"
                    margin={{ top: 4, right: 16, left: 8, bottom: 0 }}
                  >
                    <CartesianGrid {...GRID} vertical horizontal={false} />
                    <XAxis type="number" allowDecimals={false} {...AXIS} />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={140}
                      {...AXIS}
                      axisLine={false}
                      tickFormatter={(v: string) => (v.length > 20 ? `${v.slice(0, 19)}…` : v)}
                    />
                    <Tooltip cursor={CURSOR} content={(props) => <ChartTooltip {...props} />} />
                    <Bar dataKey="count" name="Citations" fill={SERIES.s1} radius={HBAR_RADIUS} barSize={16} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </ChartCard>
          </div>

          {failed.length > 0 && (
            <div className="card card-pad" style={{ marginBottom: 16 }}>
              <h2>Failed guardrail checks</h2>
              <div className="meta-row" style={{ marginTop: 8, fontSize: 13 }}>
                {failed.map((f) => (
                  <span key={f.name} className="pill pill-warning">
                    {f.label}: {f.count}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      <div className="card">
        <div
          className="card-pad"
          style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}
        >
          <div>
            <h2>Query trail</h2>
            <span className="muted" style={{ fontSize: 12 }}>
              {queries ? `${queries.total.toLocaleString()} queries logged · click a row for the full audit record` : ""}
            </span>
          </div>
          <div className="segmented" aria-label="Filter by status">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.value}
                className={statusFilter === f.value ? "active" : ""}
                onClick={() => setStatusFilter(f.value)}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Question</th>
                <th>Status</th>
                <th>Verdict</th>
                <th className="num">Faithful.</th>
                <th className="num">Relevance</th>
                <th className="num">Latency</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {queries?.items.length === 0 && (
                <tr>
                  <td colSpan={7} className="muted">
                    No queries yet. Ask something on the chat page.
                  </td>
                </tr>
              )}
              {queries?.items.map((q) => (
                <tr key={q.id} className="clickable" onClick={() => setSelected(q.id)}>
                  <td className="wrap">{q.question}</td>
                  <td>
                    <StatusPill status={q.status} />
                  </td>
                  <td>
                    <VerdictPill passed={q.passed} blocked={q.status === "blocked"} />
                  </td>
                  <td className="num">{formatScore(q.faithfulness)}</td>
                  <td className="num">{formatScore(q.context_relevance)}</td>
                  <td className="num">{formatMs(q.total_ms)}</td>
                  <td className="secondary">{formatDateTime(q.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {selected && <QueryDrawer queryId={selected} onClose={closeDrawer} />}
    </div>
  );
}
