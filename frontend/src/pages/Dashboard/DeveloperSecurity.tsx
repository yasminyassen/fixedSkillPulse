import { useEffect, useMemo, useState } from "react";
import api from "../../api/auth";
import DashboardLayout from "../DashboardLayout";

interface RepoOption {
  analysis_id: number;
  repo_name: string;
  full_name: string;
  branch: string;
  completed_at: string | null;
}

interface SecurityScoreBreakdown {
  overall: number;
  code_security: number;
  dependency_security: number;
  weights: {
    code_security: number;
    dependency_security: number;
  };
  finding_counts: {
    code_security: number;
    dependency_security: number;
  };
}

interface SecurityDetail {
  analysis_run_id: number;
  repo: string;
  branch: string;
  scores: {
    security_score: number;
    security_score_breakdown?: SecurityScoreBreakdown;
  };
  ai_insights?: {
    security_insights?: string;
  };
}

interface SecurityFinding {
  tool?: string;
  rule?: string;
  owasp_category?: string;
  line_number?: number;
  description?: string;
  severity: "HIGH" | "MEDIUM" | "LOW";
  file_path: string;
}

interface SecurityReport {
  analysis_id: number;
  total_findings: number;
  severity_distribution: Record<string, number>;
  tool_distribution: Record<string, number>;
  owasp_distribution: Record<string, number>;
  top_vulnerable_files?: Record<string, number>;
  categorized_findings: Record<string, Record<string, Omit<SecurityFinding, "severity" | "file_path">[]>>;
  failed_tools?: string[];
  security_score_breakdown?: SecurityScoreBreakdown | null;
}

const severityConfig = {
  HIGH:   { label: "High",   color: "#f87171", bg: "rgba(248,113,113,0.1)",  border: "rgba(248,113,113,0.28)" },
  MEDIUM: { label: "Medium", color: "#fb923c", bg: "rgba(251,146,60,0.1)",   border: "rgba(251,146,60,0.28)"  },
  LOW:    { label: "Low",    color: "#fbbf24", bg: "rgba(251,191,36,0.1)",   border: "rgba(251,191,36,0.28)"  },
};

const safeNumber = (value: unknown) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
};

const scoreColor = (score: number) => {
  if (score >= 80) return "#34d399";
  if (score >= 60) return "#fbbf24";
  return "#f87171";
};

function CircleRing({ value, size = 80, stroke = 6, accent = "#6366f1" }: {
  value: number; size?: number; stroke?: number; accent?: string;
}) {
  const r      = (size - stroke) / 2;
  const circ   = 2 * Math.PI * r;
  const filled = (Math.min(Math.max(value, 0), 100) / 100) * circ;
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--border)" strokeWidth={stroke} />
      <circle
        cx={size/2} cy={size/2} r={r} fill="none"
        stroke={accent} strokeWidth={stroke}
        strokeDasharray={`${filled} ${circ}`} strokeLinecap="round"
        style={{ transition: "stroke-dasharray 0.8s cubic-bezier(0.4,0,0.2,1)" }}
      />
    </svg>
  );
}

function ScoreRing({ value, size = 80 }: { value: number; size?: number }) {
  const color = scoreColor(value);
  return (
    <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      <CircleRing value={value} size={size} stroke={6} accent={color} />
      <div style={{
        position: "absolute", inset: 0,
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      }}>
        <span style={{ fontSize: size * 0.26, fontWeight: 800, color: "var(--text-primary)", lineHeight: 1 }}>
          {Math.round(value)}
        </span>
        <span style={{ fontSize: size * 0.14, color: "var(--text-faint)" }}>/ 100</span>
      </div>
    </div>
  );
}

function DeltaBadge({ delta, large = false }: { delta: number; large?: boolean }) {
  if (!Number.isFinite(delta) || Math.abs(delta) < 0.05) return null;
  const pos = delta > 0;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: "4px",
      padding: large ? "4px 10px" : "2px 7px",
      borderRadius: "20px",
      background: pos ? "rgba(52,211,153,0.15)" : "rgba(248,113,113,0.12)",
      color: pos ? "#34d399" : "#f87171",
      fontSize: large ? "13px" : "11px", fontWeight: 700,
    }}>
      {pos ? "▲" : "▼"} {pos ? "+" : ""}{Math.abs(delta).toFixed(1)} pts
    </span>
  );
}

