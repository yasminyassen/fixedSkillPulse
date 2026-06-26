import { useCallback, useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Brain,
  CheckCircle2,
  GitBranch,
  Gauge,
  Layers,
  LineChart as LineChartIcon,
  RefreshCcw,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  Users,
  ChevronDown,
  Lock,
  Unlock,
  Building2,
  CalendarClock,
  GitCommitHorizontal,
  BadgeCheck,
  Bug,
  Flame,
  Copy,
  Zap,
  Award,
  AlertCircle,
  Star,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import api from "../../api/auth";
import DashboardLayout from "../DashboardLayout";

// ─── Types ──────────────────────────────────────────────────────────────────

interface Repo {
  id: number;
  name: string | null;
  full_name: string | null;
  is_private?: boolean;
  last_analyzed_at?: string | null;
  analysis_count: number;
  member_count: number;
}

interface RepositorySummary {
  analysis_run_id: number | null;
  repository_id: number | null;
  repository_name: string | null;
  organization: string | null;
  branch: string | null;
  last_analysis: string | null;
  analyzed_on: string | null;
  overall_repository_score: number | null;
  repository_status: string;
}

interface MetricCard {
  key: string;
  label: string;
  value: number | string | null;
  unit: string | null;
  status: string | null;
}

interface ContributorHighlight {
  id: number | null;
  full_name: string | null;
  username: string | null;
  score: number | null;
  reasoning: string | null;
}

interface TeamPerformance {
  average_team_score: number | null;
  average_team_security_score: number | null;
  average_coverage: number | null;
  average_code_smells: number | null;
  best_contributor: ContributorHighlight | null;
  needs_support_contributor: ContributorHighlight | null;
  total_contributors: number;
}

interface ContributorRow {
  id: number;
  developer: string;
  username: string;
  role: string | null;
  skill_score: number | null;
  health_score: number | null;
  security_score: number | null;
  coverage: number | null;
  bugs: number | null;
  code_smells: number | null;
  complexity: number | null;
  status: string;
}

interface TrendPoint {
  period: string;
  label: string;
  health_score: number | null;
  security_score: number | null;
}

interface RiskItem {
  title: string;
  detail: string | null;
  file_path: string | null;
  metric: number | string | null;
  severity: string | null;
  count: number | null;
}

interface RiskGroups {
  high_code_smells: RiskItem[];
  high_bug_files: RiskItem[];
  files_for_bugs: RiskItem[];
}

interface Recommendations {
  fix_first: string[];
  prioritize_next: string[];
  plan_when_possible: string[];
  strengthen_further: string[];
  actionable_recommendations: string[];
  prioritized_team_next_moves: string[];
  team_improvement_guidance: string[];
  best_contributor_reasoning: string | null;
  needs_support_reasoning: string | null;
  architectural_concerns: string[];
  delivery_risks: string[];
  quality_concerns: string[];
  team_strengths: string[];
  recommended_priorities: string[];
}

interface Overview {
  repositories: Repo[];
  repository_summary: RepositorySummary;
  repository_metrics: MetricCard[];
  team_performance: TeamPerformance;
  contributors: ContributorRow[];
  trends: TrendPoint[];
  risks: RiskGroups;
  recommendations: Recommendations;
}

// ─── Defaults ────────────────────────────────────────────────────────────────

const emptyOverview: Overview = {
  repositories: [],
  repository_summary: {
    analysis_run_id: null, repository_id: null, repository_name: null,
    organization: null, branch: null, last_analysis: null, analyzed_on: null,
    overall_repository_score: null, repository_status: "Unavailable",
  },
  repository_metrics: [],
  team_performance: {
    average_team_score: null, average_team_security_score: null,
    average_coverage: null, average_code_smells: null,
    best_contributor: null, needs_support_contributor: null, total_contributors: 0,
  },
  contributors: [],
  trends: [],
  risks: { high_code_smells: [], high_bug_files: [], files_for_bugs: [] },
  recommendations: {
    fix_first: [], prioritize_next: [], plan_when_possible: [], strengthen_further: [],
    actionable_recommendations: [], prioritized_team_next_moves: [],
    team_improvement_guidance: [], best_contributor_reasoning: null,
    needs_support_reasoning: null, architectural_concerns: [], delivery_risks: [],
    quality_concerns: [], team_strengths: [], recommended_priorities: [],
  },
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

const accent = "#8b5cf6";

const accentByMetric: Record<string, string> = {
  overall_score: "#14b8a6",
  sonar_health_score: "#3b82f6",
  security_score: "#22c55e",
  coverage: "#06b6d4",
  bugs: "#ef4444",
  code_smells: "#f97316",
  duplication: "#f59e0b",
  complexity: "#ec4899",
};

const fmtNumber = (value: number | null | undefined, digits = 0) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(digits);
};

const fmtMetric = (metric?: MetricCard) => {
  if (!metric || metric.value === null || metric.value === undefined || metric.value === "") return "—";
  if (typeof metric.value === "number") {
    const digits = metric.key === "coverage" || metric.key === "duplication" ? 1 : 0;
    return `${metric.value.toFixed(digits)}${metric.unit || ""}`;
  }
  return `${metric.value}${metric.unit || ""}`;
};

const fmtPlainMetric = (value: number | string | null | undefined, unit = "", digits = 0) => {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return `${value.toFixed(digits)}${unit}`;
  return `${value}${unit}`;
};

const fmtDate = (value: string | null | undefined) => {
  if (!value) return "Unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unavailable";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });
};

const scoreColor = (score: number | null | undefined) => {
  if (score === null || score === undefined) return "#94a3b8";
  const safe = Math.max(0, Math.min(100, score));
  if (safe >= 90) return "#22c55e";
  if (safe >= 75) return "#14b8a6";
  if (safe >= 60) return "#f59e0b";
  return "#ef4444";
};

const statusClass = (status: string | null | undefined) => {
  const n = (status || "").toLowerCase();
  if (n.includes("excellent")) return "excellent";
  if (n.includes("good")) return "good";
  if (n.includes("low")) return "good";
  if (n.includes("fair")) return "fair";
  if (n.includes("medium")) return "fair";
  if (n.includes("high")) return "support";
  if (n.includes("support") || n.includes("improvement")) return "support";
  return "neutral";
};

