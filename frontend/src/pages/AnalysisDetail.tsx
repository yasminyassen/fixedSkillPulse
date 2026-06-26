import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api from "../api/auth";
import DashboardLayout from "./DashboardLayout";

// ─── Types ───────────────────────────────────────────────────────────────────

interface AnalysisResult {
  analysis_run_id?: number;
  repo?: string;
  branch?: string;
  status: string;
  candidate_name?: string | null;
  github_login?: string | null;
  github_avatar_url?: string | null;
  security_score?: number | null;
  security_assessment?: {
    score: number | null;
    status: string;
    risk_level: string;
    findings_count: number;
    breakdown?: {
      critical?: number;
      high?: number;
      medium?: number;
      low?: number;
    };
  };
  completed_at?: string | null;
  error_reason?: string;
  message?: string;
}

interface SonarIssue {
  type: "BUG" | "CODE_SMELL" | string;
  severity: string;
  file: string | null;
  line: number | null;
  message: string;
}

interface SonarDashboard {
  repository: { name: string; full_name: string; branch: string; analysis_date: string | null };
  overall: {
    skill_score: number | null;
    skill_score_level: string;
    sonar_health_score: number | null;
    sonar_state: string;
    quality_gate: { status?: string; conditions?: Array<{ metricKey?: string; comparator?: string; errorThreshold?: string; actualValue?: string; status?: string }> };
  };
  reliability: { rating: string | null; total_bugs: number; issues: SonarIssue[] };
  maintainability: { rating: string | null; code_smells: number; technical_debt_minutes: number; debt_ratio: number; issues: SonarIssue[] };
  coverage: { coverage: number; line_coverage: number; branch_coverage: number; uncovered_lines: number };
  duplication: { percentage: number; duplicated_lines: number; duplicated_blocks: number; duplicated_files: number };
  complexity: { cyclomatic_complexity: number; cognitive_complexity: number };
  project_size: { lines_of_code: number; files: number; functions: number; classes: number };
  issues_explorer: SonarIssue[];
  analysis_summary: { source: string; project_key: string | null; metrics_count: number; issues_count: number };
}

type InsightRec = "strong_hire" | "interview" | "review_required" | "reject";
type InsightRisk = "low" | "medium" | "high" | "critical";
type InsightSrc = "llm" | "fallback" | "summary";

interface CandidateInsight {
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
  recommendation: InsightRec;
  recommendation_reason: string;
  risk_level: InsightRisk;
  generated_by: InsightSrc;
  generated_at?: string | null;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const REC_LABEL: Record<InsightRec, string> = { strong_hire: "Strong Hire", interview: "Interview", review_required: "Review Required", reject: "Reject" };
const REC_COLOR: Record<InsightRec, string> = { strong_hire: "#34d399", interview: "#818cf8", review_required: "#fbbf24", reject: "#f87171" };
const RISK_COLOR: Record<InsightRisk, string> = { low: "#34d399", medium: "#fbbf24", high: "#fb923c", critical: "#f87171" };
const RISK_BG: Record<InsightRisk, string> = { low: "rgba(52,211,153,.12)", medium: "rgba(251,191,36,.12)", high: "rgba(251,146,60,.12)", critical: "rgba(248,113,113,.12)" };
const SRC_LABEL: Record<InsightSrc, string> = { llm: "AI Generated", fallback: "Fallback", summary: "Summary" };

// ─── Formatters ───────────────────────────────────────────────────────────────

const fmtNum = (v: number | null | undefined) => v === null || v === undefined ? "n/a" : new Intl.NumberFormat().format(v);
const fmtPct = (v: number | null | undefined) => v === null || v === undefined ? "n/a" : `${Number(v).toFixed(1)}%`;
const fmtMin = (v: number | null | undefined) => { if (v === null || v === undefined) return "n/a"; if (v < 60) return `${fmtNum(v)} min`; return `${Math.round(v / 60)} h`; };
const fmtRating = (v: string | null | undefined) => { if (!v) return "n/a"; const r: Record<string, string> = { "1": "A", "2": "B", "3": "C", "4": "D", "5": "E" }; const n = String(Number(v)); return r[n] ? `${r[n]} (${v})` : v; };
const fmtDate = (v: string | null | undefined) => { if (!v) return "n/a"; return new Date(v).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }); };
const getInitials = (name: string) => name.split(/\s+/).filter(Boolean).map(p => p[0]).join("").toUpperCase().slice(0, 2) || "?";
const scoreTone = (s: number | null) => s === null ? "#94a3b8" : s >= 80 ? "#34d399" : s >= 60 ? "#fbbf24" : "#f87171";