function FindingCard({ finding }: { finding: SecurityFinding }) {
  const cfg   = severityConfig[finding.severity];
  const title = finding.rule || finding.description?.split(".")[0] || "Security finding";
  return (
    <div style={{
      borderLeft: `3px solid ${cfg.color}`,
      background: "var(--bg-card)", borderRadius: "12px", padding: "16px 18px",
      borderTop: "1px solid var(--border)",
      borderRight: "1px solid var(--border)",
      borderBottom: "1px solid var(--border)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", alignItems: "flex-start" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "7px", flexWrap: "wrap" }}>
            <span style={{ fontSize: "14px", fontWeight: 800, color: "var(--text-primary)" }}>{title}</span>
            <span style={{
              fontSize: "10px", fontWeight: 800, color: cfg.color,
              background: cfg.bg, border: `1px solid ${cfg.border}`,
              padding: "2px 7px", borderRadius: "999px",
            }}>
              {cfg.label}
            </span>
          </div>
          <div style={{ fontSize: "12.5px", color: "var(--text-secondary)", lineHeight: 1.55 }}>
            {finding.description || "No description was provided by the scanner."}
          </div>
        </div>
        <span style={{
          fontSize: "11px", color: "var(--text-muted)",
          background: "var(--bg-card-hover)",
          padding: "5px 8px", borderRadius: "8px", whiteSpace: "nowrap",
        }}>
          {finding.tool || "scanner"}
        </span>
      </div>
      <div style={{ height: "1px", background: "var(--border)", margin: "13px 0" }} />
      <div style={{ display: "flex", gap: "14px", flexWrap: "wrap", fontSize: "11.5px", color: "var(--text-muted)" }}>
        <span><strong style={{ color: "var(--text-secondary)" }}>OWASP:</strong> {finding.owasp_category || "Unknown"}</span>
        <span><strong style={{ color: "var(--text-secondary)" }}>File:</strong> {finding.file_path}</span>
        <span><strong style={{ color: "var(--text-secondary)" }}>Line:</strong> {finding.line_number || 0}</span>
      </div>
    </div>
  );
}

function flattenFindings(report: SecurityReport | null): SecurityFinding[] {
  if (!report?.categorized_findings) return [];
  const rows: SecurityFinding[] = [];
  (["HIGH", "MEDIUM", "LOW"] as const).forEach(severity => {
    const files = report.categorized_findings[severity] || {};
    Object.entries(files).forEach(([filePath, findings]) => {
      findings.forEach(finding => rows.push({ ...finding, severity, file_path: filePath }));
    });
  });
  return rows;
}

function countBySeverity(report: SecurityReport | null, severity: "HIGH" | "MEDIUM" | "LOW") {
  const files = report?.categorized_findings?.[severity] || {};
  return Object.values(files).reduce((total, findings) => total + findings.length, 0);
}

