import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api from "../api/auth";
import DashboardLayout from "./DashboardLayout";

interface AnalysisResult {
  analysis_run_id?: number;
  repo?: string;
  branch?: string;
  status: string;
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
  repository: {
    name: string;
    full_name: string;
    branch: string;
    analysis_date: string | null;
  };
  overall: {
    skill_score: number | null;
    skill_score_level: string;
    sonar_health_score: number | null;
    sonar_state: string;
    quality_gate: {
      status?: string;
      conditions?: Array<{
        metricKey?: string;
        comparator?: string;
        errorThreshold?: string;
        actualValue?: string;
        status?: string;
      }>;
    };
  };
  reliability: {
    rating: string | null;
    total_bugs: number;
    issues: SonarIssue[];
  };
  maintainability: {
    rating: string | null;
    code_smells: number;
    technical_debt_minutes: number;
    debt_ratio: number;
    issues: SonarIssue[];
  };
  coverage: {
    coverage: number;
    line_coverage: number;
    branch_coverage: number;
    uncovered_lines: number;
  };
  duplication: {
    percentage: number;
    duplicated_lines: number;
    duplicated_blocks: number;
    duplicated_files: number;
  };
  complexity: {
    cyclomatic_complexity: number;
    cognitive_complexity: number;
  };
  project_size: {
    lines_of_code: number;
    files: number;
    functions: number;
    classes: number;
  };
  issues_explorer: SonarIssue[];
  analysis_summary: {
    source: string;
    project_key: string | null;
    metrics_count: number;
    issues_count: number;
  };
}

const Icons = {
  back: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6" /></svg>,
  pulse: <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>,
  alert: <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>,
  gate: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 21V7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v14" /><path d="M9 21v-8h6v8" /><path d="M8 9h.01M12 9h.01M16 9h.01" /></svg>,
  bug: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect width="8" height="14" x="8" y="6" rx="4" /><path d="m19 7-3 2M5 7l3 2M19 19l-3-2M5 19l3-2M20 13h-4M4 13h4M10 4l1 2M14 4l-1 2" /></svg>,
  wrench: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" /></svg>,
  coverage: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2v20M2 12h20" /><circle cx="12" cy="12" r="8" /></svg>,
  copy: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect width="8" height="8" x="8" y="8" /><path d="M4 4h8v4M12 16v4h8v-8h-4" /></svg>,
  complexity: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="6" cy="6" r="3" /><circle cx="18" cy="6" r="3" /><circle cx="12" cy="18" r="3" /><path d="M8.5 7.5 11 15M15.5 7.5 13 15" /></svg>,
  size: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 7h16M4 12h16M4 17h10" /></svg>,
  list: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" /><line x1="3" y1="6" x2="3.01" y2="6" /><line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" /></svg>,
};

const formatNumber = (value: number | null | undefined) =>
  value === null || value === undefined ? "n/a" : new Intl.NumberFormat().format(value);

const formatPercent = (value: number | null | undefined) =>
  value === null || value === undefined ? "n/a" : `${Number(value).toFixed(1)}%`;

const formatMinutes = (value: number | null | undefined) => {
  if (value === null || value === undefined) return "n/a";
  if (value < 60) return `${formatNumber(value)} min`;
  return `${Math.round(value / 60)} h`;
};

const formatRating = (value: string | null | undefined) => {
  if (!value) return "n/a";
  const ratings: Record<string, string> = { "1": "A", "2": "B", "3": "C", "4": "D", "5": "E" };
  const normalized = String(Number(value));
  return ratings[normalized] ? `${ratings[normalized]} (${value})` : value;
};

const formatDate = (value: string | null | undefined) => {
  if (!value) return "n/a";
  return new Date(value).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
};

function StatPill({ label, value, color = "var(--text-secondary)" }: { label: string; value: string | number; color?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "14px 18px", borderRadius: 8, background: "var(--bg-card-hover)", border: "1px solid var(--border)", gap: 4, minWidth: 96 }}>
      <span style={{ fontSize: 20, fontWeight: 800, color, fontFamily: "'Syne',sans-serif" }}>{value}</span>
      <span style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0 }}>{label}</span>
    </div>
  );
}

