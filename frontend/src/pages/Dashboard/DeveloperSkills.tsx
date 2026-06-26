import { useEffect, useMemo, useState, type ReactNode } from "react";
import api from "../../api/auth";
import DashboardLayout from "../DashboardLayout";

interface RepoSummary {
  analysis_id: number;
  repo_name: string;
  full_name: string;
  branch: string;
  completed_at: string | null;
  skill_score: number | null;
  skill_score_level: string;
  sonar_health_score: number | null;
  sonar_state: string;
  quality_gate: string | null;
  bugs: number | null;
  code_smells: number | null;
  coverage: number | null;
  coverage_available?: boolean;
  coverage_status?: string | null;
  coverage_reason?: string | null;
  coverage_source?: string | null;
  duplication_percentage: number | null;
  cognitive_complexity: number | null;
  reliability_rating: string | null;
  maintainability_rating: string | null;
  technical_debt_minutes: number | null;
  lines_of_code: number | null;
}

interface SkillsSummary {
  skill_score: number | null;
  skill_score_level: string;
  skill_score_delta?: number | null;
  sonar_health_score: number | null;
  sonar_state: string;
  delta: number | null;
  sonar_metrics: Partial<RepoSummary>;
  repos: RepoSummary[];
}

type Issue = { type: string; severity: string; file: string | null; line: number | null; message: string };
type FileMetric = {
  file: string | null;
  lines_of_code: number | null;
  complexity: number | null;
  cognitive_complexity: number | null;
  duplication: number | null;
  coverage: number | null;
  duplicated_lines: number | null;
  functions: number | null;
};
type ComplexFunction = { function: string; file: string | null; complexity: number | null };
type TableHeader = string | { label: string; align?: "left" | "right"; width?: string | number };

interface SonarDashboard {
  repository?: { name: string; full_name: string; branch: string; analysis_date: string | null; duration_seconds?: number | null };
  overall?: { skill_score: number | null; skill_score_level: string; sonar_health_score: number | null; sonar_state: string; quality_gate: string | { status?: string } | null };
  reliability?: { rating: string | null; total_bugs: number | null; issues: Issue[] };
  maintainability?: { rating: string | null; code_smells: number | null; technical_debt_minutes: number | null; debt_ratio: number | null; issues: Issue[] };
  coverage?: { available?: boolean; status?: string | null; reason?: string | null; source?: string | null; coverage: number | null; line_coverage: number | null; branch_coverage: number | null; uncovered_lines: number | null };
  duplication?: { percentage: number | null; duplicated_lines: number | null; duplicated_blocks: number | null; duplicated_files: number | null };
  complexity?: { cyclomatic_complexity: number | null; cognitive_complexity: number | null };
  project_size?: { lines_of_code: number | null; files: number | null; directories?: number | null; functions: number | null; classes: number | null; statements?: number | null };
  file_metrics?: FileMetric[];
  complex_functions?: ComplexFunction[];
  issues_explorer?: Issue[];
  analysis_summary?: Record<string, unknown>;
}

interface SonarFile {
  file_path: string;
  measures: Record<string, number | string>;
  coverage: number | null;
  duplicated_lines: number | null;
  duplicated_lines_density: number | null;
  ncloc: number | null;
  complexity: number | null;
  cognitive_complexity: number | null;
  functions: number | null;
  classes: number | null;
  statements: number | null;
}

interface SonarIssue {
  issue_key: string;
  file_path: string | null;
  line: number | null;
  type: string;
  severity: string;
  rule: string | null;
  message: string;
  status: string | null;
}

interface SonarResultResponse {
  analysis_run_id: number;
  repo: string;
  branch: string;
  analysis_scope: string;
  status: string;
  completed_at: string | null;
  skill_score: number | null;
  skill_score_level: string;
  sonar: {
    available: boolean;
    project_key?: string;
    quality_gate?: string | null;
    sonar_health_score?: number | null;
    measures?: Record<string, number | string>;
    coverage?: Record<string, unknown>;
    reason?: string;
  };
  files: SonarFile[];
  issues: SonarIssue[];
  summary: {
    files_count: number;
    issues_count: number;
    bugs_count: number;
    code_smells_count: number;
  };
}

const accent = "#6366f1";
const success = "#34d399";
const warning = "#fbbf24";
const danger = "#f87171";
const muted = "#94a3b8";

const scoreColor = (score: number | null | undefined) => score == null ? muted : score >= 80 ? success : score >= 60 ? warning : danger;
const num = (value: number | null | undefined) => typeof value === "number" && Number.isFinite(value) ? value : null;
const fmt = (value: number | string | null | undefined, suffix = "") => value === null || value === undefined || value === "" ? "—" : `${value}${suffix}`;
const pct = (value: number | null | undefined) => value == null ? "—" : `${Math.round(value)}%`;
const dateFmt = (value: string | null | undefined) => value ? new Date(value).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "—";
const minutesFmt = (value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) return "—";
  const h = Math.floor(value / 60);
  const m = Math.round(value % 60);
  return h ? `${h}h ${m}m` : `${m}m`;
};
const secondsFmt = (value: number | null | undefined) => value == null ? "—" : `${Math.round(value)} sec`;
const severityTone = (severity?: string | null) => {
  const s = (severity || "").toUpperCase();
  if (["BLOCKER", "CRITICAL", "HIGH"].includes(s)) return danger;
  if (["MAJOR", "MEDIUM"].includes(s)) return warning;
  return success;
};
const issueTypeLabel = (type?: string | null) => (type || "").replace("CODE_SMELL", "Code Smell").replace("BUG", "Bug") || "Issue";