function CandidateAvatar({ src, name, size = 72 }: { src?: string | null; name: string; size?: number }) {
  return src ? (
    <>
      <img
        className="sp-candidate-avatar"
        src={src}
        alt={`${name} GitHub avatar`}
        style={{ width: size, height: size }}
        onError={(event) => {
          event.currentTarget.style.display = "none";
          const fallback = event.currentTarget.nextElementSibling as HTMLElement | null;
          if (fallback) fallback.style.display = "flex";
        }}
      />
      <div className="sp-candidate-avatar placeholder" style={{ width: size, height: size, display: "none" }}>{getInitials(name)}</div>
    </>
  ) : (
    <div className="sp-candidate-avatar placeholder" style={{ width: size, height: size }}>{getInitials(name)}</div>
  );
}

// ─── SVG Icons ────────────────────────────────────────────────────────────────

const I = {
  back:       <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="15 18 9 12 15 6"/></svg>,
  brain:      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.46 2.5 2.5 0 0 1-1.96-3 2.5 2.5 0 0 1 .3-4.92A2.5 2.5 0 0 1 9.5 2Z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 1.96-3 2.5 2.5 0 0 0-.3-4.92A2.5 2.5 0 0 0 14.5 2Z"/></svg>,
  gauge:      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2a10 10 0 0 1 7.38 16.75"/><path d="M5 19.5A9.96 9.96 0 0 1 2 12"/><path d="m12 12-4-4"/><circle cx="12" cy="12" r="2"/></svg>,
  shield:     <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>,
  bug:        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect width="8" height="14" x="8" y="6" rx="4"/><path d="m19 7-3 2M5 7l3 2M19 19l-3-2M5 19l3-2M20 13h-4M4 13h4M10 4l1 2M14 4l-1 2"/></svg>,
  wrench:     <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>,
  umbrella:   <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M23 12a11.05 11.05 0 0 0-22 0zm-5 7a3 3 0 0 1-6 0v-7"/></svg>,
  copy2:      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect width="13" height="13" x="9" y="9" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>,
  git:        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M6 21V9a9 9 0 0 0 9 9"/></svg>,
  layers:     <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>,
  code:       <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>,
  list:       <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>,
  spin:       <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 1 1-6.22-8.56"/></svg>,
  alert:      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>,
  star:       <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>,
  sparkle:    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>,
};

// ─── Small UI pieces ──────────────────────────────────────────────────────────

function Eyebrow({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".04em", color: "#a78bfa" }}>
      <span style={{ color: "#a78bfa", display: "inline-flex" }}>{icon}</span>
      {children}
    </span>
  );
}