export default function DeveloperSecurity() {
  const role   = localStorage.getItem("role") || "developer";
  const accent = role === "manager" ? "#8b5cf6" : role === "recruiter" ? "#a855f7" : "#6366f1";

  const [repos,                    setRepos]                    = useState<RepoOption[]>([]);
  const [selectedId,               setSelectedId]               = useState<number | null>(null);
  const [loadingRepos,             setLoadingRepos]             = useState(true);
  const [loadingDetail,            setLoadingDetail]            = useState(false);
  const [detail,                   setDetail]                   = useState<SecurityDetail | null>(null);
  const [report,                   setReport]                   = useState<SecurityReport | null>(null);
  const [aggregateSecurityScore,   setAggregateSecurityScore]   = useState<number | null>(null);
  const [aggregateBreakdown,       setAggregateBreakdown]       = useState<SecurityScoreBreakdown | null>(null);
  const [aggregateSecurityDelta,   setAggregateSecurityDelta]   = useState<number | null>(null);
  const [aggregateBreakdownDeltas, setAggregateBreakdownDeltas] = useState<{
    code_security: number; dependency_security: number;
  } | null>(null);

  useEffect(() => {
    (async () => {
      setLoadingRepos(true);
      try {
        const res      = await api.get("/analysis/skills/summary");
        const repoList: RepoOption[] = res.data.repos || [];
        setRepos(repoList);

        const details = await Promise.all(
          repoList.map(repo =>
            api.get(`/analysis/${repo.analysis_id}/detailed-metrics`)
              .then(r => r.data as SecurityDetail)
              .catch(() => null),
          ),
        );
        const scores = details
          .map(item => item?.scores?.security_score)
          .filter((score): score is number => typeof score === "number" && Number.isFinite(score));
        const breakdowns = details
          .map(item => item?.scores?.security_score_breakdown)
          .filter((item): item is SecurityScoreBreakdown => Boolean(item));

        setAggregateSecurityScore(scores.length ? scores.reduce((s, v) => s + v, 0) / scores.length : null);
        setAggregateBreakdown(averageBreakdowns(breakdowns));

        const orderedDetails = repoList
          .map((repo, index) => ({ repo, detail: details[index] }))
          .filter(item => typeof item.detail?.scores?.security_score === "number")
          .sort((a, b) => {
            const aTime = a.repo.completed_at ? new Date(a.repo.completed_at).getTime() : 0;
            const bTime = b.repo.completed_at ? new Date(b.repo.completed_at).getTime() : 0;
            return (bTime - aTime) || (b.repo.analysis_id - a.repo.analysis_id);
          });
        const latest   = orderedDetails[0]?.detail;
        const previous = orderedDetails[1]?.detail;
        setAggregateSecurityDelta(
          latest && previous
            ? safeNumber(latest.scores.security_score) - safeNumber(previous.scores.security_score)
            : null,
        );
        const latestBreakdown   = latest?.scores?.security_score_breakdown;
        const previousBreakdown = previous?.scores?.security_score_breakdown;
        setAggregateBreakdownDeltas(
          latestBreakdown && previousBreakdown
            ? {
              code_security:        safeNumber(latestBreakdown.code_security)        - safeNumber(previousBreakdown.code_security),
              dependency_security:  safeNumber(latestBreakdown.dependency_security)  - safeNumber(previousBreakdown.dependency_security),
            }
            : null,
        );
      } finally {
        setLoadingRepos(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!selectedId) { setDetail(null); setReport(null); return; }
    (async () => {
      setLoadingDetail(true);
      try {
        const [detailRes, reportRes] = await Promise.all([
          api.get(`/analysis/${selectedId}/detailed-metrics`),
          api.get(`/security-report/${selectedId}`),
        ]);
        setDetail(detailRes.data);
        setReport(reportRes.data);
      } finally {
        setLoadingDetail(false);
      }
    })();
  }, [selectedId]);

  const findings          = useMemo(() => flattenFindings(report), [report]);
  const topOwasp          = Object.entries(report?.owasp_distribution || {})
    .sort((a, b) => safeNumber(b[1]) - safeNumber(a[1])).slice(0, 4);
  const topFiles          = Object.entries(report?.top_vulnerable_files || {})
    .sort((a, b) => safeNumber(b[1]) - safeNumber(a[1])).slice(0, 4);
  const selectedRepo      = repos.find(repo => repo.analysis_id === selectedId);
  const selectedBreakdown = detail?.scores?.security_score_breakdown || report?.security_score_breakdown || null;
  const failedTools       = report?.failed_tools || [];
  const score             = aggregateSecurityScore ?? 0;
  const breakdown         = aggregateBreakdown;

  const getModeNotice = () => {
    if (selectedRepo) {
      return {
        title: "Repository Security Details",
        body: `Inspecting scanner findings, vulnerable files, and AI security summary for ${selectedRepo.repo_name} (${selectedRepo.branch}).`,
        tone: "#34d399",
      };
    }
    if (!loadingRepos && repos.length === 0) {
      return {
        title: "No Security Analyses Yet",
        body: "Run a repository analysis first, then return here to inspect security findings.",
        tone: "#fbbf24",
      };
    }
    return {
      title: "Select a Security Analysis",
      body: "Security scores summarize scanner findings from repositories where SkillPulse analyzed your GitHub contributions.",
      tone: accent,
    };
  };
  const notice = getModeNotice();

  return (
    <DashboardLayout>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        input, select { font-family: 'Inter', sans-serif; }
        .sk { background: linear-gradient(90deg, var(--bg-card) 25%, var(--bg-card-hover) 50%, var(--bg-card) 75%); background-size: 400% 100%; animation: shimmer 1.5s ease-in-out infinite; border-radius: 8px; }
        @keyframes shimmer { 0%{background-position:100% 50%} 100%{background-position:0% 50%} }
        .dim-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 24px 28px; transition: border-color 0.2s, background 0.3s ease; }
        .dim-card:hover { border-color: var(--border-hover); }
        .skl-select { background: var(--bg-input); border: 1px solid rgba(99,102,241,0.25); border-radius: 12px; color: var(--text-primary); font-family: 'Inter', sans-serif; font-size: 13.5px; padding: 10px 14px; outline: none; cursor: pointer; transition: border-color 0.2s; min-width: 220px; }
        .skl-select:focus { border-color: ${accent}80; }
        .skl-select option { background: var(--bg-base); color: var(--text-primary); }
        .skl-label { font-size: 12px; font-weight: 700; color: rgba(167,139,250,0.8); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 8px; display: block; }
        .metrics-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px 32px; margin-top: 18px; }
        .skl-btn-primary { display: inline-flex; align-items: center; gap: 8px; padding: 9px 18px; background: linear-gradient(135deg, ${accent}, #ec4899); border: none; border-radius: 10px; color: white; font-family: 'Inter', sans-serif; font-size: 13px; font-weight: 700; cursor: pointer; transition: all 0.2s; box-shadow: 0 4px 16px ${accent}30; }
        .skl-btn-primary:hover { transform: translateY(-1px); box-shadow: 0 8px 24px ${accent}40; }
        .legend-bar { display: flex; gap: 20px; flex-wrap: wrap; margin-top: 16px; padding: 10px 14px; background: var(--bg-input); border-radius: 8px; border: 1px solid var(--border); }
      `}</style>

      <div style={{ minHeight: "100vh", padding: "36px 40px 80px", color: "var(--text-primary)", fontFamily: "'Inter', sans-serif", background: "var(--bg-gradient)", transition: "background 0.3s ease" }}>
        <div style={{ maxWidth: 960, margin: "0 auto", display: "flex", flexDirection: "column", gap: 24 }}>

          {/* ── Header ── */}
          <div>
            <div style={{
              display: "inline-flex", alignItems: "center", gap: 8,
              padding: "5px 14px", borderRadius: 999,
              border: `1px solid ${accent}40`, background: `${accent}12`,
              fontSize: 11, fontWeight: 700, letterSpacing: "0.8px",
              color: accent, textTransform: "uppercase" as const,
              width: "fit-content", marginBottom: 10,
            }}>
              Security
            </div>
            <h1 style={{ fontFamily: "'Inter', sans-serif", fontSize: 26, fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-0.5px", margin: "0 0 4px" }}>
              Security Overview
            </h1>
            <p style={{ fontSize: 13.5, color: "var(--text-muted)", margin: 0, lineHeight: 1.6 }}>
              OWASP-aligned security findings for your analyzed contribution scope.
            </p>
          </div>

          {/* ── Mode notice ── */}
          {!loadingRepos && (
            <div style={{ display: "flex", alignItems: "flex-start", gap: 14, padding: "16px 20px", background: `${notice.tone}0F`, border: `1px solid ${notice.tone}35`, borderRadius: 14 }}>
              <div style={{ width: 34, height: 34, borderRadius: 10, background: `${notice.tone}18`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, color: notice.tone }}>
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>{notice.title}</div>
                <div style={{ fontSize: 12.5, color: "var(--text-secondary)", lineHeight: 1.6 }}>{notice.body}</div>
              </div>
            </div>
          )}

          {/* ── Aggregate score card ── */}
          <div className="dim-card">
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 24 }}>
              <div>
                <label className="skl-label">Security Score</label>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  Aggregated across repositories with completed security analysis
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                {loadingRepos ? (
                  <div className="sk" style={{ width: 80, height: 40 }} />
                ) : (
                  <>
                    <div style={{ fontSize: 42, fontWeight: 800, color: "var(--text-primary)", lineHeight: 1, letterSpacing: "-2px" }}>
                      {aggregateSecurityScore == null ? "--" : score.toFixed(1)}
                    </div>
                    {aggregateSecurityDelta != null && (
                      <div style={{ marginTop: 4, display: "flex", justifyContent: "flex-end" }}>
                        <DeltaBadge delta={aggregateSecurityDelta} large />
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>

            {loadingRepos ? (
              <div style={{ display: "flex", gap: 24 }}>
                {[1, 2].map(i => (
                  <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
                    <div className="sk" style={{ width: 80, height: 80, borderRadius: "50%" }} />
                    <div className="sk" style={{ width: 90, height: 14 }} />
                  </div>
                ))}
              </div>
            ) : breakdown ? (
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                {[
                  {
                    label: "Code Security",
                    value: breakdown.code_security,
                    sub: `${breakdown.finding_counts.code_security} findings`,
                    delta: aggregateBreakdownDeltas?.code_security ?? 0,
                  },
                  {
                    label: "Dependency Security",
                    value: breakdown.dependency_security,
                    sub: `${breakdown.finding_counts.dependency_security} findings`,
                    delta: aggregateBreakdownDeltas?.dependency_security ?? 0,
                  },
                ].map(item => (
                  <div key={item.label} style={{ flex: 1, minWidth: 140, display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
                    <ScoreRing value={item.value} size={80} />
                    <div style={{ textAlign: "center" }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 4 }}>{item.label}</div>
                      <DeltaBadge delta={item.delta} />
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{item.sub}</div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: 12.5, color: "var(--text-muted)" }}>
                Security breakdown will appear after an analysis is available.
              </div>
            )}
          </div>

          {/* ── Repo selector ── */}
          <div className="dim-card" style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
            <span style={{ fontSize: 13.5, color: "var(--text-secondary)", fontWeight: 500, whiteSpace: "nowrap" }}>
              View your security analysis for:
            </span>
            {loadingRepos ? (
              <div className="sk" style={{ width: 220, height: 36, borderRadius: 10 }} />
            ) : (
              <select
                className="skl-select"
                value={selectedId ?? ""}
                onChange={e => setSelectedId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">Select a repository…</option>
                {repos.map(repo => (
                  <option key={repo.analysis_id} value={repo.analysis_id}>
                    {repo.repo_name} ({repo.branch}) - {repo.completed_at ? new Date(repo.completed_at).toLocaleDateString() : "latest"}
                  </option>
                ))}
              </select>
            )}
            {!selectedId && !loadingRepos && repos.length > 0 && (
              <span style={{ fontSize: 12, color: "var(--text-faint)", width: "100%" }}>
                Select a repository to view scanner findings, affected files, and AI security guidance.
              </span>
            )}
          </div>

          {/* ── Empty states ── */}
          {!selectedId && !loadingRepos && repos.length === 0 && (
            <div style={{ textAlign: "center", padding: "60px 20px", background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 16 }}>
              <div style={{ width: 60, height: 60, borderRadius: 16, background: `${accent}15`, display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px" }}>
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke={accent} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="M12 8v5" /><path d="M12 17h.01" />
                </svg>
              </div>
              <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-secondary)", marginBottom: 6 }}>No completed analyses yet</div>
              <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Run a repository analysis first, then return here to inspect security findings.</div>
            </div>
          )}

          {/* ── Detail sections ── */}
          {selectedId && (
            <>
              {loadingDetail ? (
                <>
                  {[1, 2, 3].map(i => (
                    <div key={i} className="dim-card">
                      <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
                        <div className="sk" style={{ width: 72, height: 72, borderRadius: "50%" }} />
                        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 10 }}>
                          <div className="sk" style={{ height: 18, width: "40%" }} />
                          <div className="sk" style={{ height: 13, width: "60%" }} />
                          <div className="sk" style={{ height: 28, width: "22%", borderRadius: 20 }} />
                        </div>
                      </div>
                    </div>
                  ))}
                </>
              ) : (
                <>
                  {/* ── Repo breakdown ── */}
                  <div className="dim-card">
                    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
                      <div style={{ display: "flex", alignItems: "flex-start", gap: 14, flex: 1 }}>
                        <div style={{
                          width: 38, height: 38, borderRadius: 10, flexShrink: 0,
                          background: `${accent}18`, display: "flex", alignItems: "center",
                          justifyContent: "center", color: accent,
                        }}>
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                          </svg>
                        </div>
                        <div>
                          <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text-primary)", marginBottom: 3 }}>
                            Repository Security Breakdown
                          </div>
                          <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.4 }}>
                            Scanner findings for {selectedRepo?.repo_name} on {selectedRepo?.branch}
                          </div>
                        </div>
                      </div>
                      <ScoreRing value={safeNumber(detail?.scores?.security_score)} size={72} />
                    </div>

                    {failedTools.length > 0 && (
                      <div style={{
                        marginTop: 16,
                        border: "1px solid rgba(248,113,113,0.25)",
                        background: "rgba(248,113,113,0.08)",
                        color: "var(--text-secondary)", borderRadius: 12,
                        padding: "12px 14px", fontSize: 12.5,
                      }}>
                        Some scanners failed during this analysis:{" "}
                        <strong style={{ color: "#f87171" }}>{failedTools.join(", ")}</strong>.
                      </div>
                    )}

                    {selectedBreakdown && (
                      <div className="metrics-grid">
                        {[
                          {
                            label: "Code Security",
                            value: selectedBreakdown.code_security,
                            sub: `${selectedBreakdown.finding_counts.code_security} findings · ${Math.round(selectedBreakdown.weights.code_security * 100)}% weight`,
                          },
                          {
                            label: "Dependency Security",
                            value: selectedBreakdown.dependency_security,
                            sub: `${selectedBreakdown.finding_counts.dependency_security} findings · ${Math.round(selectedBreakdown.weights.dependency_security * 100)}% weight`,
                          },
                        ].map(item => (
                          <div key={item.label}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: 6 }}>
                              <span style={{ fontSize: 12.5, color: "var(--text-secondary)", fontWeight: 500 }}>{item.label}</span>
                              <span style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>{Math.round(item.value)}</span>
                            </div>
                            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>{item.sub}</div>
                            <div style={{ height: 5, background: "var(--border)", borderRadius: 3, overflow: "hidden" }}>
                              <div style={{
                                height: "100%", borderRadius: 3,
                                background: scoreColor(item.value),
                                width: `${Math.min(100, Math.max(0, item.value))}%`,
                              }} />
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* ── Findings breakdown ── */}
                  <div className="dim-card">
                    <label className="skl-label">Findings Breakdown</label>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 18, marginTop: 8 }}>
                      {(["HIGH", "MEDIUM", "LOW"] as const).map(severity => {
                        const cfg   = severityConfig[severity];
                        const count = countBySeverity(report, severity);
                        return (
                          <div key={severity} style={{ background: cfg.bg, border: `1px solid ${cfg.border}`, borderRadius: 12, padding: 16 }}>
                            <div style={{ fontSize: 24, fontWeight: 900, color: "var(--text-primary)", marginBottom: 3 }}>{count}</div>
                            <div style={{ fontSize: 12, color: cfg.color, fontWeight: 800 }}>{cfg.label} Severity</div>
                          </div>
                        );
                      })}
                    </div>
                    <div className="metrics-grid">
                      <div>
                        <label className="skl-label">Top OWASP Categories</label>
                        {topOwasp.length ? topOwasp.map(([name, count]) => (
                          <div key={name} style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 12, color: "var(--text-secondary)", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                            <span>{name}</span>
                            <strong style={{ color: "var(--text-primary)" }}>{count}</strong>
                          </div>
                        )) : <span style={{ fontSize: 12, color: "var(--text-muted)" }}>No OWASP categories detected.</span>}
                      </div>
                      <div>
                        <label className="skl-label">Top Affected Files</label>
                        {topFiles.length ? topFiles.map(([name, count]) => (
                          <div key={name} style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 12, color: "var(--text-secondary)", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</span>
                            <strong style={{ color: "var(--text-primary)" }}>{count}</strong>
                          </div>
                        )) : <span style={{ fontSize: 12, color: "var(--text-muted)" }}>No affected files detected.</span>}
                      </div>
                    </div>
                  </div>

                  {/* ── Vulnerabilities list ── */}
                  <div className="dim-card">
                    <label className="skl-label">Detected Vulnerabilities</label>
                    {findings.length ? (
                      <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 8 }}>
                        {findings.map((finding, index) => (
                          <FindingCard
                            key={`${finding.severity}-${finding.file_path}-${finding.rule}-${index}`}
                            finding={finding}
                          />
                        ))}
                      </div>
                    ) : (
                      <div style={{ marginTop: 12, padding: "12px 16px", background: "var(--bg-input)", borderRadius: 10, fontSize: 12, color: "var(--text-faint)" }}>
                        The selected analysis did not produce security findings for this contribution scope.
                      </div>
                    )}
                  </div>

                  {/* ── AI summary ── */}
                  {detail?.ai_insights?.security_insights ? (
                    <div className="dim-card" style={{ borderColor: `${accent}35`, background: `${accent}0F` }}>
                      <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                        <div style={{
                          width: 34, height: 34, borderRadius: 10,
                          background: `${accent}18`, display: "grid", placeItems: "center",
                          flexShrink: 0, color: accent,
                        }}>
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M9 18h6" /><path d="M10 22h4" />
                            <path d="M8.5 14a6 6 0 1 1 7 0c-.7.5-1.1 1.3-1.1 2.1V17H9.6v-.9c0-.8-.4-1.6-1.1-2.1z" />
                          </svg>
                        </div>
                        <div>
                          <label className="skl-label" style={{ marginBottom: 8 }}>AI Security Summary</label>
                          <p style={{ margin: 0, fontSize: 13, lineHeight: 1.65, color: "var(--text-secondary)" }}>
                            {detail.ai_insights.security_insights}
                          </p>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div style={{ marginTop: -8, padding: "12px 16px", background: "var(--bg-input)", borderRadius: 10, fontSize: 12, color: "var(--text-faint)" }}>
                      AI guidance is not available for this dimension yet.
                    </div>
                  )}
                </>
              )}
            </>
          )}

        </div>
      </div>
    </DashboardLayout>
  );
}

function averageBreakdowns(breakdowns: SecurityScoreBreakdown[]): SecurityScoreBreakdown | null {
  if (!breakdowns.length) return null;
  const count = breakdowns.length;
  return {
    overall:              breakdowns.reduce((sum, item) => sum + safeNumber(item.overall),              0) / count,
    code_security:        breakdowns.reduce((sum, item) => sum + safeNumber(item.code_security),        0) / count,
    dependency_security:  breakdowns.reduce((sum, item) => sum + safeNumber(item.dependency_security),  0) / count,
    weights: {
      code_security:       breakdowns[0]?.weights?.code_security       ?? 0.6,
      dependency_security: breakdowns[0]?.weights?.dependency_security ?? 0.4,
    },
    finding_counts: {
      code_security:       breakdowns.reduce((sum, item) => sum + safeNumber(item.finding_counts?.code_security),       0),
      dependency_security: breakdowns.reduce((sum, item) => sum + safeNumber(item.finding_counts?.dependency_security), 0),
    },
  };
}