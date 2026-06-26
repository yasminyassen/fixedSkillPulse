import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  ArrowUp,
  BarChart3,
  CalendarDays,
  Download,
  Eye,
  Filter,
  Gauge,
  GitBranch,
  Search,
  ShieldCheck,
  Star,
  Target,
  Users,
  X,
} from "lucide-react";
import api from "../../api/auth";
import DashboardLayout from "../DashboardLayout";

type RecruiterTask = {
  id: number;
  title: string;
  csv_filename: string | null;
  total_candidates: number;
  valid_count: number;
  skipped_count: number;
  status: "pending" | "analyzing" | "completed" | "failed" | string;
  created_at: string;
  updated_at?: string | null;
  analyzed_count: number;
  average_skill_score: number | null;
};

type CandidateRow = {
  candidate_name: string;
  github_login: string | null;
  github_avatar_url?: string | null;
  repo_name?: string | null;
  repo_url?: string | null;
  task_id?: number | null;
  task_title?: string | null;
  skill_score: number | null;
  skill_score_level: string;
  sonar_health_score: number | null;
  sonar_state: string;
  quality_gate: string | null;
  bugs: number | null;
  code_smells: number | null;
  coverage: number | null;
  duplication_percentage: number | null;
  cognitive_complexity: number | null;
  reliability_rating: string | null;
  maintainability_rating: string | null;
  technical_debt_minutes: number | null;
  lines_of_code: number | null;
  security: number | null;
  repo_count: number;
  contribution_count: number;
  run_id: number;
  analysis_status?: string | null;
  completed_at?: string | null;
};

type CandidateInsight = {
  candidate_name: string;
  github_login?: string | null;
  github_avatar_url?: string | null;
  run_id: number;
  repo_name?: string | null;
  task_title?: string | null;
  skill_score: number | null;
  sonar_health_score?: number | null;
  security?: number | null;
  coverage?: number | null;
  bugs?: number | null;
  summary: string;
  strengths: string[];
  areas_to_improve: string[];
  recommendation: "strong_hire" | "interview" | "review_required" | "reject";
  recommendation_reason: string;
  risk_level: "low" | "medium" | "high" | "critical";
  generated_by: "llm" | "fallback" | "summary";
  generated_at?: string | null;
};

type RiskLevel = "low" | "medium" | "high" | "critical";

type DashboardSummary = {
  overview: {
    total_candidates: number;
    average_skill_score: number | null;
    average_sonar_health: number | null;
    average_security_score: number | null;
    passed_quality_gate_percentage: number | null;
    high_priority_candidates: number;
  };
  task_distribution: {
    excellent: number;
    good: number;
    fair: number;
    poor: number;
  };
  risk_heatmap: Array<{
    candidate_name: string;
    code_quality: RiskLevel;
    security: RiskLevel;
    maintainability: RiskLevel;
    testing: RiskLevel;
    reliability: RiskLevel;
  }>;
  top_candidate?: CandidateInsight | null;
};

type CandidateFilters = {
  task_id: string;
  search: string;
  min_skill_score: string;
  max_skill_score: string;
  min_sonar: string;
  max_sonar: string;
  min_security: string;
  max_security: string;
  min_coverage: string;
  max_coverage: string;
  quality_gate: string;
  max_bugs: string;
  max_technical_debt_minutes: string;
  sort_by: string;
  sort_dir: "asc" | "desc";
};

type ToastState = { message: string; type: "success" | "error" } | null;

const emptyFilters: CandidateFilters = {
  task_id: "all",
  search: "",
  min_skill_score: "",
  max_skill_score: "",
  min_sonar: "",
  max_sonar: "",
  min_security: "",
  max_security: "",
  min_coverage: "",
  max_coverage: "",
  quality_gate: "all",
  max_bugs: "",
  max_technical_debt_minutes: "",
  sort_by: "skill_score",
  sort_dir: "desc",
};

const emptySummary: DashboardSummary = {
  overview: {
    total_candidates: 0,
    average_skill_score: null,
    average_sonar_health: null,
    average_security_score: null,
    passed_quality_gate_percentage: null,
    high_priority_candidates: 0,
  },
  task_distribution: { excellent: 0, good: 0, fair: 0, poor: 0 },
  risk_heatmap: [],
  top_candidate: null,
};

const sortOptions = [
  ["skill_score", "Skill Score"],
  ["sonar_health_score", "Sonar Health"],
  ["security", "Security"],
  ["coverage", "Coverage"],
  ["bugs", "Bugs"],
  ["code_smells", "Code Smells"],
  ["technical_debt_minutes", "Technical Debt"],
  ["completed_at", "Completed At"],
];

const fmt = (value: number | string | null | undefined, suffix = "") => {
  if (value === null || value === undefined || value === "") return "Unavailable";
  if (typeof value === "number") return `${Number.isInteger(value) ? value : value.toFixed(1)}${suffix}`;
  return `${value}${suffix}`;
};

const scoreTone = (score: number | null | undefined) => {
  if (score === null || score === undefined) return "muted";
  if (score >= 80) return "green";
  if (score >= 60) return "yellow";
  if (score >= 40) return "orange";
  return "red";
};

const riskLabel = (level: RiskLevel) => level.charAt(0).toUpperCase() + level.slice(1);

const recommendationLabel: Record<CandidateInsight["recommendation"], string> = {
  strong_hire: "Strong Hire",
  interview: "Interview",
  review_required: "Review Required",
  reject: "Reject",
};

const generatedLabel: Record<CandidateInsight["generated_by"], string> = {
  llm: "AI generated",
  fallback: "Fallback insight",
  summary: "Summary insight",
};

const initials = (name?: string | null) =>
  String(name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0])
    .join("")
    .toUpperCase()
    .slice(0, 2) || "?";