function Badge({ children, tone = accent }: { children: ReactNode; tone?: string }) {
  return <span className="sp-badge" style={{ color: tone, borderColor: `${tone}35`, background: `${tone}14` }}>{children}</span>;
}

function Card({ children, className = "", style }: { children: ReactNode; className?: string; style?: React.CSSProperties }) {
  return <div className={`sp-card ${className}`} style={style}>{children}</div>;
}

function Metric({ label, value, sub, tone = "var(--text-primary)" }: { label: string; value: ReactNode; sub?: string; tone?: string }) {
  return (
    <Card className="metric-card" style={{ padding: "18px 20px", minHeight: 108 }}>
      <div className="sp-label">{label}</div>
      <div style={{ fontSize: 27, fontWeight: 900, color: tone, marginTop: 8, lineHeight: 1, letterSpacing: "-0.8px" }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 9 }}>{sub}</div>}
    </Card>
  );
}

function SectionTitle({ kicker, title, description, right }: { kicker: string; title: string; description?: string; right?: ReactNode }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, marginBottom: 18, flexWrap: "wrap" }}>
      <div>
        <div className="sp-label">{kicker}</div>
        <h2 style={{ margin: "6px 0 4px", fontFamily: "'Inter',sans-serif", fontSize: 21, letterSpacing: "-.35px" }}>{title}</h2>
        {description && <p style={{ margin: 0, color: "var(--text-muted)", fontSize: 13, lineHeight: 1.55 }}>{description}</p>}
      </div>
      {right}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <div className="sp-empty">{text}</div>;
}

function ProgressBar({ value, tone = accent, max = 100 }: { value: number | null | undefined; tone?: string; max?: number }) {
  const width = Math.max(0, Math.min(100, ((value || 0) / max) * 100));
  return (
    <div style={{ height: 10, borderRadius: 999, background: "var(--border)", overflow: "hidden" }}>
      <div style={{ width: `${width}%`, height: "100%", borderRadius: 999, background: `linear-gradient(90deg, ${tone}, #ec4899)`, transition: "width .5s ease" }} />
    </div>
  );
}

function Donut({ items }: { items: Array<{ label: string; value: number; tone: string }> }) {
  const total = items.reduce((a, b) => a + b.value, 0);
  let cursor = 0;
  const gradient = total ? items.map(item => {
    const start = cursor;
    const end = cursor + (item.value / total) * 100;
    cursor = end;
    return `${item.tone} ${start}% ${end}%`;
  }).join(", ") : "var(--border) 0% 100%";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 18, flexWrap: "wrap" }}>
      <div style={{ width: 124, height: 124, borderRadius: "50%", background: `conic-gradient(${gradient})`, display: "grid", placeItems: "center", flexShrink: 0 }}>
        <div style={{ width: 76, height: 76, borderRadius: "50%", background: "var(--bg-base)", border: "1px solid var(--border)", display: "grid", placeItems: "center", textAlign: "center" }}>
          <strong style={{ fontSize: 21 }}>{total}</strong>
          <span style={{ fontSize: 11, color: "var(--text-muted)", marginTop: -12 }}>issues</span>
        </div>
      </div>
      <div style={{ display: "grid", gap: 9, minWidth: 180, flex: 1 }}>
        {items.map(item => <div key={item.label} style={{ display: "grid", gridTemplateColumns: "80px 1fr 32px", gap: 10, alignItems: "center", fontSize: 12.5 }}><span style={{ color: "var(--text-secondary)" }}>{item.label}</span><ProgressBar value={item.value} max={Math.max(total, 1)} tone={item.tone} /><strong>{item.value}</strong></div>)}
      </div>
    </div>
  );
}

const numericHeaders = new Set(["Value", "Line", "Lines", "Coverage", "Complexity", "Smells", "Debt", "Duplicated Lines"]);