// ─── Tab definitions ──────────────────────────────────────────────────────────

type TabKey = "overview" | "team" | "contributors" | "trends" | "risks" | "recommendations";

const TABS: { key: TabKey; label: string; icon: ReactNode }[] = [
  { key: "overview",         label: "Repository Health",   icon: <Gauge size={15} /> },
  { key: "team",             label: "Team Performance",    icon: <Users size={15} /> },
  { key: "contributors",     label: "Contributors",        icon: <BarChart3 size={15} /> },
  { key: "trends",           label: "Trends",              icon: <LineChartIcon size={15} /> },
  { key: "risks",            label: "Risks & Insights",    icon: <AlertTriangle size={15} /> },
  { key: "recommendations",  label: "Recommendations",     icon: <Sparkles size={15} /> },
];

// ─── Sub-components ───────────────────────────────────────────────────────────

function MetricTile({ metric }: { metric: MetricCard }) {
  const color = accentByMetric[metric.key] || "#64748b";
  const iconMap: Record<string, ReactNode> = {
    overall_score: <Star size={17} />,
    sonar_health_score: <ShieldCheck size={17} />,
    security_score: <BadgeCheck size={17} />,
    coverage: <GitCommitHorizontal size={17} />,
    bugs: <Bug size={17} />,
    code_smells: <Flame size={17} />,
    duplication: <Copy size={17} />,
    complexity: <Zap size={17} />,
  };
  return (
    <article className="m-metric-tile">
      <span className="m-metric-icon" style={{ background: `${color}18`, color }}>{iconMap[metric.key] || <Gauge size={17} />}</span>
      <div>
        <small className="m-label">{metric.label}</small>
        <strong className="m-metric-value" style={{ color }}>{fmtMetric(metric)}</strong>
        {metric.status && <em className={`m-status ${statusClass(metric.status)}`}>{metric.status}</em>}
      </div>
    </article>
  );
}

function SummaryItem({ label, value, icon }: { label: string; value: ReactNode; icon?: ReactNode }) {
  return (
    <div className="m-summary-item">
      {icon && <span className="m-summary-icon">{icon}</span>}
      <div>
        <small className="m-label">{label}</small>
        <strong className="m-summary-value">{value}</strong>
      </div>
    </div>
  );
}

function ScoreRingMetric({ label, value, unit = "", description }: { label: string; value: number | null; unit?: string; description: string }) {
  const safe = value === null ? 0 : Math.max(0, Math.min(100, Number(value)));
  const status = value === null ? "Unavailable" : safe >= 80 ? "Excellent" : safe >= 60 ? "Fair" : "Needs Attention";
  const color = scoreColor(value);

  // SVG ring params
  const R = 52;
  const cx = 68;
  const cy = 68;
  const circumference = 2 * Math.PI * R;
  // We draw a 270° arc (from 135° to 405°) — classic dashboard gauge sweep
  const sweepFraction = 270 / 360;
  const trackLen = circumference * sweepFraction;
  const fillLen = (safe / 100) * trackLen;
  const gapLen = circumference - trackLen;

  // Rotate so arc starts at bottom-left (135°)
  const startAngle = 135;

  // Zone markers at 60 and 80
  const toXY = (pct: number) => {
    const angle = (startAngle + pct * 270) * (Math.PI / 180);
    return { x: cx + R * Math.cos(angle), y: cy + R * Math.sin(angle) };
  };
  const m60 = toXY(0.6);
  const m80 = toXY(0.8);

  return (
    <article className="m-ring-card">
      <span className="m-label" style={{ display: "block", marginBottom: 0 }}>{label}</span>
      <p className="m-ring-desc">{description}</p>
      <div className="m-ring-body">
        <svg width="136" height="136" viewBox="0 0 136 136" aria-label={`${label}: ${safe}`}>
          {/* track */}
          <circle
            cx={cx} cy={cy} r={R}
            fill="none"
            stroke="rgba(148,163,184,0.14)"
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={`${trackLen} ${gapLen}`}
            strokeDashoffset={0}
            transform={`rotate(${startAngle} ${cx} ${cy})`}
          />
          {/* fill */}
          <circle
            cx={cx} cy={cy} r={R}
            fill="none"
            stroke={color}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={`${fillLen} ${circumference - fillLen}`}
            strokeDashoffset={0}
            transform={`rotate(${startAngle} ${cx} ${cy})`}
            style={{ filter: `drop-shadow(0 0 6px ${color}88)`, transition: "stroke-dasharray 0.5s ease" }}
          />
          {/* zone tick at 60 */}
          <line x1={m60.x} y1={m60.y} x2={cx + (R - 10) * Math.cos((startAngle + 0.6 * 270) * Math.PI / 180)} y2={cy + (R - 10) * Math.sin((startAngle + 0.6 * 270) * Math.PI / 180)} stroke="rgba(255,255,255,0.35)" strokeWidth="2" strokeLinecap="round" />
          {/* zone tick at 80 */}
          <line x1={m80.x} y1={m80.y} x2={cx + (R - 10) * Math.cos((startAngle + 0.8 * 270) * Math.PI / 180)} y2={cy + (R - 10) * Math.sin((startAngle + 0.8 * 270) * Math.PI / 180)} stroke="rgba(255,255,255,0.35)" strokeWidth="2" strokeLinecap="round" />
          {/* center value */}
          <text x={cx} y={cy - 6} textAnchor="middle" dominantBaseline="middle" fill={color} fontSize="22" fontWeight="800" fontFamily="'Inter', sans-serif">
            {value === null ? "—" : safe.toFixed(1)}
          </text>
          <text x={cx} y={cy + 16} textAnchor="middle" dominantBaseline="middle" fill="rgba(148,163,184,0.8)" fontSize="11" fontWeight="700">
            {unit || "/ 100"}
          </text>
        </svg>
        <div className="m-ring-legend">
          <div className="m-ring-zone m-ring-zone-red"><span />Needs Attention<em>0–60</em></div>
          <div className="m-ring-zone m-ring-zone-amber"><span />Fair<em>60–80</em></div>
          <div className="m-ring-zone m-ring-zone-green"><span />Excellent<em>80–100</em></div>
        </div>
      </div>
      <span className={`m-score-status ${statusClass(status)}`}>{status}</span>
    </article>
  );
}