function CandidateAvatar({ src, name, large = false }: { src?: string | null; name?: string | null; large?: boolean }) {
  return (
    <span className={`rd-avatar${large ? " large" : ""}`}>
      {src && (
        <img
          src={src}
          alt={`${name || "Candidate"} GitHub avatar`}
          onError={(event) => {
            event.currentTarget.style.display = "none";
            const fallback = event.currentTarget.nextElementSibling as HTMLElement | null;
            if (fallback) fallback.style.opacity = "1";
          }}
        />
      )}
      <span>{initials(name)}</span>
    </span>
  );
}

const buildParams = (filters: CandidateFilters, searchValue: string) => {
  const params: Record<string, string> = {
    sort_by: filters.sort_by,
    sort_dir: filters.sort_dir,
  };
  const entries: Array<[keyof CandidateFilters, string]> = [
    ["min_skill_score", filters.min_skill_score],
    ["max_skill_score", filters.max_skill_score],
    ["min_sonar", filters.min_sonar],
    ["max_sonar", filters.max_sonar],
    ["min_security", filters.min_security],
    ["max_security", filters.max_security],
    ["min_coverage", filters.min_coverage],
    ["max_coverage", filters.max_coverage],
    ["max_bugs", filters.max_bugs],
    ["max_technical_debt_minutes", filters.max_technical_debt_minutes],
  ];

  if (filters.task_id !== "all") params.task_id = filters.task_id;
  if (searchValue.trim()) params.search = searchValue.trim();
  if (filters.quality_gate !== "all") params.quality_gate = filters.quality_gate;
  entries.forEach(([key, value]) => {
    if (value.trim()) params[key] = value.trim();
  });
  return params;
};

async function loadTasks() {
  const res = await api.get<RecruiterTask[]>("/analysis/recruiter/tasks");
  return res.data || [];
}

async function loadCandidates(filters: CandidateFilters, searchValue: string) {
  const res = await api.get<CandidateRow[]>("/analysis/recruiter/candidates", {
    params: buildParams(filters, searchValue),
  });
  return res.data || [];
}

async function loadDashboardSummary(taskId: string) {
  const res = await api.get<DashboardSummary>("/analysis/recruiter/dashboard-summary", {
    params: taskId !== "all" ? { task_id: taskId } : undefined,
  });
  return res.data || emptySummary;
}

async function loadCandidateInsights(runId: number, forceRefresh = false) {
  const res = await api.get<CandidateInsight>(`/analysis/recruiter/candidate-insights/${runId}`, {
    params: forceRefresh ? { force_refresh: true } : undefined,
  });
  return res.data;
}