function SectionCard({ title, eyebrow, icon, children, delay = 0 }: { title: string; eyebrow?: string; icon: ReactNode; children: ReactNode; delay?: number }) {
  return (
    <section className="ad-card fade-up" style={{ animationDelay: `${delay}ms` }}>
      <div className="ad-card-header">
        <Eyebrow icon={icon}>{eyebrow || title}</Eyebrow>
        <h2 className="ad-card-title">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function MetricTile({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <div className="ad-tile">
      <span className="ad-tile-label">{label}</span>
      <span className="ad-tile-value" style={{ color: tone }}>{value}</span>
    </div>
  );
}

function MetricGrid({ items }: { items: Array<{ label: string; value: string | number; tone?: string }> }) {
  return (
    <div className="ad-metric-grid">
      {items.map(item => <MetricTile key={item.label} label={item.label} value={item.value} tone={item.tone} />)}
    </div>
  );
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="ad-empty-state">
      <div className="ad-empty-icon">{I.alert}</div>
      <h2 className="ad-empty-title">{title}</h2>
      <p className="ad-empty-detail">{detail}</p>
    </div>
  );
}

function IssuesExplorer({ issues }: { issues: SonarIssue[] }) {
  if (!issues.length) return <p style={{ margin: 0, color: "rgba(148,163,184,.7)", fontSize: 13 }}>No issues returned by SonarQube.</p>;
  return (
    <div className="ad-table-wrap">
      <table className="ad-table">
        <thead><tr><th>Type</th><th>Severity</th><th>File</th><th style={{ textAlign: "right" }}>Line</th><th>Message</th></tr></thead>
        <tbody>
          {issues.map((issue, i) => (
            <tr key={`${issue.type}-${issue.file}-${issue.line}-${i}`}>
              <td><span className={`ad-chip ${issue.type === "BUG" ? "chip-bug" : "chip-smell"}`}>{issue.type}</span></td>
              <td><span className="ad-chip chip-severity">{issue.severity}</span></td>
              <td style={{ maxWidth: 260, overflowWrap: "anywhere", color: "rgba(148,163,184,.7)", fontSize: 12 }}>{issue.file || "n/a"}</td>
              <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>{issue.line || "n/a"}</td>
              <td style={{ minWidth: 280 }}>{issue.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── AI Insights panel ────────────────────────────────────────────────────────

function AiInsightsContent({ insight, loading, error, skillScore, candidateName, githubLogin, candidateAvatarUrl }: {
  insight: CandidateInsight | null; loading: boolean; error: string; skillScore: number | null; candidateName: string; githubLogin?: string | null; candidateAvatarUrl?: string | null;
}) {
  const score = insight?.skill_score ?? skillScore ?? null;
  const deg = Math.max(0, Math.min(100, score ?? 0)) * 3.6;
  const displayName = insight?.candidate_name || candidateName;
  const displayLogin = insight?.github_login || githubLogin;
  const avatarUrl = insight?.github_avatar_url || candidateAvatarUrl;

  if (loading) return (
    <div style={{ display: "grid", gap: 12 }}>
      {[48, 18, 110, 13, 13, 13].map((h, i) => (
        <div key={i} className="ad-skeleton" style={{ height: h, width: i === 1 ? "55%" : "100%", borderRadius: i === 2 ? "50%" : 8, margin: i === 2 ? "8px auto" : undefined }} />
      ))}
    </div>
  );

  if (error && !insight) return (
    <div className="ai-layout">
      <div className="ai-left">
        <div className="ai-identity">
          <div className="ai-avatar-wrap"><CandidateAvatar src={avatarUrl} name={displayName} size={72} /></div>
          <div>
            <div className="ai-name">{displayName}</div>
            {displayLogin && <div className="ai-github">@{displayLogin}</div>}
          </div>
        </div>
      </div>
      <p style={{ color: "#f87171", fontSize: 13, margin: 0 }}>{error}</p>
    </div>
  );
  if (!insight) return <p style={{ color: "var(--sp-text-muted)", fontSize: 13, margin: 0 }}>No AI insight available for this candidate.</p>;

  return (
    <div className="ai-layout">
      {/* Left: identity + score ring */}
      <div className="ai-left">
        <div className="ai-identity">
          <div className="ai-avatar-wrap">
            <CandidateAvatar src={avatarUrl} name={displayName} size={72} />
          </div>
          <div>
            <div className="ai-name">{displayName}</div>
            {displayLogin && <div className="ai-github">@{displayLogin}</div>}
            {insight.task_title && <span className="ai-task-chip">{insight.task_title}</span>}
          </div>
        </div>

        <div className="ai-score-ring" style={{ background: `conic-gradient(${scoreTone(score)} ${deg}deg, rgba(148,163,184,.1) 0deg)` }}>
          <div className="ai-score-inner">
            <strong>{score !== null ? score.toFixed(1) : "—"}</strong>
            <span>Skill Score</span>
          </div>
        </div>

        <div className="ai-badges">
          <span className="ai-badge" style={{ color: REC_COLOR[insight.recommendation], background: `${REC_COLOR[insight.recommendation]}18`, borderColor: `${REC_COLOR[insight.recommendation]}35` }}>
            {I.star} {REC_LABEL[insight.recommendation]}
          </span>
          <span className="ai-badge" style={{ color: RISK_COLOR[insight.risk_level], background: RISK_BG[insight.risk_level], borderColor: `${RISK_COLOR[insight.risk_level]}35` }}>
            {insight.risk_level.charAt(0).toUpperCase() + insight.risk_level.slice(1)} Risk
          </span>
          <span className="ai-badge" style={{ color: "#a78bfa", background: "rgba(167,139,250,.1)", borderColor: "rgba(167,139,250,.25)" }}>
            {I.sparkle} {SRC_LABEL[insight.generated_by]}
          </span>
        </div>
      </div>

      {/* Right: summary + lists + reason */}
      <div className="ai-right">
        <p className="ai-summary">{insight.summary}</p>

        {insight.strengths?.length > 0 && (
          <div className="ai-list-block">
            <span className="ai-list-label">Strengths</span>
            <ul className="ai-list">
              {insight.strengths.map((item, i) => (
                <li key={i}><span className="ai-dot" style={{ background: "#34d399" }} />{item}</li>
              ))}
            </ul>
          </div>
        )}

        {insight.areas_to_improve?.length > 0 && (
          <div className="ai-list-block">
            <span className="ai-list-label">Areas to improve</span>
            <ul className="ai-list">
              {insight.areas_to_improve.map((item, i) => (
                <li key={i}><span className="ai-dot" style={{ background: "#fb923c" }} />{item}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="ai-reason-box">
          <span className="ai-list-label">Recommendation reason</span>
          <p>{insight.recommendation_reason}</p>
        </div>
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function AnalysisDetail() {
  const { analysisId } = useParams<{ analysisId: string }>();
  const navigate = useNavigate();

  const [result, setResult]             = useState<AnalysisResult | null>(null);
  const [sonar, setSonar]               = useState<SonarDashboard | null>(null);
  const [insight, setInsight]           = useState<CandidateInsight | null>(null);
  const [loading, setLoading]           = useState(true);
  const [sonarLoading, setSonarLoading] = useState(false);
  const [insightLoading, setInsightLoading] = useState(false);
  const [notFound, setNotFound]         = useState(false);
  const [polling, setPolling]           = useState(false);
  const [sonarError, setSonarError]     = useState("");
  const [insightError, setInsightError] = useState("");

  const fetchSonarDashboard = async () => {
    if (!analysisId) return;
    setSonarLoading(true); setSonarError("");
    try { const r = await api.get(`/analysis/${analysisId}/sonar-dashboard`); setSonar(r.data); }
    catch (e: any) { setSonar(null); setSonarError(e?.response?.data?.detail || "SonarQube data unavailable."); }
    finally { setSonarLoading(false); }
  };

  const fetchInsight = async () => {
    if (!analysisId) return;
    setInsightLoading(true); setInsightError("");
    try { const r = await api.get(`/analysis/recruiter/candidate-insights/${analysisId}`); setInsight(r.data); }
    catch (e: any) { setInsightError(e?.response?.data?.detail || "Unable to load AI insight."); }
    finally { setInsightLoading(false); }
  };

  useEffect(() => {
    if (!analysisId) { setNotFound(true); setLoading(false); return; }
    (async () => {
      try {
        const r = await api.get(`/analysis/${analysisId}`);
        const data: AnalysisResult = r.data;
        if (data.status === "pending" && !data.analysis_run_id) { setNotFound(true); setLoading(false); return; }
        setResult(data);
        setPolling(data.status === "running" || data.status === "pending");
        setLoading(false);
        if (data.status === "completed") { await fetchSonarDashboard(); await fetchInsight(); }
      } catch (e: any) {
        if (e.response?.status === 401) { localStorage.clear(); window.location.href = "/login"; return; }
        setNotFound(true); setLoading(false);
      }
    })();
  }, [analysisId]);

  useEffect(() => {
    if (!polling || !analysisId) return;
    const iv = window.setInterval(async () => {
      try {
        const r = await api.get(`/analysis/${analysisId}`);
        const data: AnalysisResult = r.data;
        setResult(data);
        if (data.status === "completed" || data.status === "failed") {
          setPolling(false); window.clearInterval(iv);
          if (data.status === "completed") { await fetchSonarDashboard(); await fetchInsight(); }
        }
      } catch { window.clearInterval(iv); }
    }, 3000);
    return () => window.clearInterval(iv);
  }, [polling, analysisId]);

  const repoName      = sonar?.repository.name ?? result?.repo?.split("/").pop() ?? "Repository";
  const repoFullName  = sonar?.repository.full_name ?? result?.repo ?? "";
  const branch        = sonar?.repository.branch ?? result?.branch ?? "main";
  const skillScore    = sonar?.overall.skill_score ?? null;
  const skillLevel    = sonar?.overall.skill_score_level ?? "—";
  const candidateName = insight?.candidate_name || result?.candidate_name || sonar?.repository.name || repoName;
  const githubLogin = insight?.github_login || result?.github_login;
  const candidateAvatarUrl = insight?.github_avatar_url || result?.github_avatar_url;
  const security = result?.security_assessment;

  return (
    <DashboardLayout>
      <style>{PAGE_CSS}</style>
      <div className="ad-page">

        {/* ── Top nav bar ── */}
        <div className="ad-topbar">
          <button className="ad-back-btn" onClick={() => navigate("/dashboard/recruiter/candidates")} title="Back to candidate evaluation">
            {I.back}
          </button>
          <div className="ad-topbar-info">
            <h1 className="ad-topbar-title">
              {loading ? "Loading…" : notFound ? "Not Found" : repoName}
            </h1>
            {!notFound && !loading && (
              <p className="ad-topbar-sub">{repoFullName} / {branch}</p>
            )}
          </div>
        </div>

        {/* ── Loading skeletons ── */}
        {loading && (
          <div style={{ display: "grid", gap: 14 }}>
            {[0, 1, 2].map(i => <div key={i} className="ad-skeleton" style={{ height: 120, borderRadius: 12, opacity: 0.6 + i * 0.1 }} />)}
          </div>
        )}

        {/* ── States ── */}
        {!loading && notFound && <EmptyState title="Analysis Not Found" detail="This analysis does not exist or you don't have permission to view it." />}

        {!loading && !notFound && result && (result.status === "running" || result.status === "pending") && (
          <div className="ad-empty-state">
            <div className="ad-spin-icon"><span className="ad-spin">{I.spin}</span></div>
            <h2 className="ad-empty-title">Analysis in Progress</h2>
            <p className="ad-empty-detail">SonarQube data will appear here once the run completes.</p>
          </div>
        )}

        {!loading && !notFound && result?.status === "failed" && (
          <EmptyState title="Analysis Failed" detail={result.message || "Something went wrong while analyzing this repository."} />
        )}

        {!loading && !notFound && result?.status === "completed" && sonarLoading && (
          <div className="ad-empty-state"><p style={{ color: "rgba(148,163,184,.7)", fontSize: 14 }}>Loading dashboard…</p></div>
        )}

        {!loading && !notFound && result?.status === "completed" && !sonarLoading && sonarError && (
          <EmptyState title="SonarQube Unavailable" detail={sonarError} />
        )}

        {/* ── Main content ── */}
        {!loading && !notFound && result?.status === "completed" && sonar && (
          <div className="ad-content">

            {/* Hero */}
            <div className="ad-hero fade-up">
              <div className="ad-hero-left">
                <div className="ad-hero-eyebrow">
                  <span className="ad-level-pill">{skillLevel}</span>
                  <span className="ad-hero-sub">Skill Score Engine</span>
                </div>
                <h2 className="ad-hero-title">{sonar.repository.name}</h2>
                <div className="ad-hero-meta">
                  <span>Repository: <strong>{sonar.repository.full_name}</strong></span>
                  <span>Branch: <strong>{sonar.repository.branch}</strong></span>
                  <span>Analyzed: <strong>{fmtDate(sonar.repository.analysis_date)}</strong></span>
                </div>
              </div>
              <div className="ad-hero-stats">
                <div className="ad-hero-stat">
                  <span className="ad-hero-stat-val" style={{ color: scoreTone(skillScore) }}>{skillScore ?? "—"}</span>
                  <span className="ad-hero-stat-lbl">Overall Score</span>
                </div>
                <div className="ad-hero-stat">
                  <span className="ad-hero-stat-val">{skillLevel}</span>
                  <span className="ad-hero-stat-lbl">Score Level</span>
                </div>
                <div className="ad-hero-stat">
                  <span className="ad-hero-stat-val">{fmtNum(sonar.analysis_summary.issues_count)}</span>
                  <span className="ad-hero-stat-lbl">Issues</span>
                </div>
              </div>
            </div>

            {/* Candidate Information */}
            <SectionCard title="Candidate Information" eyebrow="AI Candidate Insights" icon={I.brain} delay={40}>
              <AiInsightsContent
                insight={insight}
                loading={insightLoading}
                error={insightError}
                skillScore={skillScore}
                candidateName={candidateName}
                githubLogin={githubLogin}
                candidateAvatarUrl={candidateAvatarUrl}
              />
            </SectionCard>

            {/* Security Assessment */}
            <SectionCard title="Security Assessment" eyebrow="Repository security" icon={I.shield} delay={80}>
              <MetricGrid items={[
                { label: "Security Score", value: security?.score !== null && security?.score !== undefined ? fmtPct(security.score) : "n/a", tone: scoreTone(security?.score ?? null) },
                { label: "Security Status", value: security?.status || "Unavailable" },
                { label: "Risk Level", value: security?.risk_level || "Unavailable", tone: (security?.risk_level || "").toLowerCase() === "critical" ? "#f87171" : (security?.risk_level || "").toLowerCase() === "high" ? "#fb923c" : (security?.risk_level || "").toLowerCase() === "medium" ? "#fbbf24" : "#34d399" },
                { label: "Critical Findings", value: fmtNum(security?.breakdown?.critical ?? 0), tone: (security?.breakdown?.critical ?? 0) > 0 ? "#f87171" : "#34d399" },
                { label: "High Findings", value: fmtNum(security?.breakdown?.high ?? 0), tone: (security?.breakdown?.high ?? 0) > 0 ? "#fb923c" : "#34d399" },
                { label: "Medium Findings", value: fmtNum(security?.breakdown?.medium ?? 0), tone: (security?.breakdown?.medium ?? 0) > 0 ? "#fbbf24" : "#34d399" },
                { label: "Low Findings", value: fmtNum(security?.breakdown?.low ?? 0) },
              ]} />
            </SectionCard>

            {/* Skill Score */}
            <SectionCard title="Skill Score Engine" eyebrow="Overall performance" icon={I.gauge} delay={120}>
              <MetricGrid items={[
                { label: "Overall Score", value: skillScore ?? "n/a", tone: scoreTone(skillScore) },
                { label: "Score Level", value: skillLevel },
                { label: "Sonar Health Score", value: sonar.overall.sonar_health_score ?? "n/a", tone: scoreTone(sonar.overall.sonar_health_score) },
              ]} />
            </SectionCard>

            {/* Reliability */}
            <SectionCard title="Reliability" eyebrow="Bug analysis" icon={I.bug} delay={120}>
              <MetricGrid items={[
                { label: "Reliability Rating", value: fmtRating(sonar.reliability.rating) },
                { label: "Bugs", value: fmtNum(sonar.reliability.total_bugs), tone: sonar.reliability.total_bugs > 0 ? "#f87171" : "#34d399" },
                { label: "Bug Issues", value: fmtNum(sonar.reliability.issues.length) },
              ]} />
            </SectionCard>

            {/* Maintainability */}
            <SectionCard title="Maintainability" eyebrow="Code health" icon={I.wrench} delay={160}>
              <MetricGrid items={[
                { label: "Rating", value: fmtRating(sonar.maintainability.rating) },
                { label: "Code Smells", value: fmtNum(sonar.maintainability.code_smells), tone: sonar.maintainability.code_smells > 0 ? "#fbbf24" : "#34d399" },
                { label: "Technical Debt", value: fmtMin(sonar.maintainability.technical_debt_minutes) },
                { label: "Debt Ratio", value: fmtPct(sonar.maintainability.debt_ratio) },
              ]} />
            </SectionCard>

            {/* Coverage */}
            <SectionCard title="Coverage" eyebrow="Test coverage" icon={I.umbrella} delay={200}>
              <MetricGrid items={[
                { label: "Overall Coverage", value: fmtPct(sonar.coverage.coverage), tone: sonar.coverage.coverage >= 80 ? "#34d399" : sonar.coverage.coverage >= 50 ? "#fbbf24" : "#f87171" },
                { label: "Line Coverage", value: fmtPct(sonar.coverage.line_coverage) },
                { label: "Branch Coverage", value: fmtPct(sonar.coverage.branch_coverage) },
                { label: "Uncovered Lines", value: fmtNum(sonar.coverage.uncovered_lines) },
              ]} />
            </SectionCard>

            {/* Duplication */}
            <SectionCard title="Duplication" eyebrow="Code duplication" icon={I.copy2} delay={240}>
              <MetricGrid items={[
                { label: "Duplications", value: fmtPct(sonar.duplication.percentage), tone: sonar.duplication.percentage > 10 ? "#f87171" : "#34d399" },
                { label: "Duplicated Lines", value: fmtNum(sonar.duplication.duplicated_lines) },
                { label: "Duplicated Blocks", value: fmtNum(sonar.duplication.duplicated_blocks) },
                { label: "Duplicated Files", value: fmtNum(sonar.duplication.duplicated_files) },
              ]} />
            </SectionCard>

            {/* Complexity */}
            <SectionCard title="Complexity" eyebrow="Code complexity" icon={I.git} delay={280}>
              <MetricGrid items={[
                { label: "Cyclomatic Complexity", value: fmtNum(sonar.complexity.cyclomatic_complexity) },
                { label: "Cognitive Complexity", value: fmtNum(sonar.complexity.cognitive_complexity) },
              ]} />
            </SectionCard>

            {/* Project Size */}
            <SectionCard title="Project Size" eyebrow="Codebase metrics" icon={I.layers} delay={320}>
              <MetricGrid items={[
                { label: "Lines of Code", value: fmtNum(sonar.project_size.lines_of_code) },
                { label: "Files", value: fmtNum(sonar.project_size.files) },
                { label: "Functions", value: fmtNum(sonar.project_size.functions) },
                { label: "Classes", value: fmtNum(sonar.project_size.classes) },
              ]} />
            </SectionCard>

            {/* Issues Explorer */}
            <SectionCard title="Issues Explorer" eyebrow="Detailed findings" icon={I.list} delay={360}>
              <IssuesExplorer issues={sonar.issues_explorer} />
            </SectionCard>

          </div>
        )}
      </div>
    </DashboardLayout>
  );
}

// ─── CSS ──────────────────────────────────────────────────────────────────────

const PAGE_CSS = `
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

@keyframes fadeUp  { from { opacity:0; transform:translateY(16px) } to { opacity:1; transform:translateY(0) } }
@keyframes rdSpin  { to { transform:rotate(360deg) } }
@keyframes shimmer { to { background-position:-220% 0 } }

.fade-up { opacity:0; animation: fadeUp .5s cubic-bezier(.22,1,.36,1) forwards; }
.ad-spin  { display:inline-flex; animation: rdSpin 1.2s linear infinite; color:#a78bfa; }

/* Page shell */
.ad-page {
  min-height: 100vh;
  width: 100%;
  padding: 28px 32px 64px;
  font-family: var(--font-body);
  color: var(--sp-text);
  background: var(--sp-bg-gradient);
  box-sizing: border-box;
}

.ad-content {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* Top bar */
.ad-topbar {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 26px;
}
.ad-back-btn {
  width: 38px; height: 38px;
  border-radius: 8px;
  border: 1px solid var(--sp-border);
  background: var(--sp-surface);
  backdrop-filter: blur(12px);
  display: flex; align-items: center; justify-content: center;
  color: var(--sp-text-muted);
  cursor: pointer;
  flex-shrink: 0;
  transition: all .15s;
}
.ad-back-btn:hover { background: var(--sp-surface-hover); border-color: rgba(167,139,250,.4); color:#8b5cf6; }
.ad-topbar-title {
  font-family: var(--font-heading);
  font-size: clamp(20px,3vw,28px);
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--sp-text);
  margin: 0;
  line-height: 1.1;
}
.ad-topbar-sub { font-size: 12px; color: var(--sp-text-faint); margin: 3px 0 0; }

/* Cards */
.ad-card {
  padding: 24px 26px;
  border-radius: 12px;
  background: var(--sp-surface);
  border: 1px solid var(--sp-border);
  backdrop-filter: blur(18px);
  box-shadow: var(--sp-shadow);
}
.ad-card-header { margin-bottom: 20px; }
.ad-card-title {
  font-family: var(--font-heading);
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--sp-text);
  margin: 6px 0 0;
}

/* Hero */
.ad-hero {
  padding: 26px 28px;
  border-radius: 12px;
  background: var(--sp-surface);
  border: 1px solid var(--sp-border);
  backdrop-filter: blur(18px);
  box-shadow: var(--sp-shadow);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  flex-wrap: wrap;
}
.ad-hero-eyebrow { display:flex; align-items:center; gap:10px; margin-bottom:10px; }
.ad-level-pill {
  display: inline-flex; align-items: center;
  padding: 4px 10px; border-radius: 999px;
  background: rgba(139,92,246,.15); border: 1px solid rgba(139,92,246,.3);
  color: #a78bfa; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing:.04em;
}
.ad-hero-sub { font-size:11px; color:var(--sp-text-faint); font-weight:700; text-transform:uppercase; letter-spacing:.04em; }
.ad-hero-title { font-family:var(--font-heading); font-size:22px; font-weight:700; letter-spacing:-0.02em; color:var(--sp-text); margin:0 0 10px; }
.ad-hero-meta { display:flex; flex-wrap:wrap; gap:6px 20px; font-size:12px; color:var(--sp-text-faint); }
.ad-hero-meta strong { color:var(--sp-text-muted); }
.ad-hero-stats { display:flex; gap:10px; flex-wrap:wrap; }
.ad-hero-stat {
  display:flex; flex-direction:column; align-items:center;
  padding:14px 18px; border-radius:10px;
  background:var(--sp-surface-strong); border:1px solid var(--sp-border-soft);
  min-width:90px; gap:4px;
}
.ad-hero-stat-val { font-size:22px; font-weight:700; color:var(--sp-text); font-variant-numeric:tabular-nums; }
.ad-hero-stat-lbl { font-size:10px; color:var(--sp-text-faint); text-transform:uppercase; font-weight:700; letter-spacing:.04em; }

/* Metric tiles */
.ad-metric-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(155px,1fr)); gap:10px; }
.ad-tile {
  padding:14px 16px; border-radius:8px;
  background:var(--sp-surface-strong); border:1px solid var(--sp-border-soft);
  display:flex; flex-direction:column; gap:8px; min-height:76px;
}
.ad-tile-label { font-size:10px; color:var(--sp-text-faint); text-transform:uppercase; font-weight:700; letter-spacing:.04em; }
.ad-tile-value { font-size:20px; font-weight:700; color:var(--sp-text-secondary); font-variant-numeric:tabular-nums; }

/* AI Insights layout */
.ai-layout {
  display:grid;
  grid-template-columns:220px 1fr;
  gap:28px;
  align-items:start;
}
.ai-left { display:flex; flex-direction:column; align-items:center; gap:18px; }
.ai-identity { display:flex; flex-direction:column; align-items:center; text-align:center; gap:8px; width:100%; }
.ai-avatar-wrap { position:relative; }
.ai-avatar {
  width:64px; height:64px; border-radius:50%;
  background:linear-gradient(135deg,#7c3aed,#a855f7);
  display:flex; align-items:center; justify-content:center;
  font-family:var(--font-heading); font-size:18px; font-weight:700; color:#fff;
  box-shadow:0 0 0 3px rgba(139,92,246,.25), 0 0 24px rgba(139,92,246,.2);
}
.sp-candidate-avatar {
  border-radius:50%;
  object-fit:cover;
  border:3px solid rgba(139,92,246,.75);
  box-shadow:0 0 0 3px rgba(139,92,246,.14), 0 12px 30px rgba(139,92,246,.18);
  flex:0 0 auto;
}
.sp-candidate-avatar.placeholder {
  display:flex;
  align-items:center;
  justify-content:center;
  background:linear-gradient(135deg,#7c3aed,#a855f7);
  color:#fff;
  font-weight:700;
}
.ai-name { font-family:var(--font-heading); font-size:15px; font-weight:700; color:var(--sp-text); letter-spacing:-0.02em; }
.ai-github { font-size:12px; color:var(--sp-text-faint); }
.ai-task-chip {
  display:inline-block; margin-top:4px;
  padding:3px 10px; border-radius:999px;
  background:rgba(99,102,241,.14); border:1px solid rgba(99,102,241,.28);
  color:#818cf8; font-size:11px; font-weight:700;
}
.ai-score-ring {
  width:110px; height:110px; border-radius:50%;
  display:grid; place-items:center;
}
.ai-score-inner {
  width:80px; height:80px; border-radius:50%;
  background:var(--sp-surface);
  display:grid; place-items:center; text-align:center;
}
.ai-score-inner strong { display:block; font-size:22px; font-weight:700; color:var(--sp-text); font-variant-numeric:tabular-nums; }
.ai-score-inner span  { font-size:9px; color:var(--sp-text-faint); font-weight:700; text-transform:uppercase; letter-spacing:.04em; }
.ai-badges { display:flex; flex-direction:column; gap:7px; width:100%; }
.ai-badge {
  display:inline-flex; align-items:center; justify-content:center;
  gap:6px; padding:6px 12px; border-radius:8px;
  font-size:11px; font-weight:700; border:1px solid; width:100%; box-sizing:border-box;
}

/* AI right col */
.ai-right { display:flex; flex-direction:column; gap:16px; }
.ai-summary { color:var(--sp-text-secondary); font-size:14px; line-height:1.75; margin:0; }
.ai-list-block { display:flex; flex-direction:column; gap:9px; }
.ai-list-label { font-size:10px; color:var(--sp-text-faint); font-weight:700; text-transform:uppercase; letter-spacing:.04em; }
.ai-list { margin:0; padding:0; list-style:none; display:flex; flex-direction:column; gap:7px; }
.ai-list li { display:flex; gap:9px; align-items:flex-start; font-size:13px; color:var(--sp-text-secondary); line-height:1.55; }
.ai-dot { width:7px; height:7px; border-radius:50%; flex-shrink:0; margin-top:5px; }
.ai-reason-box {
  padding:14px 16px; border-radius:8px;
  background:var(--sp-surface-strong); border:1px solid var(--sp-border-soft);
  display:flex; flex-direction:column; gap:8px;
}
.ai-reason-box p { margin:0; color:var(--sp-text-secondary); font-size:13px; line-height:1.65; }

/* Table */
.ad-table-wrap { overflow-x:auto; border-radius:10px; border:1px solid var(--sp-border-soft); background:var(--sp-surface-strong); }
.ad-table { width:100%; border-collapse:separate; border-spacing:0; min-width:700px; font-size:13px; }
.ad-table th { text-align:left; padding:12px 16px; color:var(--sp-text-faint); font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.04em; background:var(--sp-surface-strong); border-bottom:1px solid var(--sp-border-soft); }
.ad-table td { padding:13px 16px; color:var(--sp-text-muted); line-height:1.45; vertical-align:top; border-top:1px solid var(--sp-border-soft); }
.ad-table tbody tr:first-child td { border-top:none; }
.ad-table tbody tr:hover td { background:var(--sp-surface-hover); color:var(--sp-text-secondary); }
.ad-chip { display:inline-flex; align-items:center; padding:4px 9px; border-radius:999px; font-size:10px; font-weight:700; white-space:nowrap; border:1px solid; }
.chip-bug      { color:#f87171; background:rgba(248,113,113,.1);  border-color:rgba(248,113,113,.22); }
.chip-smell    { color:#818cf8; background:rgba(99,102,241,.1);   border-color:rgba(99,102,241,.22); }
.chip-severity { color:#fbbf24; background:rgba(251,191,36,.09);  border-color:rgba(251,191,36,.2); }

/* Empty / loading states */
.ad-empty-state {
  display:flex; flex-direction:column; align-items:center;
  padding:64px 28px; text-align:center;
  background:var(--sp-surface); border:1px solid var(--sp-border);
  border-radius:12px; backdrop-filter:blur(18px);
}
.ad-empty-icon {
  width:60px; height:60px; border-radius:14px;
  background:rgba(139,92,246,.1); border:1px solid rgba(139,92,246,.2);
  display:flex; align-items:center; justify-content:center;
  color:#a78bfa; margin-bottom:18px;
}
.ad-spin-icon { margin-bottom:18px; color:#a78bfa; }
.ad-empty-title { font-family:var(--font-heading); font-size:20px; font-weight:700; letter-spacing:-0.02em; color:var(--sp-text); margin:0 0 10px; }
.ad-empty-detail { font-size:14px; color:var(--sp-text-faint); margin:0; line-height:1.7; max-width:380px; }

/* Skeleton */
.ad-skeleton {
  border-radius:8px;
  background:linear-gradient(90deg,var(--sp-surface-strong),var(--sp-surface-hover),var(--sp-surface-strong));
  background-size:220% 100%;
  animation:shimmer 1.3s linear infinite;
}

/* Responsive */
@media (max-width:860px) {
  .ad-hero { flex-direction:column; align-items:flex-start; }
  .ai-layout { grid-template-columns:1fr; }
  .ai-left { flex-direction:row; flex-wrap:wrap; align-items:flex-start; }
  .ai-badges { flex-direction:row; flex-wrap:wrap; width:auto; }
  .ai-badge { width:auto; }
}
@media (max-width:600px) {
  .ad-page { padding:18px 16px 48px; }
  .ad-hero-stats { width:100%; }
}
`;