function CodeSmellsMetric({ value }: { value: number | null }) {
  const n = value ?? 0;
  const status = value === null ? "Unavailable" : n === 0 ? "Clean" : n <= 5 ? "Low" : n <= 15 ? "Moderate" : "High";
  const smellColor = n === 0 ? "#22c55e" : n <= 5 ? "#14b8a6" : n <= 15 ? "#f59e0b" : "#ef4444";

  // Segmented bar: 3 zones — Clean (0-5), Moderate (5-15), High (15-20+)
  // Each zone is a fixed visual width; active zone gets highlighted
  const zones = [
    { label: "Clean",    range: "0–5",   color: "#22c55e", active: n <= 5 },
    { label: "Moderate", range: "5–15",  color: "#f59e0b", active: n > 5 && n <= 15 },
    { label: "High",     range: "15+",   color: "#ef4444", active: n > 15 },
  ];

  // Spark-style mini bar chart — simulated distribution
  // 8 bars showing an illustrative code smell distribution
  const sparkBars = [2, 5, 8, 14, n, 11, 6, 3];
  const maxBar = Math.max(...sparkBars, 1);

  return (
    <article className="m-smells-card">
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: 14 }}>
        <span className="m-label" style={{ marginBottom: 0 }}>Count Of Code Smells</span>
        <strong style={{ color: smellColor, fontSize: 28, fontFamily: "'Inter', sans-serif", fontWeight: 800, lineHeight: 1 }}>
          {value === null ? "—" : n.toFixed(0)}
        </strong>
      </div>

      {/* Zone pills */}
      <div style={{ display: "flex", gap: 6, marginBottom: 18 }}>
        {zones.map(zone => (
          <div
            key={zone.label}
            style={{
              flex: 1, borderRadius: 10, padding: "8px 10px",
              background: zone.active ? `${zone.color}20` : "rgba(148,163,184,0.07)",
              border: `1px solid ${zone.active ? `${zone.color}50` : "var(--border)"}`,
              transition: "all 0.2s",
            }}
          >
            <div style={{ fontSize: 11, fontWeight: 800, color: zone.active ? zone.color : "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>{zone.label}</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>{zone.range}</div>
          </div>
        ))}
      </div>

      {/* Mini bar chart */}
      <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 52, marginBottom: 10 }}>
        {sparkBars.map((bar, i) => {
          const isActive = i === 4;
          return (
            <div
              key={i}
              style={{
                flex: 1,
                height: `${(bar / maxBar) * 100}%`,
                borderRadius: "4px 4px 0 0",
                background: isActive
                  ? smellColor
                  : `rgba(148,163,184,${isActive ? 1 : 0.2})`,
                boxShadow: isActive ? `0 0 8px ${smellColor}66` : "none",
                transition: "height 0.4s ease",
              }}
            />
          );
        })}
      </div>
      <div style={{ borderTop: "1px solid var(--border)", paddingTop: 10, marginTop: 4 }}>
        <span className={`m-score-status ${statusClass(status)}`}>{status} maintainability</span>
      </div>
    </article>
  );
}

function HighlightCard({ title, person, icon }: { title: string; person: ContributorHighlight | null; icon: ReactNode }) {
  return (
    <article className="m-highlight">
      <div className="m-highlight-head">
        <span className="m-highlight-icon">{icon}</span>
        <small className="m-label">{title}</small>
      </div>
      <strong className="m-highlight-name">{person?.full_name || "—"}</strong>
      {person?.username && <span className="m-highlight-username">@{person.username}</span>}
      <p className="m-highlight-reason">{person?.reasoning || "No contributor snapshot available yet."}</p>
    </article>
  );
}

function RiskPanel({ title, items, metricLabel, icon }: { title: string; items: RiskItem[]; metricLabel: string; icon: ReactNode }) {
  return (
    <div className="m-risk-list">
      <div className="m-risk-list-head">
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className="m-risk-icon">{icon}</span>
          <strong className="m-risk-title">{title}</strong>
        </div>
        <span className="m-risk-count">{items.length}</span>
      </div>
      {items.length ? items.map((item, i) => (
        <article key={`${title}-${i}`} className="m-risk-row">
          <div>
            <strong>{item.title}</strong>
            <p>{item.detail || item.file_path || "Detected in latest analysis."}</p>
          </div>
          <span className={`m-risk-badge ${statusClass(item.severity)}`}>
            {metricLabel}: {item.count ?? item.metric ?? "n/a"}
          </span>
        </article>
      )) : <p className="m-empty">No items in this group.</p>}
    </div>
  );
}

function RecommendationGroup({ title, items, tone, icon }: { title: string; items: string[]; tone: string; icon: ReactNode }) {
  return (
    <article className={`m-rec m-rec-${tone}`}>
      <div className="m-rec-head">
        <span className="m-rec-icon">{icon}</span>
        <h3>{title}</h3>
      </div>
      {items.length ? items.map(item => <p key={item}>{item}</p>) : <p className="m-empty">No recommendation generated.</p>}
    </article>
  );
}

// ─── Repo Dropdown ────────────────────────────────────────────────────────────