function Section({ title, icon, children, delay = 0 }: { title: string; icon: ReactNode; children: ReactNode; delay?: number }) {
  return (
    <section className="fade-up ad-section" style={{ animationDelay: `${delay}ms` }}>
      <h2 className="ad-section-title">
        <span style={{ color: "#6366f1" }}>{icon}</span>
        {title}
      </h2>
      {children}
    </section>
  );
}

function MetricTile({ label, value, tone = "var(--text-secondary)" }: { label: string; value: string | number; tone?: string }) {
  return (
    <div style={{ padding: "14px 16px", borderRadius: 8, background: "var(--bg-card-hover)", border: "1px solid var(--border)", minHeight: 78 }}>
      <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0, marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 800, color: tone, fontFamily: "'Syne',sans-serif" }}>{value}</div>
    </div>
  );
}

function MetricGrid({ items }: { items: Array<{ label: string; value: string | number; tone?: string }> }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 }}>
      {items.map((item) => (
        <MetricTile key={item.label} label={item.label} value={item.value} tone={item.tone} />
      ))}
    </div>
  );
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div style={{ textAlign: "center", padding: "56px 28px", background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12 }}>
      <div style={{ width: 64, height: 64, borderRadius: 16, background: "rgba(99,102,241,0.1)", border: "1px solid rgba(99,102,241,0.25)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 18px", color: "#818cf8" }}>
        {Icons.alert}
      </div>
      <h2 style={{ fontFamily: "'Syne',sans-serif", fontSize: 22, fontWeight: 800, color: "var(--text-primary)", margin: "0 0 10px" }}>{title}</h2>
      <p style={{ fontSize: 14, color: "var(--text-muted)", margin: "0 0 24px", lineHeight: 1.7 }}>{detail}</p>
    </div>
  );
}