function Table({ headers, children }: { headers: TableHeader[]; children: ReactNode }) {
  const normalizedHeaders = headers.map((header) => (
    typeof header === "string"
      ? { label: header, align: numericHeaders.has(header) ? "right" as const : "left" as const }
      : { align: "left" as const, ...header }
  ));

  return (
    <div className="sp-table-wrap">
      <table className="sp-table">
        <thead>
          <tr>
            {normalizedHeaders.map((header) => (
              <th
                key={header.label}
                style={{
                  textAlign: header.align,
                  width: header.width,
                }}
              >
                {header.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function Row({ children, onClick }: { children: ReactNode; onClick?: () => void }) {
  return <tr onClick={onClick} style={{ cursor: onClick ? "pointer" : "default", borderBottom: "1px solid var(--border)" }}>{children}</tr>;
}

function Cell({ children, align = "left" }: { children: ReactNode; align?: "left" | "right" }) {
  return <td className={align === "right" ? "sp-cell-number" : undefined} style={{ textAlign: align }}>{children}</td>;
}

function groupSeverity(issues: Issue[] = []) {
  const critical = issues.filter(i => ["BLOCKER", "CRITICAL", "HIGH"].includes((i.severity || "").toUpperCase())).length;
  const major = issues.filter(i => ["MAJOR", "MEDIUM"].includes((i.severity || "").toUpperCase())).length;
  const minor = Math.max(0, issues.length - critical - major);
  return { critical, major, minor };
}

function topFilesByIssues(issues: Issue[] = []) {
  const map = new Map<string, number>();
  issues.forEach(i => map.set(i.file || "n/a", (map.get(i.file || "n/a") || 0) + 1));
  return [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
}

const sonarNumber = (value: number | string | null | undefined): number | null => {
  if (value === null || value === undefined || value === "") return null;
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : null;
};

const sonarString = (value: number | string | null | undefined): string | null => {
  if (value === null || value === undefined || value === "") return null;
  return String(value);
};

const coverageString = (coverage: Record<string, unknown> | undefined, key: string): string | null => {
  const value = coverage?.[key];
  return typeof value === "string" && value ? value : null;
};

function mapSonarResultToDashboard(response: SonarResultResponse): SonarDashboard {
  const measures = response.sonar.measures || {};
  const coverage = response.sonar.coverage || {};
  const repoName = response.repo?.split("/").pop() || response.repo || "Repository";
  const mappedIssues = response.issues.map((issue) => ({
    type: issue.type,
    severity: issue.severity,
    file: issue.file_path,
    line: issue.line,
    message: issue.message,
  }));

  if (!response.sonar.available) {
    return {
      repository: {
        name: repoName,
        full_name: response.repo,
        branch: response.branch,
        analysis_date: response.completed_at,
      },
      overall: {
        skill_score: response.skill_score ?? null,
        skill_score_level: response.skill_score_level || "Unavailable",
        sonar_health_score: null,
        sonar_state: response.status,
        quality_gate: null,
      },
      reliability: { rating: null, total_bugs: 0, issues: [] },
      maintainability: {
        rating: null,
        code_smells: 0,
        technical_debt_minutes: null,
        debt_ratio: null,
        issues: [],
      },
      coverage: {
        available: false,
        status: "unavailable",
        reason: response.sonar.reason || "sonar_results_not_found",
        source: null,
        coverage: null,
        line_coverage: null,
        branch_coverage: null,
        uncovered_lines: null,
      },
      duplication: {
        percentage: null,
        duplicated_lines: null,
        duplicated_blocks: null,
        duplicated_files: null,
      },
      complexity: {
        cyclomatic_complexity: null,
        cognitive_complexity: null,
      },
      project_size: {
        lines_of_code: null,
        files: 0,
        functions: null,
        classes: null,
        statements: null,
      },
      file_metrics: [],
      complex_functions: [],
      issues_explorer: [],
      analysis_summary: response.summary,
    };
  }

  return {
    repository: {
      name: repoName,
      full_name: response.repo,
      branch: response.branch,
      analysis_date: response.completed_at,
    },
    overall: {
      skill_score: response.skill_score ?? null,
      skill_score_level: response.skill_score_level || "Unavailable",
      sonar_health_score: response.sonar.sonar_health_score ?? null,
      sonar_state: response.status,
      quality_gate: response.sonar.quality_gate ?? null,
    },
    reliability: {
      rating: sonarString(measures.reliability_rating),
      total_bugs: response.summary.bugs_count,
      issues: mappedIssues.filter((issue) => issue.type === "BUG"),
    },
    maintainability: {
      rating: sonarString(measures.sqale_rating),
      code_smells: response.summary.code_smells_count,
      technical_debt_minutes: sonarNumber(measures.sqale_index),
      debt_ratio: sonarNumber(measures.sqale_debt_ratio),
      issues: mappedIssues.filter((issue) => issue.type === "CODE_SMELL"),
    },
    coverage: {
      available: response.sonar.available,
      status: coverageString(coverage, "status"),
      reason: coverageString(coverage, "reason"),
      source: coverageString(coverage, "source"),
      coverage: sonarNumber(measures.coverage),
      line_coverage: sonarNumber(measures.line_coverage),
      branch_coverage: sonarNumber(measures.branch_coverage),
      uncovered_lines: sonarNumber(measures.uncovered_lines),
    },
    duplication: {
      percentage: sonarNumber(measures.duplicated_lines_density),
      duplicated_lines: sonarNumber(measures.duplicated_lines),
      duplicated_blocks: sonarNumber(measures.duplicated_blocks),
      duplicated_files: sonarNumber(measures.duplicated_files),
    },
    complexity: {
      cyclomatic_complexity: sonarNumber(measures.complexity),
      cognitive_complexity: sonarNumber(measures.cognitive_complexity),
    },
    project_size: {
      lines_of_code: sonarNumber(measures.ncloc),
      files: sonarNumber(measures.files),
      functions: sonarNumber(measures.functions),
      classes: sonarNumber(measures.classes),
      statements: sonarNumber(measures.statements),
    },
    file_metrics: response.files.map((file) => ({
      file: file.file_path,
      lines_of_code: file.ncloc,
      complexity: file.complexity,
      cognitive_complexity: file.cognitive_complexity,
      duplication: file.duplicated_lines_density,
      coverage: file.coverage,
      duplicated_lines: file.duplicated_lines,
      functions: file.functions,
    })),
    complex_functions: [],
    issues_explorer: mappedIssues,
    analysis_summary: response.summary,
  };
}

export default function DeveloperSkills() {
  const [summary, setSummary] = useState<SkillsSummary | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<SonarDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);
  const [expandedIssue, setExpandedIssue] = useState<Issue | null>(null);
  const [filter, setFilter] = useState<"ALL" | "BUG" | "CODE_SMELL" | "RELIABILITY">("ALL");
  const [query, setQuery] = useState("");

  useEffect(() => {
    api.get<SkillsSummary>("/analysis/skills/summary")
      .then((res) => {
        setSummary(res.data);
        setSelectedId(res.data.repos?.[0]?.analysis_id ?? null);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedId) { setDetail(null); return; }
    let cancelled = false;
    setDetail(null);
    api.get<SonarResultResponse>(`/analysis/${selectedId}/sonar-results`)
      .then((res) => {
        const dashboard = mapSonarResultToDashboard(res.data);
        console.log("Sonar API", res.data);
        console.log("Mapped dashboard", dashboard);
        if (!cancelled) setDetail(dashboard);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      });
    return () => { cancelled = true; };
  }, [selectedId]);

  useEffect(() => {
    setFilter("ALL");
    setQuery("");
    setExpandedIssue(null);
    setSelectedIssue(null);
  }, [selectedId]);

  const current = summary?.repos.find((repo) => repo.analysis_id === selectedId) ?? null;
  const repo = detail?.repository;
  const skillScore = detail?.overall?.skill_score ?? current?.skill_score ?? null;
  const skillScoreLevel = detail?.overall?.skill_score_level ?? current?.skill_score_level ?? "Unavailable";
  const healthTone = scoreColor(skillScore);
  const coverageAvailable = detail?.coverage?.available ?? current?.coverage_available ?? ((detail?.coverage?.coverage ?? current?.coverage) != null);
  const coverageReason = detail?.coverage?.reason ?? current?.coverage_reason ?? "coverage_report_not_found";
  const coverageSource = detail?.coverage?.source ?? current?.coverage_source ?? null;
  const coverageValue = coverageAvailable ? (detail?.coverage?.coverage ?? current?.coverage ?? null) : null;
  const coverageUnavailableMessage = coverageReason === "sonar_results_not_found"
    ? "Sonar results unavailable"
    : coverageReason === "coverage_paths_do_not_match_repository"
    ? "The uploaded coverage.xml was received, but its file paths do not match this repository, so SonarQube could not import coverage data."
    : coverageReason === "coverage_xml_could_not_be_parsed"
      ? "The uploaded coverage.xml was received, but it could not be parsed. Upload a valid Cobertura-style coverage XML report."
      : "No coverage.xml report was uploaded and no coverage.xml report was found in the repository. Upload a coverage XML report to include test coverage in this analysis.";

  const allIssues = useMemo(() => detail?.issues_explorer || [], [detail?.issues_explorer]);
  const reliabilityIssues = useMemo(
    () => allIssues.filter(issue => String(issue.type).toUpperCase() === "BUG"),
    [allIssues],
  );
  const maintainabilityIssues = useMemo(
    () => allIssues.filter(issue => String(issue.type).toUpperCase() === "CODE_SMELL"),
    [allIssues],
  );
  const totalBugs = detail?.reliability?.total_bugs ?? 0;
  const visibleReliabilityIssues = Number(totalBugs) > 0 ? reliabilityIssues : [];
  const bugSeverity = groupSeverity(visibleReliabilityIssues);
  const smellSeverity = groupSeverity(maintainabilityIssues);

  useEffect(() => {
    console.log("selectedId", selectedId);
    console.log("repo", detail?.repository);
    console.log("reliability issues", reliabilityIssues);
    console.log("maintainability issues", maintainabilityIssues);
  }, [selectedId, detail?.repository, reliabilityIssues, maintainabilityIssues]);

  const fileMetrics = detail?.file_metrics || [];
  const lowCoverage = fileMetrics.filter(f => num(f.coverage) !== null).sort((a, b) => (a.coverage || 0) - (b.coverage || 0)).slice(0, 8);
  const duplicatedFiles = fileMetrics.filter(f => (f.duplicated_lines || 0) > 0 || (f.duplication || 0) > 0).sort((a, b) => (b.duplicated_lines || 0) - (a.duplicated_lines || 0)).slice(0, 8);
  const complexFiles = fileMetrics.filter(f => (f.complexity || 0) > 0 || (f.cognitive_complexity || 0) > 0).sort((a, b) => ((b.complexity || 0) + (b.cognitive_complexity || 0)) - ((a.complexity || 0) + (a.cognitive_complexity || 0))).slice(0, 8);
  const complexFunctions = (detail?.complex_functions || []).slice(0, 10);
  const showComplexityTables = complexFiles.length > 0 || complexFunctions.length > 0;
  const complexityGridColumns = complexFiles.length > 0 && complexFunctions.length > 0 ? "1fr 1fr" : "1fr";

  const filteredIssues = useMemo(() => allIssues.filter(issue => {
    const issueType = String(issue.type).toUpperCase();
    const matchesType = filter === "ALL" || (filter === "RELIABILITY" ? issueType === "BUG" : issueType === filter);
    const matchesSearch = !query.trim() || `${issue.file || ""} ${issue.message || ""} ${issue.severity || ""}`.toLowerCase().includes(query.trim().toLowerCase());
    return matchesType && matchesSearch;
  }), [allIssues, filter, query]);

  const recommendations = [
    ...(skillScore != null && skillScore < 70 ? ["Improve the overall Skill Score"] : ["Maintain the current Skill Score level"]),
    ...(coverageAvailable && coverageValue != null && coverageValue < 80 ? ["Add tests for low coverage files"] : []),
    ...(!coverageAvailable ? [coverageReason === "coverage_paths_do_not_match_repository" ? "Regenerate coverage.xml with repository-relative file paths" : "Upload coverage.xml to enable test coverage metrics"] : []),
    ...(detail?.duplication?.percentage != null && detail.duplication.percentage > 5 ? ["Remove duplicate validation and helper logic"] : []),
    ...(bugSeverity.critical > 0 ? [`Fix ${bugSeverity.critical} critical bugs`] : []),
    ...(complexFiles[0] ? [`Refactor ${complexFiles[0].file}`] : []),
  ];

  return (
    <DashboardLayout>
      <style>{`
        .sp-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; box-shadow: var(--shadow-card); transition: border-color .2s ease, background .3s ease, transform .2s ease; }
        .sp-card:hover { border-color: var(--border-hover); background: var(--bg-card-hover); }
        .metric-card:hover { transform: translateY(-1px); }
        .sp-label { font-size: 11px; font-weight: 800; color: rgba(167,139,250,.82); text-transform: uppercase; letter-spacing: .75px; }
        .sp-badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 999px; border: 1px solid; font-size: 11.5px; font-weight: 800; white-space: nowrap; }
        .sp-empty { padding: 28px 20px; border: 1px dashed var(--border-hover); border-radius: 14px; background: var(--bg-input); color: var(--text-muted); font-size: 13px; text-align: center; }
        .skl-select, .sp-search { background: var(--bg-input); border: 1px solid rgba(99,102,241,.25); border-radius: 12px; color: var(--text-primary); font-family: 'Inter', sans-serif; font-size: 13.5px; padding: 10px 14px; outline: none; transition: border-color .2s; }
        .skl-select:focus, .sp-search:focus { border-color: ${accent}80; }
        .skl-select option { background: var(--bg-base); color: var(--text-primary); }
        .filter-btn { border: 1px solid var(--border); background: var(--bg-input); color: var(--text-secondary); padding: 8px 12px; border-radius: 999px; cursor: pointer; font-size: 12px; font-weight: 800; }
        .filter-btn.active { color: ${accent}; border-color: ${accent}70; background: ${accent}14; }
        .sp-table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 14px; }
        .sp-table { width: 100%; border-collapse: collapse; min-width: 560px; table-layout: fixed; }
        .sp-table th { padding: 12px 16px; color: var(--text-muted); font-size: 11px; text-transform: uppercase; letter-spacing: .7px; background: var(--bg-input); border-bottom: 1px solid var(--border); white-space: nowrap; }
        .sp-table td { padding: 12px 16px; font-size: 13px; color: var(--text-secondary); vertical-align: top; overflow-wrap: anywhere; }
        .sp-table th:last-child, .sp-table td:last-child { padding-right: 18px; }
        .sp-cell-number { font-variant-numeric: tabular-nums; white-space: nowrap; }
        .sp-table tbody tr:hover td { background: var(--bg-input); color: var(--text-primary); }
        tbody tr:hover td { background: var(--bg-input); color: var(--text-primary); }
      `}</style>

      <div style={{ minHeight: "100vh", padding: "36px 40px 80px", color: "var(--text-primary)", fontFamily: "'Inter', sans-serif", background: "var(--bg-gradient)" }}>
        <div style={{ maxWidth: 1180, margin: "0 auto", display: "flex", flexDirection: "column", gap: 24 }}>
          <header style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.5fr) minmax(280px, .85fr)", gap: 18 }}>
            <Card style={{ padding: "28px 32px" }}>
              <Badge>Code Quality Dashboard</Badge>
              <h1 style={{ fontFamily: "'Inter', sans-serif", fontSize: 34, fontWeight: 800, letterSpacing: "-.8px", margin: "16px 0 8px", lineHeight: 1.1 }}>{repo?.name || current?.repo_name || "Repository"}</h1>
              <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: 14 }}>Python · FastAPI</p>
              <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 18, color: "var(--text-muted)", fontSize: 13 }}>
                <span>{fmt(detail?.project_size?.files ?? current?.lines_of_code ? detail?.project_size?.files : null)} Files</span>
                <span>·</span>
                <span>{fmt(detail?.project_size?.lines_of_code ?? current?.lines_of_code)} LOC</span>
                <span>·</span>
                <span>Analysis Date: {dateFmt(repo?.analysis_date || current?.completed_at)}</span>
                <span>·</span>
                <span>Duration: {secondsFmt(repo?.duration_seconds)}</span>
              </div>
              {summary && <div style={{ marginTop: 20 }}><select className="skl-select" value={selectedId ?? ""} onChange={(e) => setSelectedId(Number(e.target.value) || null)}>{summary.repos.map(r => <option key={r.analysis_id} value={r.analysis_id}>{r.repo_name} / {r.branch} · {dateFmt(r.completed_at)}</option>)}</select></div>}
            </Card>
            <Card style={{ padding: "28px 32px", display: "flex", flexDirection: "column", justifyContent: "center", gap: 12 }}>
              <div className="sp-label">Skill Score Engine</div>
              <div style={{ fontSize: 32, fontWeight: 900, color: healthTone }}>Overall Score: {fmt(skillScore)}</div>
              <div style={{ fontSize: 18, fontWeight: 800, color: healthTone }}>Score Level: {skillScoreLevel}</div>
              <ProgressBar value={skillScore} tone={healthTone} />
              <div style={{ color: "var(--text-muted)", fontSize: 12 }}>70% Sonar health + 30% security</div>
            </Card>
          </header>

          {loading && <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12 }}>{[1, 2, 3, 4].map(i => <div key={i} className="sk sp-card" style={{ height: 110 }} />)}</div>}
          {!loading && !summary?.repos.length && <EmptyState text="Analyze a repository to populate SonarQube metrics." />}

          {detail && <>
            <Card style={{ padding: "24px 28px" }}>
              <SectionTitle kicker="1. Reliability" title="Bugs & Reliability" description="Bug count, severity distribution, and affected files." right={<Badge tone={severityTone(bugSeverity.critical ? "CRITICAL" : "MINOR")}>{totalBugs} bugs</Badge>} />
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 20 }}>
                <Metric label="Reliability Rating" value={fmt(detail.reliability?.rating ?? current?.reliability_rating)} />
                <Metric label="Total Bugs" value={fmt(totalBugs)} tone={totalBugs ? danger : success} />
                <Metric label="Critical Bugs" value={bugSeverity.critical} tone={bugSeverity.critical ? danger : success} />
                <Metric label="Major Bugs" value={bugSeverity.major} tone={bugSeverity.major ? warning : success} />
                <Metric label="Minor Bugs" value={bugSeverity.minor} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, .8fr) minmax(0, 1.2fr)", gap: 20, marginBottom: 20 }}>
                <Card style={{ padding: 18, boxShadow: "none" }}><Donut items={[{ label: "Critical", value: bugSeverity.critical, tone: danger }, { label: "Major", value: bugSeverity.major, tone: warning }, { label: "Minor", value: bugSeverity.minor, tone: success }]} /></Card>
                <Card style={{ padding: 18, boxShadow: "none" }}><div style={{ display: "grid", gap: 13 }}>{[["Critical", bugSeverity.critical, danger], ["Major", bugSeverity.major, warning], ["Minor", bugSeverity.minor, success]].map(([label, value, tone]) => <div key={label as string}><div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 12 }}><span>{label}</span><strong>{value}</strong></div><ProgressBar value={value as number} max={Math.max(visibleReliabilityIssues.length, 1)} tone={tone as string} /></div>)}</div></Card>
              </div>
              {visibleReliabilityIssues.length ? <Table headers={["Severity", "File", "Line", "Message"]}>{visibleReliabilityIssues.slice(0, 10).map((i, idx) => <Row key={idx} onClick={() => setExpandedIssue(expandedIssue === i ? null : i)}><Cell><Badge tone={severityTone(i.severity)}>{i.severity}</Badge></Cell><Cell>{i.file || "n/a"}</Cell><Cell>{fmt(i.line)}</Cell><Cell>{i.message}</Cell></Row>)}</Table> : <EmptyState text="No reliability bugs returned." />}
              {expandedIssue && <Card style={{ padding: 16, marginTop: 14, boxShadow: "none", background: "var(--bg-input)" }}><strong>{expandedIssue.file || "n/a"}</strong><div style={{ color: "var(--text-muted)", marginTop: 6 }}>Line {fmt(expandedIssue.line)}</div><code style={{ display: "block", marginTop: 10, color: "var(--text-secondary)" }}>{expandedIssue.message}</code></Card>}
            </Card>

            <Card style={{ padding: "24px 28px" }}>
              <SectionTitle kicker="2. Maintainability" title="Code Smells & Technical Debt" description="Maintainability rating, smell distribution, and files with the most issues." />
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12, marginBottom: 20 }}>
                <Metric label="Maintainability Rating" value={fmt(detail.maintainability?.rating ?? current?.maintainability_rating)} />
                <Metric label="Code Smells" value={fmt(detail.maintainability?.code_smells ?? current?.code_smells)} />
                <Metric label="Technical Debt" value={minutesFmt(detail.maintainability?.technical_debt_minutes ?? current?.technical_debt_minutes)} />
                <Metric label="Debt Ratio" value={pct(detail.maintainability?.debt_ratio)} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, .8fr) minmax(0, 1.2fr)", gap: 20, marginBottom: 20 }}>
                <Card style={{ padding: 18, boxShadow: "none" }}><Donut items={[{ label: "Critical", value: smellSeverity.critical, tone: danger }, { label: "Major", value: smellSeverity.major, tone: warning }, { label: "Minor", value: smellSeverity.minor, tone: success }]} /></Card>
                <Card style={{ padding: 18, boxShadow: "none" }}><div style={{ color: "var(--text-muted)", fontSize: 12, marginBottom: 10 }}>Estimated Fix Time: {minutesFmt(detail.maintainability?.technical_debt_minutes)}</div><ProgressBar value={Math.min(detail.maintainability?.technical_debt_minutes || 0, 600)} max={600} tone={warning} /></Card>
              </div>
              <Table headers={[{ label: "File", width: "64%" }, { label: "Smells", align: "right", width: "18%" }, { label: "Debt", align: "right", width: "18%" }]}>{topFilesByIssues(maintainabilityIssues).map(([file, count]) => <Row key={file}><Cell>{file}</Cell><Cell align="right">{count}</Cell><Cell>{minutesFmt(count * 8)}</Cell></Row>)}</Table>
            </Card>

            <Card style={{ padding: "24px 28px" }}>
              <SectionTitle kicker="3. Test Coverage" title="Coverage" description="Coverage is imported from an uploaded or repository coverage.xml report." />
              {coverageAvailable ? <>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 14, marginBottom: 18 }}>
                  <Metric label="Line Coverage" value={pct(detail.coverage?.line_coverage)} />
                  <Metric label="Branch Coverage" value={pct(detail.coverage?.branch_coverage)} />
                  <Metric label="Uncovered Lines" value={fmt(detail.coverage?.uncovered_lines)} />
                </div>
                <Card style={{ padding: "22px 24px", boxShadow: "none", marginBottom: coverageSource || lowCoverage.length ? 18 : 0 }}><div style={{ fontSize: 32, fontWeight: 900, marginBottom: 12 }}>{pct(coverageValue)}</div><ProgressBar value={coverageValue} tone={scoreColor(coverageValue)} /></Card>
                {coverageSource && <div style={{ color: "var(--text-muted)", fontSize: 12, marginBottom: lowCoverage.length ? 14 : 0 }}>Coverage source: {coverageSource === "uploaded" ? "uploaded coverage.xml" : coverageSource === "repository" ? "coverage.xml found in repository" : coverageSource}</div>}
                {lowCoverage.length > 0 && <Table headers={[{ label: "File", width: "78%" }, { label: "Coverage", align: "right", width: "22%" }]}>{lowCoverage.map(f => <Row key={f.file || "file"}><Cell>{f.file}</Cell><Cell align="right"><Badge tone={scoreColor(f.coverage)}>{pct(f.coverage)}</Badge></Cell></Row>)}</Table>}
                {lowCoverage[0] && (lowCoverage[0].coverage || 0) < 60 && <div style={{ marginTop: 14, color: warning, fontWeight: 800 }}>⚠ {lowCoverage[0].file} has low coverage ({pct(lowCoverage[0].coverage)})</div>}
              </> : <Card style={{ padding: 18, boxShadow: "none", background: "var(--bg-input)", borderStyle: "dashed" }}>
                <div style={{ fontSize: 24, fontWeight: 900, marginBottom: 8 }}>Coverage unavailable</div>
                <div style={{ color: "var(--text-muted)", lineHeight: 1.6 }}>{coverageUnavailableMessage}</div>
                <div style={{ marginTop: 10 }}><Badge tone={warning}>{coverageReason}</Badge></div>
              </Card>}
            </Card>

            <Card style={{ padding: "24px 28px" }}>
              <SectionTitle kicker="4. Duplication" title="Duplicated Code" description="Duplicated lines, blocks, and files." />
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 14, marginBottom: 18 }}>
                <Metric label="Duplicated Lines" value={fmt(detail.duplication?.duplicated_lines)} />
                <Metric label="Duplicated Blocks" value={fmt(detail.duplication?.duplicated_blocks)} />
                <Metric label="Duplicated Files" value={fmt(detail.duplication?.duplicated_files)} />
              </div>
              <Card style={{ padding: "22px 24px", boxShadow: "none", marginBottom: duplicatedFiles.length ? 18 : 0 }}><div style={{ fontSize: 28, fontWeight: 900, marginBottom: 12 }}>{pct(detail.duplication?.percentage ?? current?.duplication_percentage)}</div><ProgressBar value={detail.duplication?.percentage ?? current?.duplication_percentage} tone={(detail.duplication?.percentage || 0) > 10 ? danger : warning} /></Card>
              {duplicatedFiles.length > 0 && <Table headers={[{ label: "File", width: "58%" }, { label: "Duplication %", align: "right", width: "21%" }, { label: "Duplicated Lines", align: "right", width: "21%" }]}>{duplicatedFiles.map(f => <Row key={f.file || "file"}><Cell>{f.file}</Cell><Cell align="right">{pct(f.duplication)}</Cell><Cell align="right">{fmt(f.duplicated_lines)}</Cell></Row>)}</Table>}
            </Card>

            <Card style={{ padding: "24px 28px" }}>
              <SectionTitle kicker="5. Complexity" title="Code Complexity" description="Cyclomatic and cognitive complexity across files and functions." />
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14, marginBottom: showComplexityTables ? 18 : 0 }}>
                <Metric label="Cyclomatic Complexity" value={fmt(detail.complexity?.cyclomatic_complexity)} />
                <Metric label="Cognitive Complexity" value={fmt(detail.complexity?.cognitive_complexity ?? current?.cognitive_complexity)} />
              </div>
              {showComplexityTables && <div style={{ display: "grid", gridTemplateColumns: complexityGridColumns, gap: 18 }}>
                {complexFiles.length > 0 && <Table headers={[{ label: "File", width: "46%" }, { label: "Cyclomatic Complexity", align: "right", width: "22%" }, { label: "Cognitive Complexity", align: "right", width: "22%" }, { label: "Functions", align: "right", width: "10%" }]}>{complexFiles.map(f => <Row key={f.file || "file"}><Cell>{f.file}</Cell><Cell align="right">{fmt(f.complexity)}</Cell><Cell align="right">{fmt(f.cognitive_complexity)}</Cell><Cell align="right">{fmt(f.functions)}</Cell></Row>)}</Table>}
                {complexFunctions.length > 0 && <Table headers={[{ label: "Function", width: "72%" }, { label: "Complexity", align: "right", width: "28%" }]}>{complexFunctions.map(fn => <Row key={`${fn.file}-${fn.function}`}><Cell>{fn.function}()<div style={{ fontSize: 11, color: "var(--text-muted)" }}>{fn.file}</div></Cell><Cell align="right">{fmt(fn.complexity)}</Cell></Row>)}</Table>}
              </div>}
            </Card>

            <Card style={{ padding: "24px 28px" }}>
              <SectionTitle kicker="6. Project Size" title="Repository Size" description="High-level size metrics collected from SonarQube." />
              <Table headers={[{ label: "Metric", width: "70%" }, { label: "Value", align: "right", width: "30%" }]}>{[
                ["Lines of Code", detail.project_size?.lines_of_code],
                ["Files", detail.project_size?.files],
                ["Functions", detail.project_size?.functions],
                ["Classes", detail.project_size?.classes],
                ["Statements", detail.project_size?.statements],
              ].map(([label, value]) => <Row key={label as string}><Cell>{label}</Cell><Cell align="right">{fmt(value as number | null | undefined)}</Cell></Row>)}</Table>
            </Card>

            <Card style={{ padding: "24px 28px" }}>
              <SectionTitle kicker="7. Issues Explorer" title="Search Issues" description="Filter SonarQube BUG and CODE_SMELL issues by type or file." right={<Badge>{filteredIssues.length} shown</Badge>} />
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 16 }}>
                {[["ALL", "All"], ["BUG", "Bugs"], ["CODE_SMELL", "Code Smells"], ["RELIABILITY", "Reliability"]].map(([key, label]) => <button key={key} className={`filter-btn ${filter === key ? "active" : ""}`} onClick={() => setFilter(key as typeof filter)}>{label}</button>)}
                <input className="sp-search" placeholder="🔍 Search file..." value={query} onChange={(e) => setQuery(e.target.value)} style={{ marginLeft: "auto", minWidth: 240 }} />
              </div>
              {filteredIssues.length ? <Table headers={[{ label: "Type", width: "18%" }, { label: "Severity", width: "18%" }, { label: "File", width: "50%" }, { label: "Line", align: "right", width: "14%" }]}>{filteredIssues.slice(0, 50).map((i, idx) => <Row key={idx} onClick={() => setSelectedIssue(i)}><Cell><Badge tone={i.type === "BUG" ? danger : accent}>{issueTypeLabel(i.type)}</Badge></Cell><Cell><Badge tone={severityTone(i.severity)}>{i.severity}</Badge></Cell><Cell>{i.file || "n/a"}</Cell><Cell align="right">{fmt(i.line)}</Cell></Row>)}</Table> : <EmptyState text="No issues match the current filters." />}
            </Card>

            <Card style={{ padding: "24px 28px" }}>
              <SectionTitle kicker="8. Analysis Summary" title="Repository Summary" description="Important quality signals and recommended next actions." />
              <div style={{ display: "grid", gap: 9, fontSize: 14, marginBottom: 18 }}>
                <div>Overall Score {fmt(skillScore)} - {skillScoreLevel}</div>
                <div>✅ Maintainability Rating {fmt(detail.maintainability?.rating ?? current?.maintainability_rating)}</div>
                <div>{bugSeverity.critical || bugSeverity.major ? "⚠" : "✅"} Reliability Rating {fmt(detail.reliability?.rating ?? current?.reliability_rating)}</div>
                <div>{!coverageAvailable ? `ℹ Coverage unavailable: ${coverageReason}` : (coverageValue || 0) < 80 ? "⚠ Coverage below target" : "✅ Coverage looks healthy"}</div>
                <div>{(detail.duplication?.percentage || 0) > 5 ? "⚠ Duplication higher than recommended" : "✅ Duplication is under control"}</div>
              </div>
              <div className="sp-label" style={{ marginBottom: 10 }}>Recommendations</div>
              <ul style={{ margin: 0, paddingLeft: 18, color: "var(--text-secondary)", lineHeight: 1.8 }}>{recommendations.map(item => <li key={item}>{item}</li>)}</ul>
            </Card>
          </>}
        </div>
      </div>

      {selectedIssue && <div onClick={() => setSelectedIssue(null)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.35)", zIndex: 200, display: "flex", justifyContent: "flex-end" }}>
        <aside onClick={(e) => e.stopPropagation()} style={{ width: "min(420px, 92vw)", height: "100%", background: "var(--bg-base)", borderLeft: "1px solid var(--border)", padding: 24, boxShadow: "var(--shadow-card)", overflowY: "auto" }}>
          <button onClick={() => setSelectedIssue(null)} style={{ float: "right", border: "1px solid var(--border)", background: "var(--bg-input)", color: "var(--text-primary)", borderRadius: 8, padding: "6px 10px", cursor: "pointer" }}>Close</button>
          <div className="sp-label">Issue</div>
          <h2 style={{ fontFamily: "'Inter',sans-serif", margin: "8px 0 16px" }}>{selectedIssue.message}</h2>
          <div style={{ display: "grid", gap: 14, color: "var(--text-secondary)", fontSize: 14 }}>
            <div><strong style={{ color: "var(--text-primary)" }}>Type:</strong><br />{issueTypeLabel(selectedIssue.type)}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Severity:</strong><br />{selectedIssue.severity}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>File:</strong><br />{selectedIssue.file || "n/a"}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Line:</strong><br />{fmt(selectedIssue.line)}</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Estimated Fix:</strong><br />Review the affected code, split complex logic into smaller functions, and add tests before rerunning analysis.</div>
          </div>
        </aside>
      </div>}
    </DashboardLayout>
  );
}