function RepoDropdown({ repos, selectedRepoId, loading, onChange, dropdownRef }: {
  repos: Repo[];
  selectedRepoId: string;
  loading: boolean;
  onChange: (id: string) => void;
  dropdownRef: RefObject<HTMLDivElement | null>;
}) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [dropdownRef]);

  const selectedRepo = repos.find(r => String(r.id) === selectedRepoId);
  const displayName = selectedRepoId === "latest"
    ? "Latest analyzed repository"
    : selectedRepo?.full_name || selectedRepo?.name || `Repository ${selectedRepoId}`;
  const isPrivate = selectedRepo?.is_private;

  const choose = (id: string) => { onChange(id); setOpen(false); };

  return (
    <div ref={dropdownRef} style={{ position: "relative" }}>
      <button
        type="button"
        className={`m-repo-trigger ${open ? "open" : ""}`}
        disabled={loading}
        onClick={() => setOpen(v => !v)}
      >
        <span className="m-repo-trigger-inner">
          <span className="m-repo-trigger-icon" style={{ color: accent }}>
            {isPrivate ? <Lock size={14} /> : <Unlock size={14} />}
          </span>
          <span>
            <span className="m-repo-trigger-name">{loading ? "Loading repositories…" : displayName}</span>
            <span className="m-repo-trigger-sub">
              {selectedRepo?.member_count != null ? `${selectedRepo.member_count} members` : "Select a repository to analyze"}
            </span>
          </span>
        </span>
        <span className="m-repo-caret" style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)" }}>
          <ChevronDown size={18} />
        </span>
      </button>

      {open && (
        <div className="m-repo-menu">
          <button type="button" className={`m-repo-option ${selectedRepoId === "latest" ? "selected" : ""}`} onClick={() => choose("latest")}>
            <span>
              <span className="m-repo-opt-name">Latest analyzed repository</span>
              <span className="m-repo-opt-sub">Auto-select most recent</span>
            </span>
            {selectedRepoId === "latest" && <span style={{ color: accent, fontWeight: 900 }}>✓</span>}
          </button>
          {repos.map(repo => (
            <button
              type="button"
              key={repo.id}
              className={`m-repo-option ${String(repo.id) === selectedRepoId ? "selected" : ""}`}
              onClick={() => choose(String(repo.id))}
            >
              <span className="m-repo-opt-lock">{repo.is_private ? <Lock size={12} /> : <Unlock size={12} />}</span>
              <span>
                <span className="m-repo-opt-name">{repo.full_name || repo.name || `Repository ${repo.id}`}</span>
                <span className="m-repo-opt-sub">{repo.member_count} members · {repo.analysis_count} analyses</span>
              </span>
              {String(repo.id) === selectedRepoId && <span style={{ color: accent, fontWeight: 900 }}>✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function ManagerDashboard() {
  const [selectedRepoId, setSelectedRepoId] = useState("latest");
  const [trendGranularity, setTrendGranularity] = useState<"daily" | "monthly">("monthly");
  const [data, setData] = useState<Overview>(emptyOverview);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const dropdownRef = useRef<HTMLDivElement | null>(null);

  const fetchOverview = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = selectedRepoId === "latest"
        ? { trend_granularity: trendGranularity }
        : { repo_id: Number(selectedRepoId), trend_granularity: trendGranularity };
      const response = await api.get<Overview>("/manager/dashboard/overview", { params });
      setData(response.data || emptyOverview);
    } catch {
      setError("Unable to load manager dashboard.");
    } finally {
      setLoading(false);
    }
  }, [selectedRepoId, trendGranularity]);

  useEffect(() => { fetchOverview(); }, [fetchOverview]);

  const metricsWithoutGate = data.repository_metrics.filter(m => m.key !== "quality_gate");

  const trendData = data.trends.map(point => ({
    ...point,
    health_score: point.health_score ?? undefined,
    security_score: point.security_score ?? undefined,
  }));

  const score = data.repository_summary.overall_repository_score;

  return (
    <DashboardLayout>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        .m-page {
          min-height: 100vh; padding: 32px 40px 80px;
          color: var(--text-primary);
          font-family: 'Inter', system-ui, sans-serif;
          background: var(--bg-gradient);
        }
        .m-shell { max-width: 1180px; margin: 0 auto; display: flex; flex-direction: column; gap: 0; }

        /* ── Header ── */
        .m-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 28px; flex-wrap: wrap; }
        .m-eyebrow {
          display: inline-flex; align-items: center; gap: 7px;
          padding: 5px 14px; border-radius: 999px;
          border: 1px solid ${accent}40; background: ${accent}12;
          color: ${accent}; font-size: 11px; font-weight: 800;
          letter-spacing: 0.8px; text-transform: uppercase; width: fit-content; margin-bottom: 10px;
        }
        .m-header h1 {
          margin: 0; font-size: 30px; line-height: 1.1; font-weight: 800;
          font-family: 'Inter', sans-serif; letter-spacing: -0.5px;
        }
        .m-header-sub { color: var(--text-muted); margin: 6px 0 0; font-size: 14px; }
        .m-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .m-refresh-btn {
          width: 42px; height: 42px; border: 1px solid var(--border);
          background: var(--bg-card); color: var(--text-primary);
          border-radius: 12px; display: grid; place-items: center;
          cursor: pointer; transition: border-color 0.2s, background 0.2s;
        }
        .m-refresh-btn:hover { border-color: ${accent}80; background: ${accent}12; color: ${accent}; }

        /* ── Repo Dropdown ── */
        .m-repo-trigger {
          min-width: 280px; border: 1px solid rgba(139,92,246,0.28);
          background: var(--bg-input, var(--bg-card)); color: var(--text-primary);
          border-radius: 14px; padding: 11px 15px; cursor: pointer;
          display: flex; align-items: center; justify-content: space-between; gap: 14px;
          font-family: 'Inter', system-ui, sans-serif; text-align: left;
          transition: border-color 0.2s, box-shadow 0.2s;
        }
        .m-repo-trigger:hover, .m-repo-trigger.open {
          border-color: ${accent}80; box-shadow: 0 0 0 4px ${accent}12;
        }
        .m-repo-trigger-inner { display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1; }
        .m-repo-trigger-icon { flex-shrink: 0; }
        .m-repo-trigger-name { display: block; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; }
        .m-repo-trigger-sub { display: block; color: var(--text-muted); font-size: 12px; margin-top: 3px; }
        .m-repo-caret { color: ${accent}; transition: transform 0.2s; flex-shrink: 0; }
        .m-repo-menu {
          position: absolute; z-index: 60; top: calc(100% + 8px); left: 0; right: 0;
          background: #1a1a2e; border: 1px solid rgba(139,92,246,0.4);
          border-radius: 16px;
          box-shadow: 0 24px 60px rgba(0,0,0,0.6), 0 0 0 1px rgba(139,92,246,0.12), inset 0 1px 0 rgba(255,255,255,0.05);
          max-height: 300px; overflow: auto; padding: 8px; backdrop-filter: blur(20px);
        }
        .m-repo-option {
          width: 100%; border: none; cursor: pointer; border-radius: 12px;
          padding: 11px 12px; background: transparent; color: rgba(200,200,220,0.9);
          display: flex; align-items: center; gap: 10px; justify-content: space-between;
          font-family: 'Inter', system-ui, sans-serif; text-align: left;
          transition: background 0.15s, color 0.15s;
        }
        .m-repo-option:hover { background: ${accent}18; color: #fff; }
        .m-repo-option.selected { background: ${accent}22; color: #fff; }
        .m-repo-opt-lock { color: var(--text-muted); flex-shrink: 0; }
        .m-repo-opt-name { display: block; font-weight: 700; font-size: 13.5px; }
        .m-repo-opt-sub { display: block; color: var(--text-muted); font-size: 12px; margin-top: 2px; }

        /* ── Score Band ── */
        .m-score-band {
          display: grid; grid-template-columns: 200px 1fr; gap: 18px;
          border: 1px solid var(--border); border-radius: 20px;
          background: linear-gradient(135deg, rgba(139,92,246,0.1), rgba(20,184,166,0.06));
          padding: 22px; margin-bottom: 24px;
          box-shadow: 0 4px 24px rgba(0,0,0,0.18);
        }
        .m-score-col {
          border-right: 1px solid var(--border); padding-right: 18px;
          display: grid; align-content: center; gap: 8px;
        }
        .m-score-label { color: var(--text-muted); font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.8px; }
        .m-score-number { font-size: 52px; line-height: 1; font-family: 'Inter', sans-serif; font-weight: 800; }
        .m-summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
        .m-summary-item {
          border: 1px solid var(--border); border-radius: 14px;
          background: var(--bg-card); padding: 14px;
          display: flex; align-items: flex-start; gap: 10px;
        }
        .m-summary-icon { color: ${accent}; flex-shrink: 0; margin-top: 2px; }
        .m-summary-value { display: flex; align-items: center; gap: 6px; margin-top: 5px; font-size: 14px; font-weight: 700; overflow-wrap: anywhere; }

        /* ── Tabs ── */
        .m-tabs-wrap { position: sticky; top: 0; z-index: 40; background: var(--bg-gradient); padding: 0 0 0; margin-bottom: 24px; }
        .m-tabs {
          display: flex; gap: 4px; border-bottom: 1px solid var(--border);
          overflow-x: auto; padding-bottom: 0;
          scrollbar-width: none;
        }
        .m-tabs::-webkit-scrollbar { display: none; }
        .m-tab {
          display: inline-flex; align-items: center; gap: 7px;
          padding: 11px 18px; border: none; background: none;
          color: var(--text-muted); cursor: pointer; font-family: 'Inter', system-ui, sans-serif;
          font-size: 13.5px; font-weight: 600; white-space: nowrap;
          border-bottom: 2px solid transparent; margin-bottom: -1px;
          transition: color 0.15s, border-color 0.15s;
        }
        .m-tab:hover { color: var(--text-primary); }
        .m-tab.active { color: ${accent}; border-bottom-color: ${accent}; font-weight: 700; }

        /* ── Section wrapper ── */
        .m-section { display: flex; flex-direction: column; gap: 18px; animation: mFadeIn 0.22s ease; }
        @keyframes mFadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
        .m-section-title { display: flex; align-items: center; gap: 9px; margin-bottom: 4px; }
        .m-section-title h2 { margin: 0; color: ${accent}; font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.8px; }
        .m-section-aside { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 2px; }

        /* ── Cards shared ── */
        .m-card {
          background: var(--bg-card); border: 1px solid var(--border);
          border-radius: 18px; padding: 22px 24px;
          transition: border-color 0.2s;
        }
        .m-card:hover { border-color: ${accent}40; }
        .m-label { color: var(--text-muted); font-size: 11.5px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.7px; display: block; margin-bottom: 4px; }

        /* ── Metric Tiles ── */
        .m-metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
        .m-metric-tile {
          background: var(--bg-card); border: 1px solid var(--border);
          border-radius: 16px; padding: 16px; display: flex; gap: 13px; align-items: flex-start;
          transition: border-color 0.2s, transform 0.2s;
        }
        .m-metric-tile:hover { border-color: ${accent}40; transform: translateY(-2px); }
        .m-metric-icon { width: 38px; height: 38px; border-radius: 12px; display: grid; place-items: center; flex-shrink: 0; }
        .m-metric-value { display: block; font-size: 24px; font-weight: 800; line-height: 1.1; margin: 7px 0 4px; font-family: 'Inter', sans-serif; }
        .m-status {
          display: inline-flex; width: fit-content; border-radius: 999px;
          padding: 3px 9px; font-size: 11px; font-weight: 800;
          color: var(--text-muted); background: rgba(148,163,184,0.16); white-space: nowrap;
        }
        .m-status.excellent, .m-status.good { color: #16a34a; background: rgba(34,197,94,0.13); }
        .m-status.fair { color: #d97706; background: rgba(245,158,11,0.15); }
        .m-status.support { color: #dc2626; background: rgba(239,68,68,0.14); }

        /* ── Team section ── */
        .m-team-top { display: grid; grid-template-columns: 200px 1fr 1fr; gap: 12px; }
        .m-team-stat {
          background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px;
          padding: 18px; display: grid; align-content: center; gap: 6px;
        }
        .m-team-stat-number { font-size: 38px; font-weight: 800; font-family: 'Inter', sans-serif; }
        .m-highlight {
          background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px;
          padding: 18px; min-width: 0;
        }
        .m-highlight-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
        .m-highlight-icon { color: ${accent}; }
        .m-highlight-name { display: block; font-size: 16px; font-weight: 700; margin-bottom: 2px; }
        .m-highlight-username { display: block; color: var(--text-muted); font-size: 12.5px; margin-bottom: 8px; }
        .m-highlight-reason { color: var(--text-muted); font-size: 13px; line-height: 1.5; margin: 0; }
        .m-gauge-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
        .m-ring-card, .m-smells-card, .m-gauge-card {
          background: var(--bg-card); border: 1px solid var(--border);
          border-radius: 16px; padding: 18px; min-height: 230px;
        }
        .m-ring-desc { margin: 4px 0 14px; color: var(--text-muted); font-size: 12.5px; line-height: 1.45; }
        .m-ring-body { display: flex; align-items: center; gap: 18px; }
        .m-ring-legend { display: flex; flex-direction: column; gap: 8px; flex: 1; }
        .m-ring-zone { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-muted); }
        .m-ring-zone em { margin-left: auto; font-style: normal; font-size: 11px; color: var(--text-muted); opacity: 0.7; }
        .m-ring-zone span { width: 10px; height: 10px; border-radius: 3px; flex-shrink: 0; }
        .m-ring-zone-red span { background: #ef4444; }
        .m-ring-zone-amber span { background: #f59e0b; }
        .m-ring-zone-green span { background: #22c55e; }
        .m-score-status { display: block; width: fit-content; margin-top: 14px; border-radius: 999px; padding: 5px 12px; font-size: 12px; font-weight: 800; color: var(--text-muted); background: rgba(148,163,184,0.16); }
        .m-score-status.excellent, .m-score-status.good { color: #16a34a; background: rgba(34,197,94,0.13); }
        .m-score-status.fair { color: #d97706; background: rgba(245,158,11,0.15); }
        .m-score-status.support { color: #dc2626; background: rgba(239,68,68,0.14); }

        /* ── Contributors Table ── */
        .m-table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 18px; background: var(--bg-card); }
        .m-table { width: 100%; border-collapse: collapse; min-width: 980px; }
        .m-table th { text-align: left; color: var(--text-muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; padding: 14px 14px; border-bottom: 1px solid var(--border); font-weight: 800; }
        .m-table td { padding: 13px 14px; border-bottom: 1px solid var(--border); color: var(--text-muted); font-size: 13px; }
        .m-table tr:last-child td { border-bottom: 0; }
        .m-table td strong { display: block; color: var(--text-primary); font-weight: 700; }
        .m-table td small { color: var(--text-muted); font-size: 12px; }
        .m-table tbody tr { transition: background 0.12s; }
        .m-table tbody tr:hover { background: ${accent}08; }

        /* ── Trends ── */
        .m-trend-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 18px; padding: 20px; }
        .m-trend-select {
          border: 1px solid var(--border); background: var(--bg-card);
          color: var(--text-primary); border-radius: 10px; height: 38px; padding: 0 12px;
          font-weight: 700; font-family: 'Inter', system-ui, sans-serif; cursor: pointer;
        }

        /* ── Risks ── */
        .m-risk-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
        .m-risk-list {
          background: var(--bg-card); border: 1px solid var(--border);
          border-radius: 18px; padding: 18px; min-width: 0;
        }
        .m-risk-list-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
        .m-risk-icon { width: 32px; height: 32px; border-radius: 10px; display: grid; place-items: center; background: rgba(239,68,68,0.12); color: #ef4444; flex-shrink: 0; }
        .m-risk-title { font-size: 15px; font-weight: 700; color: var(--text-primary); }
        .m-risk-count { background: rgba(239,68,68,0.12); color: #ef4444; border-radius: 999px; padding: 3px 10px; font-size: 12px; font-weight: 800; }
        .m-risk-row { display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: center; border-top: 1px solid var(--border); padding: 11px 0; }
        .m-risk-row strong { display: block; color: var(--text-primary); font-size: 13.5px; overflow-wrap: anywhere; margin-bottom: 3px; }
        .m-risk-row p { margin: 0; color: var(--text-muted); font-size: 12.5px; line-height: 1.4; }
        .m-risk-badge { border-radius: 999px; background: rgba(148,163,184,0.15); padding: 5px 10px; font-size: 11.5px; font-weight: 800; color: var(--text-muted); white-space: nowrap; }
        .m-risk-badge.excellent, .m-risk-badge.good { color: #16a34a; background: rgba(34,197,94,0.13); }
        .m-risk-badge.fair { color: #d97706; background: rgba(245,158,11,0.15); }
        .m-risk-badge.support { color: #dc2626; background: rgba(239,68,68,0.14); }

        /* ── Recommendations ── */
        .m-rec-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
        .m-rec {
          background: var(--bg-card); border: 1px solid var(--border);
          border-radius: 18px; padding: 18px;
        }
        .m-rec-head { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
        .m-rec-icon { width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center; flex-shrink: 0; }
        .m-rec h3 { margin: 0; font-size: 15px; font-weight: 700; color: var(--text-primary); }
        .m-rec p { border-top: 1px solid var(--border); padding-top: 10px; margin: 10px 0 0; color: var(--text-muted); font-size: 13px; line-height: 1.5; }
        .m-rec-fix { border-color: rgba(239,68,68,0.3); }
        .m-rec-fix .m-rec-icon { background: rgba(239,68,68,0.12); color: #ef4444; }
        .m-rec-next { border-color: rgba(249,115,22,0.3); }
        .m-rec-next .m-rec-icon { background: rgba(249,115,22,0.12); color: #f97316; }
        .m-rec-plan { border-color: rgba(59,130,246,0.3); }
        .m-rec-plan .m-rec-icon { background: rgba(59,130,246,0.12); color: #3b82f6; }
        .m-rec-strong { border-color: rgba(34,197,94,0.3); }
        .m-rec-strong .m-rec-icon { background: rgba(34,197,94,0.12); color: #22c55e; }
        .m-reason-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 12px; }
        .m-reason-card {
          background: var(--bg-card); border: 1px solid var(--border);
          border-radius: 16px; padding: 16px;
        }
        .m-reason-head { display: flex; align-items: center; gap: 8px; color: ${accent}; margin-bottom: 10px; }
        .m-reason-head strong { font-size: 13px; font-weight: 700; color: var(--text-primary); }
        .m-reason-card p { margin: 7px 0 0; color: var(--text-muted); font-size: 12.5px; line-height: 1.45; }

        /* ── States ── */
        .m-empty { color: var(--text-muted); font-size: 13px; margin: 0; }
        .m-loading { border: 1px solid var(--border); border-radius: 18px; min-height: 240px; padding: 24px; background: var(--bg-card); animation: mShimmer 1.4s ease-in-out infinite; background-size: 400% 100%; }
        .m-error { border: 1px solid rgba(239,68,68,0.3); border-radius: 18px; min-height: 120px; padding: 24px; color: #ef4444; background: rgba(239,68,68,0.06); display: grid; place-items: center; font-weight: 700; }
        @keyframes mShimmer { 0%{background-position:100% 50%} 100%{background-position:0% 50%} }
        .sk { background: linear-gradient(90deg, var(--bg-card) 25%, var(--bg-card-hover, rgba(255,255,255,0.04)) 50%, var(--bg-card) 75%); background-size: 400% 100%; animation: mShimmer 1.4s ease-in-out infinite; border-radius: 10px; }

        /* ── Responsive ── */
        @media (max-width: 1100px) {
          .m-metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          .m-team-top, .m-gauge-grid, .m-reason-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          .m-rec-grid { grid-template-columns: 1fr; }
        }
        @media (max-width: 760px) {
          .m-page { padding: 22px 16px 60px; }
          .m-header { flex-direction: column; }
          .m-score-band { grid-template-columns: 1fr; }
          .m-score-col { border-right: 0; border-bottom: 1px solid var(--border); padding-right: 0; padding-bottom: 14px; }
          .m-summary-grid, .m-metric-grid, .m-team-top, .m-gauge-grid, .m-risk-grid, .m-rec-grid, .m-reason-grid { grid-template-columns: 1fr; }
          .m-risk-row { grid-template-columns: 1fr; }
          .m-repo-trigger { min-width: 0; width: 100%; }
        }
      `}</style>

      <main className="m-page">
        <div className="m-shell">

          {/* ── Header ── */}
          <header className="m-header">
            <div>
              <div className="m-eyebrow"><BarChart3 size={13} /> Manager Dashboard</div>
              <h1>Monitor your repository<br />and team performance</h1>
              <p className="m-header-sub">Get a full picture of code health, team velocity, and actionable insights.</p>
            </div>
            <div className="m-actions">
              <RepoDropdown
                repos={data.repositories}
                selectedRepoId={selectedRepoId}
                loading={loading}
                onChange={setSelectedRepoId}
                dropdownRef={dropdownRef}
              />
              <button type="button" className="m-refresh-btn" onClick={fetchOverview} title="Refresh dashboard">
                <RefreshCcw size={17} />
              </button>
            </div>
          </header>

          {/* ── Score band (always visible) ── */}
          {!loading && !error && (
            <div className="m-score-band">
              <div className="m-score-col">
                <span className="m-score-label">Overall Repository Score</span>
                <strong className="m-score-number" style={{ color: scoreColor(score) }}>
                  {fmtNumber(score)}
                </strong>
                <span className={`m-status ${statusClass(data.repository_summary.repository_status)}`}>
                  {data.repository_summary.repository_status}
                </span>
              </div>
              <div className="m-summary-grid">
                <SummaryItem label="Repository" value={data.repository_summary.repository_name || "—"} icon={<Building2 size={15} />} />
                <SummaryItem label="Organization" value={data.repository_summary.organization || "—"} icon={<Users size={15} />} />
                <SummaryItem label="Branch" value={<><GitBranch size={13} style={{ flexShrink: 0 }} /> {data.repository_summary.branch || "—"}</>} icon={<GitBranch size={15} />} />
                <SummaryItem label="Last Analysis" value={fmtDate(data.repository_summary.last_analysis)} icon={<CalendarClock size={15} />} />
                <SummaryItem label="Analyzed On" value={fmtDate(data.repository_summary.analyzed_on)} icon={<CalendarClock size={15} />} />
                <SummaryItem label="Analysis ID" value={data.repository_summary.analysis_run_id ? `#${data.repository_summary.analysis_run_id}` : "—"} icon={<GitCommitHorizontal size={15} />} />
              </div>
            </div>
          )}

          {/* ── Tabs ── */}
          <div className="m-tabs-wrap">
            <div className="m-tabs" role="tablist">
              {TABS.map(tab => (
                <button
                  key={tab.key}
                  type="button"
                  role="tab"
                  aria-selected={activeTab === tab.key}
                  className={`m-tab ${activeTab === tab.key ? "active" : ""}`}
                  onClick={() => setActiveTab(tab.key)}
                >
                  {tab.icon}{tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* ── Content ── */}
          {loading ? (
            <div className="m-loading sk" style={{ minHeight: 320 }} />
          ) : error ? (
            <div className="m-error">{error}</div>
          ) : (
            <>
              {/* ── Repository Health ── */}
              {activeTab === "overview" && (
                <div className="m-section">
                  <div className="m-section-title">
                    <Gauge size={14} style={{ color: accent }} />
                    <h2>Repository Metrics</h2>
                  </div>
                  <div className="m-metric-grid">
                    {metricsWithoutGate.map(metric => <MetricTile key={metric.key} metric={metric} />)}
                  </div>
                </div>
              )}

              {/* ── Team Performance ── */}
              {activeTab === "team" && (
                <div className="m-section">
                  <div className="m-section-title">
                    <Users size={14} style={{ color: accent }} />
                    <h2>Team Performance Overview</h2>
                  </div>
                  <div className="m-team-top">
                    <div className="m-team-stat">
                      <span className="m-label">Average Team Score</span>
                      <strong className="m-team-stat-number" style={{ color: scoreColor(data.team_performance.average_team_score) }}>
                        {fmtNumber(data.team_performance.average_team_score)}
                      </strong>
                      <span style={{ color: "var(--text-muted)", fontSize: 13 }}>
                        {data.team_performance.total_contributors} active contributors
                      </span>
                    </div>
                    <HighlightCard title="Best Contributor" person={data.team_performance.best_contributor} icon={<TrendingUp size={17} />} />
                    <HighlightCard title="Needs Support" person={data.team_performance.needs_support_contributor} icon={<Target size={17} />} />
                  </div>
                  <div className="m-gauge-grid">
                    <ScoreRingMetric label="Team Average Skill Score" value={data.team_performance.average_team_score} description="Combined team capability score across contributors." />
                    <ScoreRingMetric label="Team Average Security Score" value={data.team_performance.average_team_security_score} description="Security posture average from the latest contributor analyses." />
                    <CodeSmellsMetric value={data.team_performance.average_code_smells} />
                  </div>
                </div>
              )}

              {/* ── Contributors ── */}
              {activeTab === "contributors" && (
                <div className="m-section">
                  <div className="m-section-title">
                    <BarChart3 size={14} style={{ color: accent }} />
                    <h2>Contributors Overview</h2>
                  </div>
                  <div className="m-table-wrap">
                    <table className="m-table">
                      <thead>
                        <tr>
                          {["Developer", "Role", "Skill Score", "Health Score", "Security Score", "Coverage", "Bugs", "Code Smells", "Complexity", "Status"].map(h => (
                            <th key={h}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {data.contributors.map(row => (
                          <tr key={row.id}>
                            <td><strong>{row.developer}</strong><small>@{row.username}</small></td>
                            <td>{row.role || "Developer"}</td>
                            <td style={{ color: scoreColor(row.skill_score), fontWeight: 700 }}>{fmtNumber(row.skill_score)}</td>
                            <td>{fmtNumber(row.health_score)}</td>
                            <td>{fmtNumber(row.security_score)}</td>
                            <td>{fmtPlainMetric(row.coverage, "%", 1)}</td>
                            <td>{fmtPlainMetric(row.bugs)}</td>
                            <td>{fmtPlainMetric(row.code_smells)}</td>
                            <td>{fmtPlainMetric(row.complexity)}</td>
                            <td><span className={`m-status ${statusClass(row.status)}`}>{row.status}</span></td>
                          </tr>
                        ))}
                        {!data.contributors.length && (
                          <tr><td colSpan={10} style={{ color: "var(--text-muted)", textAlign: "center", padding: 28 }}>No completed contributor analysis is available yet.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* ── Trends ── */}
              {activeTab === "trends" && (
                <div className="m-section">
                  <div className="m-section-aside">
                    <div className="m-section-title" style={{ marginBottom: 0 }}>
                      <LineChartIcon size={14} style={{ color: accent }} />
                      <h2>Repository Trends</h2>
                    </div>
                    <select
                      className="m-trend-select"
                      value={trendGranularity}
                      onChange={e => setTrendGranularity(e.target.value as "daily" | "monthly")}
                    >
                      <option value="daily">Daily</option>
                      <option value="monthly">Monthly</option>
                    </select>
                  </div>
                  <div className="m-trend-card">
                    {trendData.length ? (
                      <ResponsiveContainer width="100%" height={280}>
                        <LineChart data={trendData}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(148,163,184,0.15)" />
                          <XAxis dataKey="label" tickLine={false} axisLine={false} style={{ fontSize: 12 }} />
                          <YAxis domain={[0, 100]} tickLine={false} axisLine={false} style={{ fontSize: 12 }} />
                          <Tooltip contentStyle={{ background: "#1a1a2e", border: "1px solid rgba(139,92,246,0.3)", borderRadius: 12 }} />
                          <Line type="monotone" dataKey="health_score" name="Health Score" stroke="#3b82f6" strokeWidth={2.4} dot={{ r: 3 }} />
                          <Line type="monotone" dataKey="security_score" name="Security Score" stroke="#22c55e" strokeWidth={2.4} dot={{ r: 3 }} />
                        </LineChart>
                      </ResponsiveContainer>
                    ) : <p className="m-empty" style={{ padding: 32, textAlign: "center" }}>No historical trend data available yet.</p>}
                  </div>
                </div>
              )}

              {/* ── Risks & Insights ── */}
              {activeTab === "risks" && (
                <div className="m-section">
                  <div className="m-section-title">
                    <AlertTriangle size={14} style={{ color: accent }} />
                    <h2>Risks & Attention</h2>
                  </div>
                  <div className="m-risk-grid">
                    <RiskPanel title="Files with Code Smells" items={data.risks.high_code_smells} metricLabel="Code Smells" icon={<Flame size={16} />} />
                    <RiskPanel title="Files for Bugs" items={(data.risks.files_for_bugs?.length ? data.risks.files_for_bugs : data.risks.high_bug_files)} metricLabel="Bugs" icon={<Bug size={16} />} />
                  </div>
                </div>
              )}

              {/* ── Recommendations ── */}
              {activeTab === "recommendations" && (
                <div className="m-section">
                  <div className="m-section-title">
                    <Sparkles size={14} style={{ color: accent }} />
                    <h2>Actionable Recommendations</h2>
                  </div>
                  <div className="m-rec-grid">
                    <RecommendationGroup title="Fix First" items={data.recommendations.fix_first} tone="fix" icon={<AlertCircle size={18} />} />
                    <RecommendationGroup title="Prioritize Next" items={data.recommendations.prioritize_next} tone="next" icon={<TrendingUp size={18} />} />
                    <RecommendationGroup title="Plan When Possible" items={data.recommendations.plan_when_possible} tone="plan" icon={<CheckCircle2 size={18} />} />
                    <RecommendationGroup title="Strengthen Further" items={data.recommendations.strengthen_further} tone="strong" icon={<Award size={18} />} />
                  </div>
                  <div className="m-reason-grid">
                    <div className="m-reason-card">
                      <div className="m-reason-head"><Brain size={16} /><strong>Architectural Concerns</strong></div>
                      {data.recommendations.architectural_concerns.map(item => <p key={item}>{item}</p>)}
                      {!data.recommendations.architectural_concerns.length && <p className="m-empty">None identified.</p>}
                    </div>
                    <div className="m-reason-card">
                      <div className="m-reason-head"><Activity size={16} /><strong>Delivery Risks</strong></div>
                      {data.recommendations.delivery_risks.map(item => <p key={item}>{item}</p>)}
                      {!data.recommendations.delivery_risks.length && <p className="m-empty">None identified.</p>}
                    </div>
                    <div className="m-reason-card">
                      <div className="m-reason-head"><Layers size={16} /><strong>Quality Concerns</strong></div>
                      {data.recommendations.quality_concerns.map(item => <p key={item}>{item}</p>)}
                      {!data.recommendations.quality_concerns.length && <p className="m-empty">None identified.</p>}
                    </div>
                    <div className="m-reason-card">
                      <div className="m-reason-head"><ShieldCheck size={16} /><strong>Team Strengths</strong></div>
                      {data.recommendations.team_strengths.map(item => <p key={item}>{item}</p>)}
                      {!data.recommendations.team_strengths.length && <p className="m-empty">None identified.</p>}
                    </div>
                    <div className="m-reason-card">
                      <div className="m-reason-head"><CheckCircle2 size={16} /><strong>Recommended Priorities</strong></div>
                      {data.recommendations.recommended_priorities.map(item => <p key={item}>{item}</p>)}
                      {!data.recommendations.recommended_priorities.length && <p className="m-empty">None identified.</p>}
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </DashboardLayout>
  );
}