function IssuesExplorer({ issues }: { issues: SonarIssue[] }) {
  if (!issues.length) {
    return <p style={{ margin: 0, color: "var(--text-muted)", fontSize: 13 }}>No BUG or CODE_SMELL issues were returned by SonarQube.</p>;
  }

  return (
    <div className="ad-table-wrap">
      <table className="ad-table">
        <thead>
          <tr>
            <th>Type</th>
            <th>Severity</th>
            <th>File</th>
            <th className="ad-cell-right">Line</th>
            <th>Message</th>
          </tr>
        </thead>
        <tbody>
          {issues.map((issue, index) => (
            <tr key={`${issue.type}-${issue.file}-${issue.line}-${index}`}>
              <td><span className={`ad-issue-chip ${issue.type === "BUG" ? "bug" : "smell"}`}>{issue.type}</span></td>
              <td><span className="ad-severity-chip">{issue.severity}</span></td>
              <td className="ad-file-cell">{issue.file || "n/a"}</td>
              <td className="ad-cell-right">{issue.line || "n/a"}</td>
              <td className="ad-message-cell">{issue.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AnalysisDetail() {
  const { analysisId } = useParams<{ analysisId: string }>();
  const navigate = useNavigate();
  const role = localStorage.getItem("role") || "developer";
  const dashboardPath = `/dashboard/${role}/analysis`;

  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [sonar, setSonar] = useState<SonarDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [sonarLoading, setSonarLoading] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [polling, setPolling] = useState(false);
  const [sonarError, setSonarError] = useState("");

  const fetchSonarDashboard = async () => {
    if (!analysisId) return;
    setSonarLoading(true);
    setSonarError("");
    try {
      const res = await api.get(`/analysis/${analysisId}/sonar-dashboard`);
      setSonar(res.data);
    } catch (err: any) {
      setSonar(null);
      setSonarError(err?.response?.data?.detail || "SonarQube dashboard data is not available for this run.");
    } finally {
      setSonarLoading(false);
    }
  };

  useEffect(() => {
    if (!analysisId) {
      setNotFound(true);
      setLoading(false);
      return;
    }

    const fetchResult = async () => {
      try {
        const res = await api.get(`/analysis/${analysisId}`);
        const data: AnalysisResult = res.data;
        if (data.status === "pending" && !data.analysis_run_id) {
          setNotFound(true);
          setLoading(false);
          return;
        }
        setResult(data);
        setPolling(data.status === "running" || data.status === "pending");
        setLoading(false);
        if (data.status === "completed") {
          await fetchSonarDashboard();
        }
      } catch (err: any) {
        if (err.response?.status === 401) {
          localStorage.clear();
          window.location.href = "/login";
          return;
        }
        setNotFound(true);
        setLoading(false);
      }
    };

    fetchResult();
  }, [analysisId]);

  useEffect(() => {
    if (!polling || !analysisId) return;
    const iv = window.setInterval(async () => {
      try {
        const res = await api.get(`/analysis/${analysisId}`);
        const data: AnalysisResult = res.data;
        setResult(data);
        if (data.status === "completed" || data.status === "failed") {
          setPolling(false);
          window.clearInterval(iv);
          if (data.status === "completed") {
            await fetchSonarDashboard();
          }
        }
      } catch {
        window.clearInterval(iv);
      }
    }, 3000);
    return () => window.clearInterval(iv);
  }, [polling, analysisId]);

  const repoName = sonar?.repository.name ?? result?.repo?.split("/").pop() ?? result?.repo ?? "Repository";
  const repoFullName = sonar?.repository.full_name ?? result?.repo ?? "Repository";
  const branch = sonar?.repository.branch ?? result?.branch ?? "main";
  const skillScore = sonar?.overall.skill_score ?? null;
  const skillScoreLevel = sonar?.overall.skill_score_level ?? "Unavailable";

  return (
    <DashboardLayout>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800;900&family=DM+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&display=swap');
        @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        @keyframes fadeUp { from{opacity:0;transform:translateY(18px)} to{opacity:1;transform:translateY(0)} }
        @keyframes glow { 0%,100%{box-shadow:0 0 20px rgba(99,102,241,0.15)} 50%{box-shadow:0 0 40px rgba(99,102,241,0.35)} }
        .fade-up { opacity: 0; animation: fadeUp 0.55s cubic-bezier(.22,1,.36,1) forwards; }
        .glow { animation: glow 2.5s ease-in-out infinite; }
        .back-btn:hover { background: var(--bg-card-hover) !important; color: var(--text-primary) !important; }
        .ad-section { padding: 24px 26px; border-radius: 12px; background: var(--bg-card); border: 1px solid var(--border); }
        .ad-table-wrap { overflow-x: auto; border: 1px solid rgba(148,163,184,.14); border-radius: 16px; background: rgba(255,255,255,.018); }
        .ad-table { width: 100%; border-collapse: separate; border-spacing: 0; min-width: 720px; }
        .ad-table th { text-align: left; padding: 14px 16px; color: rgba(148,163,184,.82); font-size: 11px; font-weight: 900; text-transform: uppercase; letter-spacing: .72px; background: rgba(255,255,255,.035); border-bottom: 1px solid rgba(148,163,184,.13); }
        .ad-table td { padding: 15px 16px; color: var(--text-secondary); font-size: 13.5px; line-height: 1.45; vertical-align: top; border-top: 1px solid rgba(148,163,184,.09); }
        .ad-table tbody tr:first-child td { border-top: none; }
        .ad-table tbody tr:hover td { background: rgba(99,102,241,.08); color: var(--text-primary); }
        .ad-cell-right { text-align: right !important; white-space: nowrap; }
        .ad-file-cell { max-width: 260px; overflow-wrap: anywhere; color: var(--text-muted) !important; }
        .ad-message-cell { min-width: 280px; }
        .ad-issue-chip, .ad-severity-chip { display: inline-flex; align-items: center; padding: 5px 9px; border-radius: 999px; font-size: 11px; font-weight: 900; white-space: nowrap; }
        .ad-issue-chip.bug { color: #f87171; background: rgba(248,113,113,.12); border: 1px solid rgba(248,113,113,.23); }
        .ad-issue-chip.smell { color: #818cf8; background: rgba(99,102,241,.13); border: 1px solid rgba(99,102,241,.24); }
        .ad-severity-chip { color: #fbbf24; background: rgba(251,191,36,.1); border: 1px solid rgba(251,191,36,.22); }
        .ad-section-title { font-family: 'Syne',sans-serif; font-size: 15px; font-weight: 800; color: var(--text-primary); margin: 0 0 18px; display: flex; align-items: center; gap: 8px; }
        @media (max-width: 720px) {
          .hero-wrap { flex-direction: column; align-items: flex-start !important; }
          .hero-stats { width: 100%; align-items: stretch !important; }
        }
      `}</style>

      <div style={{ minHeight: "100vh", padding: "32px 20px 56px", fontFamily: "'DM Sans', sans-serif", color: "var(--text-primary)", background: "var(--bg-gradient)", maxWidth: 980, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 28 }}>
          <button className="back-btn" onClick={() => navigate(dashboardPath)} style={{ width: 38, height: 38, borderRadius: 8, border: "1px solid var(--border)", background: "var(--bg-card)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", cursor: "pointer", flexShrink: 0, transition: "all 0.15s" }}>
            {Icons.back}
          </button>
          <div>
            <h1 style={{ fontFamily: "'Syne',sans-serif", fontSize: 21, fontWeight: 800, color: "var(--text-primary)", margin: 0 }}>
              {loading ? "Loading..." : notFound ? "Not Found" : repoName}
            </h1>
            {!notFound && (
              <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "2px 0 0" }}>
                {repoFullName} / {branch}
              </p>
            )}
          </div>
        </div>

        {loading && (
          <div style={{ display: "grid", gap: 14 }}>
            {[0, 1, 2].map((item) => (
              <div key={item} style={{ height: 118, borderRadius: 12, background: "var(--bg-card)", border: "1px solid var(--border)", opacity: 0.7 }} />
            ))}
          </div>
        )}

        {!loading && notFound && (
          <EmptyState title="Analysis Not Found" detail="This analysis does not exist or you do not have permission to view it." />
        )}

        {!loading && !notFound && result && (result.status === "running" || result.status === "pending") && (
          <div style={{ textAlign: "center", padding: "64px 28px", background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12 }}>
            <div className="glow" style={{ width: 72, height: 72, borderRadius: 16, background: "rgba(99,102,241,0.1)", border: "1px solid rgba(99,102,241,0.25)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 20px", color: "#818cf8" }}>
              <span style={{ animation: "spin 2s linear infinite", display: "inline-flex" }}>{Icons.pulse}</span>
            </div>
            <h2 style={{ fontFamily: "'Syne',sans-serif", fontSize: 22, fontWeight: 800, color: "var(--text-primary)", margin: "0 0 10px" }}>Analysis in Progress</h2>
            <p style={{ fontSize: 14, color: "var(--text-muted)", margin: 0, lineHeight: 1.7 }}>SonarQube data will appear here when the run completes.</p>
          </div>
        )}

        {!loading && !notFound && result?.status === "failed" && (
          <EmptyState title="Analysis Failed" detail={result.message || "Something went wrong while analyzing this repository."} />
        )}

        {!loading && !notFound && result?.status === "completed" && sonarLoading && (
          <div style={{ textAlign: "center", padding: "56px 28px", background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, color: "var(--text-muted)" }}>
            Loading SonarQube dashboard...
          </div>
        )}

        {!loading && !notFound && result?.status === "completed" && !sonarLoading && sonarError && (
          <EmptyState title="SonarQube Data Unavailable" detail={sonarError} />
        )}

        {!loading && !notFound && result?.status === "completed" && sonar && (
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <div className="fade-up hero-wrap" style={{ padding: "26px 28px", borderRadius: 12, background: "var(--bg-card)", border: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24, animationDelay: "0ms" }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 999, background: "rgba(99,102,241,0.12)", color: "#818cf8", fontSize: 11, fontWeight: 800, textTransform: "uppercase" }}>{skillScoreLevel}</span>
                  <span style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 800 }}>Skill Score Engine</span>
                </div>
                <h2 style={{ fontFamily: "'Syne',sans-serif", fontSize: 22, fontWeight: 800, color: "var(--text-primary)", margin: "0 0 8px" }}>{sonar.repository.name}</h2>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 18px", fontSize: 12, color: "var(--text-muted)" }}>
                  <span>Repository: <strong style={{ color: "var(--text-secondary)" }}>{sonar.repository.full_name}</strong></span>
                  <span>Branch: <strong style={{ color: "var(--text-secondary)" }}>{sonar.repository.branch}</strong></span>
                  <span>Analyzed: <strong style={{ color: "var(--text-secondary)" }}>{formatDate(sonar.repository.analysis_date)}</strong></span>
                </div>
              </div>
              <div className="hero-stats" style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap", justifyContent: "flex-end" }}>
                <StatPill label="Overall Score" value={skillScore ?? "n/a"} color={skillScore === null ? "#94a3b8" : (skillScore >= 80 ? "#34d399" : skillScore >= 60 ? "#fbbf24" : "#f87171")} />
                <StatPill label="Score Level" value={skillScoreLevel} />
                <StatPill label="Issues" value={formatNumber(sonar.analysis_summary.issues_count)} />
              </div>
            </div>

            <Section title="Skill Score Engine" icon={Icons.gate} delay={80}>
              <MetricGrid items={[
                { label: "Overall Score", value: skillScore ?? "n/a" },
                { label: "Score Level", value: skillScoreLevel },
                { label: "Sonar Health Score", value: sonar.overall.sonar_health_score ?? "n/a" },
              ]} />
            </Section>

            <Section title="Reliability" icon={Icons.bug} delay={120}>
              <MetricGrid items={[
                { label: "Reliability Rating", value: formatRating(sonar.reliability.rating) },
                { label: "Bugs", value: formatNumber(sonar.reliability.total_bugs), tone: sonar.reliability.total_bugs > 0 ? "#f87171" : "#34d399" },
                { label: "Bug Issues", value: formatNumber(sonar.reliability.issues.length) },
              ]} />
            </Section>

            <Section title="Maintainability" icon={Icons.wrench} delay={160}>
              <MetricGrid items={[
                { label: "Maintainability Rating", value: formatRating(sonar.maintainability.rating) },
                { label: "Code Smells", value: formatNumber(sonar.maintainability.code_smells) },
                { label: "Technical Debt", value: formatMinutes(sonar.maintainability.technical_debt_minutes) },
                { label: "Debt Ratio", value: formatPercent(sonar.maintainability.debt_ratio) },
              ]} />
            </Section>

            <Section title="Coverage" icon={Icons.coverage} delay={200}>
              <MetricGrid items={[
                { label: "Coverage", value: formatPercent(sonar.coverage.coverage) },
                { label: "Line Coverage", value: formatPercent(sonar.coverage.line_coverage) },
                { label: "Branch Coverage", value: formatPercent(sonar.coverage.branch_coverage) },
                { label: "Uncovered Lines", value: formatNumber(sonar.coverage.uncovered_lines) },
              ]} />
            </Section>

            <Section title="Duplication" icon={Icons.copy} delay={240}>
              <MetricGrid items={[
                { label: "Duplications", value: formatPercent(sonar.duplication.percentage) },
                { label: "Duplicated Lines", value: formatNumber(sonar.duplication.duplicated_lines) },
                { label: "Duplicated Blocks", value: formatNumber(sonar.duplication.duplicated_blocks) },
                { label: "Duplicated Files", value: formatNumber(sonar.duplication.duplicated_files) },
              ]} />
            </Section>

            <Section title="Complexity" icon={Icons.complexity} delay={280}>
              <MetricGrid items={[
                { label: "Cyclomatic Complexity", value: formatNumber(sonar.complexity.cyclomatic_complexity) },
                { label: "Cognitive Complexity", value: formatNumber(sonar.complexity.cognitive_complexity) },
              ]} />
            </Section>

            <Section title="Project Size" icon={Icons.size} delay={320}>
              <MetricGrid items={[
                { label: "Lines Of Code", value: formatNumber(sonar.project_size.lines_of_code) },
                { label: "Files", value: formatNumber(sonar.project_size.files) },
              ]} />
            </Section>

            <Section title="Issues Explorer" icon={Icons.list} delay={360}>
              <IssuesExplorer issues={sonar.issues_explorer} />
            </Section>

            <Section title="Analysis Summary" icon={Icons.gate} delay={400}>
              <MetricGrid items={[
                { label: "Source", value: sonar.analysis_summary.source },
                { label: "Project Key", value: sonar.analysis_summary.project_key || "n/a" },
                { label: "Metrics", value: formatNumber(sonar.analysis_summary.metrics_count) },
                { label: "Issues", value: formatNumber(sonar.analysis_summary.issues_count) },
              ]} />
            </Section>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