export default function CandidateEvaluation() {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<RecruiterTask[]>([]);
  const [filters, setFilters] = useState<CandidateFilters>(emptyFilters);
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [candidates, setCandidates] = useState<CandidateRow[]>([]);
  const [summary, setSummary] = useState<DashboardSummary>(emptySummary);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [insightsByRun, setInsightsByRun] = useState<Record<number, CandidateInsight>>({});
  const [loadingTasks, setLoadingTasks] = useState(true);
  const [loadingCandidates, setLoadingCandidates] = useState(true);
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [candidateError, setCandidateError] = useState("");
  const [summaryError, setSummaryError] = useState("");
  const [toast, setToast] = useState<ToastState>(null);

  const [activeTab, setActiveTab] = useState<"ranking" | "analytics">("ranking");


  const showToast = useCallback((message: string, type: "success" | "error" = "success") => {
    setToast({ message, type });
    window.setTimeout(() => setToast(null), 2600);
  }, []);

  const fetchTasks = useCallback(async () => {
    setLoadingTasks(true);
    try {
      setTasks(await loadTasks());
    } catch {
      showToast("Unable to load uploaded tasks.", "error");
    } finally {
      setLoadingTasks(false);
    }
  }, [showToast]);

  const fetchCandidates = useCallback(async () => {
    setLoadingCandidates(true);
    setCandidateError("");
    try {
      const data = await loadCandidates(filters, debouncedSearch);
      setCandidates(data);
      setSelectedRunId((current) => {
        if (!data.length) return null;
        if (current && data.some((candidate) => candidate.run_id === current)) return current;
        return data[0].run_id;
      });
    } catch (error: any) {
      setCandidateError(error?.response?.data?.detail || "Unable to load candidates.");
    } finally {
      setLoadingCandidates(false);
    }
  }, [debouncedSearch, filters]);

  const fetchSummary = useCallback(async () => {
    setLoadingSummary(true);
    setSummaryError("");
    try {
      setSummary(await loadDashboardSummary(filters.task_id));
    } catch (error: any) {
      setSummaryError(error?.response?.data?.detail || "Unable to load dashboard summary.");
      setSummary(emptySummary);
    } finally {
      setLoadingSummary(false);
    }
  }, [filters.task_id]);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedSearch(filters.search), 300);
    return () => window.clearTimeout(handle);
  }, [filters.search]);

  useEffect(() => {
    fetchCandidates();
  }, [fetchCandidates]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);


  const setFilter = <K extends keyof CandidateFilters>(key: K, value: CandidateFilters[K]) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const clearFilters = () => {
    setFilters(emptyFilters);
    setDebouncedSearch("");
  };

  const exportCsv = () => {
    const headers = [
      "candidate_name",
      "github_login",
      "repo_name",
      "skill_score",
      "sonar_health_score",
      "security",
      "coverage",
      "bugs",
      "quality_gate",
    ];
    const escape = (value: unknown) => `"${String(value ?? "").replace(/"/g, '""')}"`;
    const lines = [
      headers.join(","),
      ...candidates.map((candidate) =>
        headers.map((key) => escape(candidate[key as keyof CandidateRow])).join(","),
      ),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "candidate-dashboard.csv";
    link.click();
    URL.revokeObjectURL(url);
  };


  const overview = summary.overview;
  const totalDistribution =
    summary.task_distribution.excellent +
    summary.task_distribution.good +
    summary.task_distribution.fair +
    summary.task_distribution.poor;
  const donut = distributionGradient(summary.task_distribution);

  return (
    <DashboardLayout>
      <style>{dashboardCss}</style>
      <div className="rd-page">
        <header className="rd-header">
          <div>
            <h1>Recruiter Dashboard</h1>
            <p>Overview of candidates performance and analysis</p>
          </div>
          <div className="rd-actions">
            <button className="rd-ghost-btn" type="button">
              <CalendarDays size={16} />
              May 1 - May 31, 2025
            </button>
            <button className="rd-ghost-btn" type="button" onClick={exportCsv} disabled={!candidates.length}>
              <Download size={16} />
              Export
            </button>

          </div>
        </header>

        <section className="rd-kpis">
          <KpiCard icon={<Users size={20} />} label="Total Candidates" value={overview.total_candidates} loading={loadingSummary} />
          <KpiCard icon={<Star size={20} />} label="Average Skill Score" value={fmt(overview.average_skill_score)} tone={scoreTone(overview.average_skill_score)} loading={loadingSummary} />
          <KpiCard icon={<Gauge size={20} />} label="Average Sonar Health" value={fmt(overview.average_sonar_health)} tone={scoreTone(overview.average_sonar_health)} loading={loadingSummary} />
          <KpiCard icon={<ShieldCheck size={20} />} label="Average Security Score" value={fmt(overview.average_security_score)} tone={scoreTone(overview.average_security_score)} loading={loadingSummary} />

          <KpiCard icon={<Target size={20} />} label="High Priority Candidates" value={overview.high_priority_candidates} tone="purple" loading={loadingSummary} />
        </section>

        <section className="rd-panel rd-filters">
          <div className="rd-panel-title">
            <div>
              <span className="rd-eyebrow"><Filter size={14} /> Smart Filters</span>
              <h2>Refine candidate ranking</h2>
            </div>
            <button className="rd-clear-btn" type="button" onClick={clearFilters}>
              <X size={14} />
              Clear All
            </button>
          </div>

          <div className="rd-filter-grid">
            <label className="rd-field rd-search-field">
              <span>Search candidate</span>
              <div className="rd-input-icon">
                <Search size={16} />
                <input value={filters.search} onChange={(e) => setFilter("search", e.target.value)} placeholder="Search candidate..." />
              </div>
            </label>
            <label className="rd-field">
              <span>Uploaded Task</span>
              <select value={filters.task_id} onChange={(e) => setFilter("task_id", e.target.value)} disabled={loadingTasks}>
                <option value="all">All Uploaded Tasks</option>
                {tasks.map((task) => (
                  <option key={task.id} value={String(task.id)}>
                    {task.title} · {task.valid_count} candidates
                  </option>
                ))}
              </select>
            </label>
            <RangeFields label="Skill Score" min={filters.min_skill_score} max={filters.max_skill_score} onMin={(v) => setFilter("min_skill_score", v)} onMax={(v) => setFilter("max_skill_score", v)} />
            <RangeFields label="Sonar Health" min={filters.min_sonar} max={filters.max_sonar} onMin={(v) => setFilter("min_sonar", v)} onMax={(v) => setFilter("max_sonar", v)} />
            <RangeFields label="Security Score" min={filters.min_security} max={filters.max_security} onMin={(v) => setFilter("min_security", v)} onMax={(v) => setFilter("max_security", v)} />
            <RangeFields label="Coverage" min={filters.min_coverage} max={filters.max_coverage} onMin={(v) => setFilter("min_coverage", v)} onMax={(v) => setFilter("max_coverage", v)} />
            <label className="rd-field">
              <span>Max Bugs</span>
              <input type="number" min="0" value={filters.max_bugs} onChange={(e) => setFilter("max_bugs", e.target.value)} placeholder="Any" />
            </label>
            <label className="rd-field">
              <span>Max Technical Debt</span>
              <input type="number" min="0" value={filters.max_technical_debt_minutes} onChange={(e) => setFilter("max_technical_debt_minutes", e.target.value)} placeholder="Minutes" />
            </label>
            <label className="rd-field">
              <span>Sort By</span>
              <select value={filters.sort_by} onChange={(e) => setFilter("sort_by", e.target.value)}>
                {sortOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label className="rd-field">
              <span>Sort Direction</span>
              <select value={filters.sort_dir} onChange={(e) => setFilter("sort_dir", e.target.value as "asc" | "desc")}>
                <option value="desc">Descending</option>
                <option value="asc">Ascending</option>
              </select>
            </label>
          </div>
        </section>

        <div className="rd-tabs-nav">
          <button
            className={`rd-tab-btn${activeTab === "ranking" ? " active" : ""}`}
            type="button"
            onClick={() => setActiveTab("ranking")}
          >
            <BarChart3 size={15} /> Candidate Ranking
          </button>
          <button
            className={`rd-tab-btn${activeTab === "analytics" ? " active" : ""}`}
            type="button"
            onClick={() => setActiveTab("analytics")}
          >
            <Target size={15} /> Risk & Analytics
          </button>
        </div>

        {activeTab === "ranking" && (
          <div className="rd-main-grid">
            <section className="rd-panel rd-table-panel">
              <div className="rd-panel-title">
                <div>
                  <span className="rd-eyebrow"><BarChart3 size={14} /> Candidate Ranking</span>
                  <h2>{candidates.length} analyzed candidates</h2>
                </div>
                {candidateError && <button className="rd-clear-btn" type="button" onClick={fetchCandidates}>Retry</button>}
              </div>

              {loadingCandidates ? (
                <TableSkeleton />
              ) : candidateError ? (
                <div className="rd-empty rd-error">
                  <AlertTriangle size={26} />
                  <p>{candidateError}</p>
                  <button className="rd-primary-btn" type="button" onClick={fetchCandidates}>Retry</button>
                </div>
              ) : !candidates.length ? (
                <div className="rd-empty">No candidates match the selected filters.</div>
              ) : (
                <div className="rd-table-wrap">
                  <table className="rd-table">
                    <thead>
                      <tr>
                        {["Rank", "Candidate", "Repo", "Skill Score", "Sonar Health", "Security Score", "Coverage", "Bugs", "Actions"].map((header) => (
                          <th key={header}>{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {candidates.map((candidate, index) => (
                        <tr
                          key={candidate.run_id}
                          className={candidate.run_id === selectedRunId ? "selected" : ""}
                          onClick={() => setSelectedRunId(candidate.run_id)}
                        >
                          <td><span className="rd-rank">{index + 1}</span></td>
                          <td>
                            <div className="rd-candidate-cell">
                              <CandidateAvatar src={candidate.github_avatar_url} name={candidate.candidate_name} />
                              <div>
                                <strong>{candidate.candidate_name}</strong>
                                <span>{candidate.github_login || "GitHub unavailable"}</span>
                              </div>
                            </div>
                          </td>
                          <td>
                            <div className="rd-repo-cell">
                              <strong>{candidate.repo_name || "Repository"}</strong>
                              {candidate.repo_url && (
                                <a href={candidate.repo_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                                  <GitBranch size={12} /> Open repo
                                </a>
                              )}
                            </div>
                          </td>
                          <ScoreCell value={candidate.skill_score} />
                          <ScoreCell value={candidate.sonar_health_score} />
                          <ScoreCell value={candidate.security} />
                          <ScoreCell value={candidate.coverage} suffix="%" />
                          <td>{fmt(candidate.bugs)}</td>
                          <td>
                            <button
                              className="rd-icon-btn"
                              type="button"
                              title="View full analysis"
                              onClick={(e) => {
                                e.stopPropagation();
                                navigate(`/analysis/${candidate.run_id}`);
                              }}
                            >
                              <Eye size={16} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>
        )}

        {activeTab === "analytics" && (
          <section className="rd-bottom-grid">
            <RiskHeatmap rows={summary.risk_heatmap.slice(0, 8)} loading={loadingSummary} error={summaryError} />
            <section className="rd-panel">
              <div className="rd-panel-title">
                <div>
                  <span className="rd-eyebrow"><Target size={14} /> Task Analytics</span>
                  <h2>Distribution by score band</h2>
                </div>
              </div>
              <div className="rd-analytics">
                <div className="rd-donut" style={{ background: donut }}>
                  <div>
                    <strong>{totalDistribution}</strong>
                    <span>candidates</span>
                  </div>
                </div>
                <div className="rd-bars">
                  <DistributionBar label="Excellent" range="90-100" value={summary.task_distribution.excellent} total={totalDistribution} tone="green" />
                  <DistributionBar label="Good" range="70-89" value={summary.task_distribution.good} total={totalDistribution} tone="purple" />
                  <DistributionBar label="Fair" range="60-69" value={summary.task_distribution.fair} total={totalDistribution} tone="yellow" />
                  <DistributionBar label="Poor" range="0-59" value={summary.task_distribution.poor} total={totalDistribution} tone="red" />
                </div>
              </div>
            </section>
          </section>
        )}

        {toast && <div className={`rd-toast ${toast.type}`}>{toast.message}</div>}
      </div>
    </DashboardLayout>
  );
}

function KpiCard({
  icon,
  label,
  value,
  tone = "purple",
  loading,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  tone?: string;
  loading: boolean;
}) {
  return (
    <div className="rd-kpi">
      <div className={`rd-kpi-icon ${tone}`}>{icon}</div>
      <span>{label}</span>
      {loading ? <div className="rd-skeleton rd-skeleton-value" /> : <strong className={`rd-score-${tone}`}>{value}</strong>}
      <small><ArrowUp size={13} /> from selected task</small>
    </div>
  );
}

function RangeFields({
  label,
  min,
  max,
  onMin,
  onMax,
}: {
  label: string;
  min: string;
  max: string;
  onMin: (value: string) => void;
  onMax: (value: string) => void;
}) {
  return (
    <label className="rd-field">
      <span>{label} range</span>
      <div className="rd-range">
        <input type="number" min="0" max="100" value={min} onChange={(e) => onMin(e.target.value)} placeholder="Min" />
        <input type="number" min="0" max="100" value={max} onChange={(e) => onMax(e.target.value)} placeholder="Max" />
      </div>
    </label>
  );
}

function ScoreCell({ value, suffix = "" }: { value: number | null | undefined; suffix?: string }) {
  const tone = scoreTone(value);
  return <td><span className={`rd-score rd-score-${tone}`}>{fmt(value, suffix)}</span></td>;
}

function InsightsPanel({
  candidate,
  insight,
  loading,
  refreshing,
  error,
  isTopPerformer,
  onView,
  onRegenerate,
}: {
  candidate: CandidateRow | null;
  insight?: CandidateInsight;
  loading: boolean;
  refreshing: boolean;
  error: string;
  isTopPerformer: boolean;
  onView: () => void;
  onRegenerate: () => void;
}) {
  const score = insight?.skill_score ?? candidate?.skill_score ?? null;
  const scoreDegrees = Math.max(0, Math.min(100, score ?? 0)) * 3.6;

  return (
    <aside className="rd-panel rd-insights">
      <div className="rd-panel-title">
        <div>
          <span className="rd-eyebrow"><Brain size={14} /> AI Candidate Insights</span>
          <h2>Selected candidate</h2>
        </div>
      </div>

      {!candidate ? (
        <div className="rd-empty">Select a candidate to view AI-generated insights.</div>
      ) : loading && !insight ? (
        <InsightSkeleton />
      ) : (
        <>
          <div className="rd-insight-head">
            <CandidateAvatar src={candidate.github_avatar_url || insight?.github_avatar_url} name={candidate.candidate_name} large />
            <div>
              <h3>{candidate.candidate_name}</h3>
              <p>{candidate.github_login || "GitHub unavailable"}</p>
              {candidate.task_title && <span className="rd-task-chip">{candidate.task_title}</span>}
            </div>
          </div>

          <div className="rd-insight-badges">
            {isTopPerformer && <span className="rd-badge purple"><Star size={12} /> Top Performer</span>}
            {insight && <span className={`rd-badge rec-${insight.recommendation}`}>{recommendationLabel[insight.recommendation]}</span>}
            {insight && <span className={`rd-badge ${insight.risk_level}`}>{riskLabel(insight.risk_level)} risk</span>}
            {insight && <span className="rd-badge muted"><Sparkles size={12} /> {generatedLabel[insight.generated_by]}</span>}
          </div>

          <div className="rd-score-ring" style={{ background: `conic-gradient(#a855f7 ${scoreDegrees}deg, rgba(148,163,184,.14) 0deg)` }}>
            <div>
              <strong>{fmt(score)}</strong>
              <span>Skill Score</span>
            </div>
          </div>

          {error && <div className="rd-inline-error">{error}</div>}

          {insight ? (
            <div className="rd-insight-body">
              <p>{insight.summary}</p>
              <InsightList title="Strengths" items={insight.strengths} tone="green" />
              <InsightList title="Areas to improve" items={insight.areas_to_improve} tone="orange" />
              <div className="rd-reason">
                <span>Recommendation reason</span>
                <p>{insight.recommendation_reason}</p>
              </div>
            </div>
          ) : (
            <div className="rd-empty compact">Unable to generate candidate insight.</div>
          )}

          <div className="rd-insight-actions">
            <button className="rd-ghost-btn" type="button" onClick={onView}>
              <Eye size={16} /> View Full Analysis
            </button>
            <button className="rd-clear-btn" type="button" onClick={onRegenerate} disabled={refreshing || !candidate}>
              <RefreshCw size={16} className={refreshing ? "rd-spin" : ""} /> Refresh Insight
            </button>
          </div>
        </>
      )}
    </aside>
  );
}

function InsightList({ title, items, tone }: { title: string; items: string[]; tone: "green" | "orange" }) {
  return (
    <div className="rd-insight-list">
      <span>{title}</span>
      <ul>
        {(items || []).map((item) => (
          <li key={item}><span className={tone} />{item}</li>
        ))}
      </ul>
    </div>
  );
}

function RiskHeatmap({
  rows,
  loading,
  error,
}: {
  rows: DashboardSummary["risk_heatmap"];
  loading: boolean;
  error: string;
}) {
  return (
    <section className="rd-panel">
      <div className="rd-panel-title">
        <div>
          <span className="rd-eyebrow"><AlertTriangle size={14} /> Risk Heatmap</span>
          <h2>Candidate risk signals</h2>
        </div>
      </div>
      <div className="rd-risk-legend">
        {(["low", "medium", "high", "critical"] as RiskLevel[]).map((level) => (
          <span key={level}><i className={`risk-dot ${level}`} />{riskLabel(level)}</span>
        ))}
      </div>
      {loading ? (
        <div className="rd-skeleton-list" />
      ) : error ? (
        <div className="rd-empty compact">{error}</div>
      ) : !rows.length ? (
        <div className="rd-empty compact">No risk data available.</div>
      ) : (
        <div className="rd-heatmap">
          <div className="rd-heatmap-head">
            <span>Candidate</span><span>Code Quality</span><span>Security</span><span>Maintainability</span><span>Testing</span><span>Reliability</span>
          </div>
          {rows.map((row) => (
            <div className="rd-heatmap-row" key={row.candidate_name}>
              <strong>{row.candidate_name}</strong>
              <RiskPill level={row.code_quality} />
              <RiskPill level={row.security} />
              <RiskPill level={row.maintainability} />
              <RiskPill level={row.testing} />
              <RiskPill level={row.reliability} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function RiskPill({ level }: { level: RiskLevel }) {
  return <span className="rd-risk-pill"><i className={`risk-dot ${level}`} />{riskLabel(level)}</span>;
}

function DistributionBar({
  label,
  range,
  value,
  total,
  tone,
}: {
  label: string;
  range: string;
  value: number;
  total: number;
  tone: string;
}) {
  const pct = total ? Math.round((value / total) * 100) : 0;
  return (
    <div className="rd-bar-row">
      <div>
        <strong>{label}</strong>
        <span>{range}</span>
      </div>
      <div className="rd-bar-track"><i className={tone} style={{ width: `${pct}%` }} /></div>
      <b>{value}</b>
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="rd-table-skeleton">
      {Array.from({ length: 7 }).map((_, index) => <div className="rd-skeleton" key={index} />)}
    </div>
  );
}

function InsightSkeleton() {
  return (
    <div className="rd-insight-skeleton">
      <div className="rd-skeleton avatar" />
      <div className="rd-skeleton title" />
      <div className="rd-skeleton circle" />
      <div className="rd-skeleton line" />
      <div className="rd-skeleton line short" />
      <div className="rd-skeleton line" />
    </div>
  );
}

function distributionGradient(distribution: DashboardSummary["task_distribution"]) {
  const colors = {
    excellent: "#34d399",
    good: "#a855f7",
    fair: "#fbbf24",
    poor: "#f87171",
  };
  const total = distribution.excellent + distribution.good + distribution.fair + distribution.poor;
  if (!total) return "conic-gradient(rgba(148,163,184,.18) 0deg 360deg)";

  let current = 0;
  return `conic-gradient(${(["excellent", "good", "fair", "poor"] as const).map((key) => {
    const start = current;
    current += (distribution[key] / total) * 360;
    return `${colors[key]} ${start}deg ${current}deg`;
  }).join(", ")})`;
}

const dashboardCss = `
.rd-page {
  min-height: 100vh;
  padding: 28px;
  color: var(--sp-text);
  background: var(--sp-bg-gradient);
  font-family: var(--font-body);
}
.rd-header, .rd-actions, .rd-panel-title, .rd-candidate-cell, .rd-repo-cell a, .rd-insight-head, .rd-insight-actions, .rd-risk-legend, .rd-risk-pill, .rd-eyebrow, .rd-badge, .rd-clear-btn, .rd-ghost-btn, .rd-primary-btn, .rd-input-icon, .rd-kpi small {
  display: flex;
  align-items: center;
}
.rd-header {
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 22px;
}
.rd-header h1 {
  margin: 0;
  font-family: var(--font-heading);
  font-size: clamp(28px, 4vw, 42px);
  font-weight: 700;
  line-height: 1.05;
  letter-spacing: -0.02em;
}
.rd-header p {
  margin: 8px 0 0;
  color: var(--sp-text-muted);
  font-size: 14px;
}
.rd-actions {
  flex-wrap: wrap;
  gap: 10px;
  justify-content: flex-end;
}
.rd-ghost-btn, .rd-primary-btn, .rd-clear-btn, .rd-icon-btn {
  border: 1px solid var(--sp-border);
  border-radius: 8px;
  cursor: pointer;
  font-weight: 700;
  transition: transform .16s ease, border-color .16s ease, background .16s ease;
}
.rd-ghost-btn, .rd-primary-btn, .rd-clear-btn {
  gap: 8px;
  min-height: 38px;
  padding: 9px 13px;
  color: var(--sp-text);
}
.rd-ghost-btn {
  background: var(--sp-surface);
}
.rd-primary-btn {
  background: linear-gradient(135deg, #8b5cf6, #a855f7);
  border-color: rgba(168, 85, 247, .55);
}
.rd-clear-btn {
  background: var(--sp-surface-strong);
  color: var(--sp-text-secondary);
}
.rd-ghost-btn:hover, .rd-primary-btn:hover, .rd-clear-btn:hover, .rd-icon-btn:hover {
  transform: translateY(-1px);
  border-color: rgba(168, 85, 247, .55);
}
.rd-ghost-btn:disabled, .rd-primary-btn:disabled {
  cursor: not-allowed;
  opacity: .55;
}
.rd-kpis {
  display: grid;
  grid-template-columns: repeat(5, minmax(145px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}
.rd-kpi, .rd-panel {
  background: var(--sp-surface);
  border: 1px solid var(--sp-border);
  box-shadow: var(--sp-shadow);
  backdrop-filter: blur(18px);
}
.rd-kpi {
  position: relative;
  min-height: 138px;
  padding: 16px;
  border-radius: 8px;
  overflow: hidden;
}
.rd-kpi::after {
  content: "";
  position: absolute;
  inset: auto -30px -50px auto;
  width: 100px;
  height: 100px;
  background: rgba(168, 85, 247, .12);
  transform: rotate(20deg);
}
.rd-kpi-icon {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  margin-bottom: 13px;
  background: rgba(168, 85, 247, .15);
  color: #c4b5fd;
}
.rd-kpi-icon.green { background: rgba(52,211,153,.15); color: #34d399; }
.rd-kpi-icon.yellow { background: rgba(251,191,36,.15); color: #fbbf24; }
.rd-kpi-icon.orange { background: rgba(251,146,60,.15); color: #fb923c; }
.rd-kpi-icon.red { background: rgba(248,113,113,.15); color: #f87171; }
.rd-kpi span {
  display: block;
  color: var(--sp-text-muted);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .04em;
}
.rd-kpi strong {
  display: block;
  margin-top: 6px;
  font-size: 26px;
  line-height: 1;
}
.rd-kpi small {
  gap: 4px;
  margin-top: 10px;
  color: var(--sp-text-muted);
  font-size: 12px;
}
.rd-panel {
  border-radius: 8px;
  padding: 18px;
}
.rd-panel-title {
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 16px;
}
.rd-panel-title h2 {
  margin: 5px 0 0;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.02em;
}
.rd-eyebrow {
  gap: 7px;
  color: #a78bfa;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .04em;
}
.rd-filters {
  margin-bottom: 14px;
}
.rd-filter-grid {
  display: grid;
  grid-template-columns: 1.4fr 1.4fr repeat(4, minmax(170px, 1fr));
  gap: 12px;
}
.rd-field {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.rd-field > span {
  color: var(--sp-text-muted);
  font-size: 12px;
  font-weight: 700;
}
.rd-field input, .rd-field select {
  width: 100%;
  min-height: 38px;
  border: 1px solid var(--sp-border);
  border-radius: 8px;
  background: var(--sp-input-bg);
  color: var(--sp-text);
  padding: 9px 10px;
  outline: none;
}
.rd-field input:focus, .rd-field select:focus {
  border-color: rgba(168, 85, 247, .65);
}
.rd-input-icon {
  gap: 8px;
  border: 1px solid var(--sp-border);
  border-radius: 8px;
  background: var(--sp-input-bg);
  padding-left: 10px;
  color: var(--sp-text-muted);
}
.rd-input-icon input {
  border: 0;
  background: transparent;
  padding-left: 0;
}
.rd-range {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.rd-main-grid {
  display: block;
}
.rd-table-panel {
  min-width: 0;
}
.rd-table-wrap {
  overflow-x: auto;
}
.rd-table {
  width: 100%;
  min-width: 1060px;
  border-collapse: separate;
  border-spacing: 0 8px;
}
.rd-table th {
  padding: 0 12px 8px;
  color: var(--sp-text-muted);
  font-size: 11px;
  text-align: left;
  text-transform: uppercase;
  letter-spacing: .04em;
  white-space: nowrap;
}
.rd-table td {
  padding: 11px 12px;
  background: var(--sp-surface-strong);
  border-top: 1px solid var(--sp-border-soft);
  border-bottom: 1px solid var(--sp-border-soft);
  color: var(--sp-text-secondary);
  font-size: 13px;
}
.rd-table tr td:first-child {
  border-left: 1px solid var(--sp-border-soft);
  border-radius: 8px 0 0 8px;
}
.rd-table tr td:last-child {
  border-right: 1px solid var(--sp-border-soft);
  border-radius: 0 8px 8px 0;
}
.rd-table tbody tr {
  cursor: pointer;
}
.rd-table tr.selected td {
  background: var(--sp-surface-hover);
  border-color: rgba(168, 85, 247, .4);
}
.rd-rank {
  display: inline-grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--sp-surface-hover);
  color: var(--sp-text-secondary);
  font-weight: 700;
}
.rd-candidate-cell {
  gap: 10px;
}
.rd-avatar {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 50%;
  background: linear-gradient(135deg, #8b5cf6, #ec4899);
  border: 2px solid rgba(139,92,246,.72);
  color: white;
  font-size: 12px;
  font-weight: 700;
  overflow: hidden;
  position: relative;
  box-shadow: 0 0 0 2px rgba(139,92,246,.12);
}
.rd-avatar.large {
  width: 72px;
  height: 72px;
  font-size: 16px;
}
.rd-avatar img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.rd-avatar > span {
  position: relative;
  z-index: 1;
}
.rd-avatar img + span {
  opacity: 0;
}
.rd-candidate-cell strong, .rd-repo-cell strong {
  display: block;
  color: var(--sp-text);
}
.rd-candidate-cell span, .rd-repo-cell a {
  color: var(--sp-text-muted);
  font-size: 12px;
  text-decoration: none;
}
.rd-repo-cell a {
  gap: 5px;
  margin-top: 4px;
  color: #a78bfa;
}
.rd-score {
  font-weight: 700;
}
.rd-score-green { color: #34d399; }
.rd-score-yellow { color: #fbbf24; }
.rd-score-orange { color: #fb923c; }
.rd-score-red { color: #f87171; }
.rd-score-muted { color: var(--sp-text-muted); }
.rd-score-purple { color: #c4b5fd; }
.rd-badge {
  display: inline-flex;
  gap: 5px;
  width: max-content;
  max-width: 100%;
  min-height: 24px;
  padding: 4px 8px;
  border-radius: 999px;
  border: 1px solid var(--sp-border-soft);
  background: var(--sp-surface-strong);
  color: var(--sp-text-secondary);
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}
.rd-badge.green, .rd-badge.low { color: #34d399; background: rgba(52,211,153,.12); border-color: rgba(52,211,153,.28); }
.rd-badge.yellow, .rd-badge.medium { color: #fbbf24; background: rgba(251,191,36,.12); border-color: rgba(251,191,36,.28); }
.rd-badge.orange, .rd-badge.high { color: #fb923c; background: rgba(251,146,60,.12); border-color: rgba(251,146,60,.28); }
.rd-badge.red, .rd-badge.critical { color: #f87171; background: rgba(248,113,113,.12); border-color: rgba(248,113,113,.28); }
.rd-badge.purple, .rd-badge.rec-strong_hire { color: #c4b5fd; background: rgba(168,85,247,.15); border-color: rgba(168,85,247,.35); }
.rd-badge.rec-interview { color: #34d399; background: rgba(52,211,153,.12); border-color: rgba(52,211,153,.28); }
.rd-badge.rec-review_required { color: #fbbf24; background: rgba(251,191,36,.12); border-color: rgba(251,191,36,.28); }
.rd-badge.rec-reject { color: #f87171; background: rgba(248,113,113,.12); border-color: rgba(248,113,113,.28); }
.rd-icon-btn {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  background: rgba(168, 85, 247, .11);
  color: #c4b5fd;
}
.rd-insights {
  position: sticky;
  top: 18px;
  align-self: start;
}
.rd-insight-head {
  gap: 12px;
}
.rd-insight-head h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--sp-text);
}
.rd-insight-head p {
  margin: 2px 0 7px;
  color: var(--sp-text-muted);
  font-size: 13px;
}
.rd-task-chip {
  display: inline-block;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #c4b5fd;
  font-size: 12px;
}
.rd-insight-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 16px 0;
}
.rd-score-ring {
  width: 132px;
  height: 132px;
  display: grid;
  place-items: center;
  margin: 4px auto 18px;
  border-radius: 50%;
}
.rd-score-ring > div {
  width: 100px;
  height: 100px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--sp-surface);
  text-align: center;
}
.rd-score-ring strong {
  display: block;
  font-size: 24px;
}
.rd-score-ring span {
  color: var(--sp-text-muted);
  font-size: 11px;
  font-weight: 700;
}
.rd-insight-body > p {
  color: var(--sp-text-secondary);
  line-height: 1.65;
  margin: 0 0 14px;
}
.rd-insight-list {
  margin-top: 14px;
}
.rd-insight-list > span, .rd-reason > span {
  color: var(--sp-text-muted);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .04em;
}
.rd-insight-list ul {
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
}
.rd-insight-list li {
  display: flex;
  gap: 8px;
  margin-bottom: 7px;
  color: var(--sp-text-secondary);
  font-size: 13px;
}
.rd-insight-list li span, .risk-dot {
  width: 9px;
  height: 9px;
  flex: 0 0 auto;
  border-radius: 50%;
  margin-top: 5px;
}
.rd-insight-list li span.green, .risk-dot.low { background: #34d399; }
.rd-insight-list li span.orange, .risk-dot.high { background: #fb923c; }
.risk-dot.medium { background: #fbbf24; }
.risk-dot.critical { background: #f87171; }
.rd-reason {
  margin-top: 14px;
  padding: 12px;
  border-radius: 8px;
  background: var(--sp-surface-strong);
  border: 1px solid var(--sp-border-soft);
}
.rd-reason p {
  margin: 6px 0 0;
  color: var(--sp-text-secondary);
  font-size: 13px;
}
.rd-insight-actions {
  flex-wrap: wrap;
  gap: 9px;
  margin-top: 16px;
}
.rd-bottom-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(320px, .7fr);
  gap: 14px;
  margin-top: 14px;
}
.rd-risk-legend {
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.rd-risk-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--sp-text-muted);
  font-size: 12px;
}
.rd-heatmap {
  min-width: 0;
  overflow-x: auto;
}
.rd-heatmap-head, .rd-heatmap-row {
  display: grid;
  grid-template-columns: 1.3fr repeat(5, minmax(120px, 1fr));
  gap: 8px;
  align-items: center;
  min-width: 760px;
}
.rd-heatmap-head {
  color: var(--sp-text-muted);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .04em;
  padding: 0 6px 8px;
}
.rd-heatmap-row {
  padding: 10px 6px;
  border-top: 1px solid var(--sp-border-soft);
}
.rd-heatmap-row strong {
  color: var(--sp-text);
  font-size: 13px;
}
.rd-risk-pill {
  gap: 6px;
  color: var(--sp-text-secondary);
  font-size: 12px;
}
.rd-analytics {
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr);
  gap: 18px;
  align-items: center;
}
.rd-donut {
  width: 150px;
  height: 150px;
  display: grid;
  place-items: center;
  border-radius: 50%;
}
.rd-donut > div {
  width: 104px;
  height: 104px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--sp-surface);
  text-align: center;
}
.rd-donut strong {
  display: block;
  font-size: 24px;
}
.rd-donut span {
  color: var(--sp-text-muted);
  font-size: 11px;
}
.rd-bars {
  display: grid;
  gap: 12px;
}
.rd-bar-row {
  display: grid;
  grid-template-columns: 94px 1fr 28px;
  gap: 10px;
  align-items: center;
}
.rd-bar-row strong {
  display: block;
  color: var(--sp-text);
  font-size: 13px;
}
.rd-bar-row span {
  color: var(--sp-text-muted);
  font-size: 11px;
}
.rd-bar-track {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(148, 163, 184, .13);
}
.rd-bar-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
}
.rd-bar-track i.green { background: #34d399; }
.rd-bar-track i.purple { background: #a855f7; }
.rd-bar-track i.yellow { background: #fbbf24; }
.rd-bar-track i.red { background: #f87171; }
.rd-bar-row b {
  color: var(--sp-text);
  font-size: 13px;
  text-align: right;
}
.rd-empty {
  min-height: 190px;
  display: grid;
  place-items: center;
  gap: 10px;
  color: var(--sp-text-muted);
  text-align: center;
}
.rd-empty.compact {
  min-height: 80px;
}
.rd-error {
  color: #f87171;
}
.rd-inline-error {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(248, 113, 113, .1);
  border: 1px solid rgba(248, 113, 113, .24);
  color: #fecaca;
  font-size: 13px;
}
.rd-skeleton {
  border-radius: 8px;
  background: linear-gradient(90deg, var(--sp-surface-strong), var(--sp-surface-hover), var(--sp-surface-strong));
  background-size: 220% 100%;
  animation: rdShimmer 1.25s linear infinite;
}
.rd-skeleton-value {
  width: 82px;
  height: 28px;
  margin-top: 8px;
}
.rd-table-skeleton {
  display: grid;
  gap: 10px;
}
.rd-table-skeleton .rd-skeleton {
  height: 56px;
}
.rd-insight-skeleton {
  display: grid;
  gap: 12px;
}
.rd-insight-skeleton .avatar {
  width: 52px;
  height: 52px;
  border-radius: 50%;
}
.rd-insight-skeleton .title {
  width: 70%;
  height: 22px;
}
.rd-insight-skeleton .circle {
  width: 132px;
  height: 132px;
  border-radius: 50%;
  margin: 0 auto;
}
.rd-insight-skeleton .line {
  height: 14px;
}
.rd-insight-skeleton .short {
  width: 72%;
}
.rd-skeleton-list {
  height: 180px;
  border-radius: 8px;
  background: rgba(148, 163, 184, .08);
}
.rd-toast {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 600;
  padding: 12px 15px;
  border-radius: 8px;
  border: 1px solid rgba(52, 211, 153, .35);
  background: var(--sp-surface);
  color: #34d399;
  box-shadow: var(--sp-shadow);
  font-weight: 700;
  font-size: 13px;
}
.rd-toast.error {
  border-color: rgba(248, 113, 113, .35);
  color: #f87171;
}
.rd-spin {
  animation: rdSpin .9s linear infinite;
}
.rd-tabs-nav {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 14px;
  padding: 4px;
  background: var(--sp-surface);
  border: 1px solid var(--sp-border);
  border-radius: 10px;
  width: fit-content;
}
.rd-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 18px;
  border-radius: 7px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--sp-text-muted);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: color .18s ease, background .18s ease, border-color .18s ease;
}
.rd-tab-btn:hover {
  color: var(--sp-text-secondary);
  background: var(--sp-surface-hover);
}
.rd-tab-btn.active {
  background: linear-gradient(135deg, rgba(139,92,246,.28), rgba(168,85,247,.18));
  border-color: rgba(168, 85, 247, .45);
  color: #c4b5fd;
}
:root[data-theme="light"] .rd-avatar.large,
:root[data-theme="light"] .rd-avatar {
  box-shadow: 0 0 0 2px rgba(139,92,246,.15), 0 10px 24px rgba(15,23,42,.08);
}
:root[data-theme="light"] .rd-ghost-btn,
:root[data-theme="light"] .rd-clear-btn,
:root[data-theme="light"] .rd-field input,
:root[data-theme="light"] .rd-field select,
:root[data-theme="light"] .rd-input-icon {
  background: var(--sp-input-bg);
}
:root[data-theme="light"] .rd-toast {
  background: rgba(255,255,255,.96);
  box-shadow: var(--sp-shadow);
}
@keyframes rdShimmer {
  to { background-position: -220% 0; }
}
@keyframes rdSpin {
  to { transform: rotate(360deg); }
}
@media (max-width: 1450px) {
  .rd-kpis { grid-template-columns: repeat(3, minmax(170px, 1fr)); }
  .rd-filter-grid { grid-template-columns: repeat(3, minmax(190px, 1fr)); }
}
@media (max-width: 1120px) {
  .rd-main-grid, .rd-bottom-grid { grid-template-columns: 1fr; }
  .rd-insights { position: static; }
  .rd-filter-grid { grid-template-columns: repeat(2, minmax(180px, 1fr)); }
}
@media (max-width: 720px) {
  .rd-page { padding: 18px; }
  .rd-header { align-items: flex-start; flex-direction: column; }
  .rd-actions { justify-content: flex-start; }
  .rd-kpis, .rd-filter-grid, .rd-analytics { grid-template-columns: 1fr; }
  .rd-donut { margin: 0 auto; }
}
`;
