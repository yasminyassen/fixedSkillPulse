import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  KeyRound,
  Lightbulb,
  Lock,
  RefreshCcw,
  Shield,
  ShieldAlert,
  Target,
  Users,
  type LucideIcon,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import api from "../../api/auth";
import DashboardLayout from "../DashboardLayout";

interface SecurityRepo {
  id: number;
  name: string | null;
  full_name: string | null;
  is_private: boolean;
  last_analyzed_at: string | null;
  security_score: number;
  total_issues: number;
}

interface RiskBreakdown {
  high: number;
  medium: number;
  low: number;
  total: number;
}

interface TrendPoint {
  period: string;
  label: string;
  high: number;
  medium: number;
  low: number;
}

interface CommonIssue {
  title: string;
  severity: string;
  occurrences: number;
  repositories_affected: number;
}

interface SecurityMember {
  id: number;
  full_name: string;
  username: string;
  avatar_url: string | null;
  specialization: string | null;
  repository_count: number;
  security_score: number;
  high: number;
  medium: number;
  low: number;
}

interface TeamSecurityOverview {
  overall_score: number;
  repository_count: number;
  total_issues: number;
  team_members: number;
  risk_breakdown: RiskBreakdown;
  trend: TrendPoint[];
  common_issues: CommonIssue[];
  systemic_risk_analysis: string;
  why_this_matters: string[];
  members: SecurityMember[];
}

interface RepositorySummary {
  id: number;
  name: string | null;
  full_name: string | null;
  security_score: number;
  total_issues: number;
  high: number;
  medium: number;
  low: number;
}

interface Vulnerability {
  id: number;
  title: string;
  severity: string;
  description: string | null;
  file_path: string | null;
  line_number: number | null;
  cwe: string | null;
  owasp_category: string | null;
  contributor_id: number | null;
  contributor_name: string | null;
}

interface ContributorImpact {
  id: number;
  full_name: string;
  username: string;
  avatar_url: string | null;
  specialization: string | null;
  security_score: number;
  issue_count: number;
  issues_fixed: number;
  issues_introduced: number;
  high: number;
  medium: number;
  low: number;
  net_impact: string;
}

interface ContributorIssueGroup {
  severity: string;
  issues: Vulnerability[];
}

interface RepositorySecurityDetail {
  repository: RepositorySummary;
  release_readiness: string;
  detected_vulnerabilities: Vulnerability[];
  recommended_actions: string[];
  contributor_impacts: ContributorImpact[];
  issues_by_contributor: ContributorIssueGroup[];
}

const emptyTeam: TeamSecurityOverview = {
  overall_score: 0,
  repository_count: 0,
  total_issues: 0,
  team_members: 0,
  risk_breakdown: { high: 0, medium: 0, low: 0, total: 0 },
  trend: [],
  common_issues: [],
  systemic_risk_analysis: "",
  why_this_matters: [],
  members: [],
};

const severityMeta: Record<string, { color: string; bg: string; label: string }> = {
  High: { color: "#ef4444", bg: "rgba(239,68,68,0.12)", label: "High" },
  Medium: { color: "#f97316", bg: "rgba(249,115,22,0.13)", label: "Medium" },
  Low: { color: "#eab308", bg: "rgba(234,179,8,0.14)", label: "Low" },
};

const scoreColor = (score: number) => {
  if (score >= 85) return "#22c55e";
  if (score >= 70) return "#f59e0b";
  return "#f97316";
};

const fmt = (value: number | null | undefined, digits = 0) => {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? n.toFixed(digits) : "0";
};

const initials = (name: string) =>
  name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0])
    .join("")
    .toUpperCase() || "SP";

const titleForRepo = (repo?: SecurityRepo | null) => repo?.name || repo?.full_name || "Repository";

function Panel({ title, icon: Icon, children, className = "" }: {
  title: string;
  icon?: LucideIcon;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`ms-panel ${className}`}>
      <div className="ms-panel-title">
        {Icon && <Icon size={18} strokeWidth={2.2} />}
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );
}

function ScoreHero({
  score,
  repositoryCount,
  totalIssues,
  teamMembers,
}: {
  score: number;
  repositoryCount: number;
  totalIssues: number;
  teamMembers: number;
}) {
  return (
    <section className="ms-hero">
      <div>
        <div className="ms-hero-label"><Shield size={20} /> Overall Security Score</div>
        <div className="ms-hero-score"><strong>{fmt(score)}</strong><span>/ 100</span></div>
        <p>Aggregated security score based on manager-run team repository analysis.</p>
        <div className="ms-hero-stats">
          <MetricMini value={repositoryCount} label="Repositories" />
          <MetricMini value={totalIssues} label="Total Issues" />
          <MetricMini value={teamMembers} label="Team Members" />
        </div>
      </div>
      <div className="ms-score-ring" style={{ "--score": `${Math.max(0, Math.min(100, score)) * 3.6}deg` } as CSSProperties}>
        <Shield size={46} />
      </div>
    </section>
  );
}

function MetricMini({ value, label }: { value: number; label: string }) {
  return <div className="ms-mini"><strong>{value}</strong><span>{label}</span></div>;
}

function RiskCard({ label, value, total, severity }: {
  label: string;
  value: number;
  total: number;
  severity: "High" | "Medium" | "Low";
}) {
  const meta = severityMeta[severity];
  const pct = total ? Math.min(100, (value / total) * 100) : 0;
  return (
    <div className="ms-risk-card" style={{ borderColor: meta.color, background: meta.bg }}>
      <div className="ms-risk-top">
        <span style={{ background: meta.bg, color: meta.color }}>
          {severity === "High" ? <ShieldAlert size={16} /> : <AlertTriangle size={16} />}
        </span>
        <strong>{value}</strong>
        <small>issues</small>
      </div>
      <b style={{ color: meta.color }}>{label}</b>
      <div className="ms-risk-bar"><span style={{ width: `${pct}%`, background: meta.color }} /></div>
    </div>
  );
}

function IssueRow({ issue }: { issue: CommonIssue }) {
  const severity = issue.severity as "High" | "Medium" | "Low";
  const meta = severityMeta[severity] || severityMeta.Medium;
  return (
    <article className="ms-issue-row">
      <span className="ms-issue-icon" style={{ color: meta.color, background: meta.bg }}>
        {issue.title.toLowerCase().includes("secret") ? <KeyRound size={18} /> : <Lock size={18} />}
      </span>
      <div>
        <strong>{issue.title}</strong>
        <p>{issue.occurrences} occurrence{issue.occurrences === 1 ? "" : "s"} • {issue.repositories_affected} repositor{issue.repositories_affected === 1 ? "y" : "ies"} affected</p>
      </div>
      <span className="ms-pill" style={{ color: meta.color, background: meta.bg }}>{meta.label}</span>
      <b>{issue.occurrences}</b>
    </article>
  );
}

function MemberSecurityRow({ member }: { member: SecurityMember }) {
  const color = scoreColor(member.security_score);
  return (
    <article className="ms-member-row">
      <div className="ms-avatar">{member.avatar_url ? <img src={member.avatar_url} alt="" /> : initials(member.full_name)}</div>
      <div>
        <strong>{member.full_name}</strong>
        <p>{member.repository_count} repositor{member.repository_count === 1 ? "y" : "ies"}</p>
        <small>
          {!!member.high && <span className="ms-high">{member.high} high</span>}
          {!!member.medium && <span className="ms-med">{member.medium} medium</span>}
          {!!member.low && <span className="ms-low">{member.low} low</span>}
          {!member.high && !member.medium && !member.low && <span>No attributed issues</span>}
        </small>
      </div>
      <div className="ms-member-score" style={{ color }}>
        <strong>{fmt(member.security_score)}</strong><span>/100</span>
      </div>
    </article>
  );
}

function VulnerabilityRow({ item }: { item: Vulnerability }) {
  const meta = severityMeta[item.severity] || severityMeta.Medium;
  return (
    <article className="ms-vuln-row">
      <span className="ms-issue-icon" style={{ color: meta.color, background: meta.bg }}><AlertTriangle size={18} /></span>
      <div>
        <div className="ms-vuln-title">
          <strong>{item.title}</strong>
          <span className="ms-pill" style={{ color: meta.color, background: meta.bg }}>{item.severity}</span>
        </div>
        <p>{item.description || "Security finding detected by static analysis."}</p>
        {(item.file_path || item.contributor_name) && (
          <small>{item.file_path}{item.line_number ? `:${item.line_number}` : ""}{item.contributor_name ? ` • Last attributed to ${item.contributor_name}` : ""}</small>
        )}
      </div>
    </article>
  );
}

function ContributorCard({ contributor }: { contributor: ContributorImpact }) {
  const impactClass = contributor.net_impact.toLowerCase();
  return (
    <article className="ms-contributor-card">
      <div className="ms-contributor-head">
        <div className="ms-avatar">{contributor.avatar_url ? <img src={contributor.avatar_url} alt="" /> : initials(contributor.full_name)}</div>
        <div>
          <strong>{contributor.full_name}</strong>
          <p>{fmt(contributor.security_score)} security score</p>
        </div>
        <span className={`ms-impact ${impactClass}`}>{contributor.net_impact}</span>
      </div>
      <div className="ms-contributor-stats">
        <span><CheckCircle2 size={14} /> Issues Fixed <b>{contributor.issues_fixed}</b></span>
        <span className={contributor.issues_introduced ? "ms-med" : ""}><AlertTriangle size={14} /> Issues Introduced <b>{contributor.issues_introduced}</b></span>
        {!!contributor.high && <span className="ms-high"><AlertTriangle size={14} /> {contributor.high} high</span>}
        {!!contributor.medium && <span className="ms-med"><AlertTriangle size={14} /> {contributor.medium} medium</span>}
        {!!contributor.low && <span className="ms-low"><AlertTriangle size={14} /> {contributor.low} low</span>}
        {!contributor.issue_count && !contributor.issues_fixed && !contributor.issues_introduced && <span>No active or changed issues</span>}
      </div>
    </article>
  );
}

export default function ManagerSecurityDashboard() {
  const [repos, setRepos] = useState<SecurityRepo[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState("all");
  const [teamData, setTeamData] = useState<TeamSecurityOverview>(emptyTeam);
  const [repoData, setRepoData] = useState<RepositorySecurityDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const selectedRepo = useMemo(
    () => repos.find(repo => String(repo.id) === selectedRepoId) || null,
    [repos, selectedRepoId],
  );

  const fetchRepos = async () => {
    const response = await api.get<SecurityRepo[]>("/manager/security/repos");
    setRepos(response.data || []);
  };

  const fetchDashboard = async () => {
    setLoading(true);
    setError("");
    try {
      if (selectedRepoId === "all") {
        const response = await api.get<TeamSecurityOverview>("/manager/security/team");
        setTeamData(response.data || emptyTeam);
        setRepoData(null);
      } else {
        const response = await api.get<RepositorySecurityDetail>(`/manager/security/repositories/${selectedRepoId}`);
        setRepoData(response.data);
      }
    } catch (err) {
      console.error(err);
      setError("Unable to load manager security dashboard.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRepos().catch(console.error);
  }, []);

  useEffect(() => {
    fetchDashboard();
  }, [selectedRepoId]);

  const activeBreakdown = selectedRepoId === "all"
    ? teamData.risk_breakdown
    : {
        high: repoData?.repository.high || 0,
        medium: repoData?.repository.medium || 0,
        low: repoData?.repository.low || 0,
        total: repoData?.repository.total_issues || 0,
      };

  return (
    <DashboardLayout>
      <main className="ms-page">
        <header className="ms-header">
          <div>
            <h1>Team Security Health</h1>
            <p>Security risk assessment and release readiness across team repositories</p>
          </div>
          <button className="ms-refresh" type="button" onClick={() => { fetchRepos(); fetchDashboard(); }} title="Refresh dashboard">
            <RefreshCcw size={17} />
          </button>
        </header>

        <ScoreHero
          score={selectedRepoId === "all" ? teamData.overall_score : repoData?.repository.security_score || 0}
          repositoryCount={selectedRepoId === "all" ? teamData.repository_count : 1}
          totalIssues={activeBreakdown.total}
          teamMembers={selectedRepoId === "all" ? teamData.team_members : repoData?.contributor_impacts.length || 0}
        />

        <section className="ms-filter">
          <div><Target size={18} /><span><strong>Repository Filter</strong><small>View security details for a specific repository</small></span></div>
          <select value={selectedRepoId} onChange={event => setSelectedRepoId(event.target.value)}>
            <option value="all">All Repositories (Team View)</option>
            {repos.map(repo => <option key={repo.id} value={repo.id}>{titleForRepo(repo)}</option>)}
          </select>
        </section>

        {loading ? (
          <div className="ms-panel ms-loading">Loading security metrics...</div>
        ) : error ? (
          <div className="ms-panel ms-error">{error}</div>
        ) : selectedRepoId === "all" ? (
          <>
            <Panel title="Security Risk Breakdown">
              <div className="ms-risk-grid">
                <RiskCard label="High Risk Issues" value={teamData.risk_breakdown.high} total={teamData.risk_breakdown.total} severity="High" />
                <RiskCard label="Medium Risk Issues" value={teamData.risk_breakdown.medium} total={teamData.risk_breakdown.total} severity="Medium" />
                <RiskCard label="Low Risk Issues" value={teamData.risk_breakdown.low} total={teamData.risk_breakdown.total} severity="Low" />
              </div>
              <div className="ms-note"><Info size={14} /> Based on OWASP-aligned static security analysis.</div>
              <div className="ms-divider" />
              <h3>Security Risk Trend (Last 3 Months)</h3>
              <div className="ms-chart">
                <ResponsiveContainer width="100%" height={170}>
                  <BarChart data={teamData.trend}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--chart-grid)" />
                    <XAxis dataKey="label" tickLine={false} axisLine={false} />
                    <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
                    <Tooltip />
                    <Bar dataKey="high" stackId="a" fill="#fecaca" name="High" />
                    <Bar dataKey="medium" stackId="a" fill="#fed7aa" name="Medium" />
                    <Bar dataKey="low" stackId="a" fill="#fef08a" name="Low" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>

            <Panel title="Most Common Security Issues">
              <div className="ms-list">
                {teamData.common_issues.length ? teamData.common_issues.map(issue => <IssueRow key={issue.title} issue={issue} />) : <p className="ms-empty">No security issues detected.</p>}
              </div>
            </Panel>

            <section className="ms-callout blue"><Lightbulb size={24} /><div><h2>Systemic Risk Pattern Analysis</h2><p>{teamData.systemic_risk_analysis}</p></div></section>
            <section className="ms-callout green"><Target size={24} /><div><h2>Why This Matters</h2>{teamData.why_this_matters.map(item => <p key={item}><CheckCircle2 size={15} /> {item}</p>)}</div></section>

            <Panel title="Individual Security Scores" icon={Users}>
              <div className="ms-list">{teamData.members.map(member => <MemberSecurityRow key={member.id} member={member} />)}</div>
            </Panel>
          </>
        ) : repoData ? (
          <>
            <Panel title={`Repository Security Score: ${repoData.repository.name || selectedRepo?.name || "Repository"}`} icon={Shield}>
              <div className="ms-repo-score"><strong>{fmt(repoData.repository.security_score)}</strong><span>/ 100</span></div>
              <div className="ms-repo-metrics">
                <MetricMini value={repoData.repository.total_issues} label="Total Issues" />
                <MetricMini value={repoData.repository.high} label="High Risk" />
                <MetricMini value={repoData.repository.medium} label="Medium Risk" />
                <MetricMini value={repoData.repository.low} label="Low Risk" />
              </div>
            </Panel>

            <section className="ms-callout blue"><Target size={24} /><div><h2>Release Readiness Assessment</h2><p>{repoData.release_readiness}</p></div></section>

            <Panel title="Detected Vulnerabilities">
              <div className="ms-list">{repoData.detected_vulnerabilities.length ? repoData.detected_vulnerabilities.map(item => <VulnerabilityRow key={item.id} item={item} />) : <p className="ms-empty">No vulnerabilities detected in this repository.</p>}</div>
            </Panel>

            <section className="ms-callout blue"><Lightbulb size={24} /><div><h2>Recommended Actions</h2>{repoData.recommended_actions.map(action => <p key={action}><CheckCircle2 size={15} /> {action}</p>)}</div></section>

            <Panel title="Security Contribution by Member (This Repository)" icon={Users}>
              <p className="ms-subtle">Shows how each team member is associated with the security outcome of this repository.</p>
              <div className="ms-contributor-grid">{repoData.contributor_impacts.map(item => <ContributorCard key={item.id} contributor={item} />)}</div>
            </Panel>

            <Panel title="Security Issues by Contributor">
              <p className="ms-subtle">Vulnerabilities grouped by severity and attributed to contributors using analysis-time file ownership.</p>
              {repoData.issues_by_contributor.length ? repoData.issues_by_contributor.map(group => (
                <div className="ms-group" key={group.severity}>
                  <span className="ms-pill" style={{ color: severityMeta[group.severity]?.color, background: severityMeta[group.severity]?.bg }}>{group.severity} Risk</span>
                  {group.issues.map(issue => <VulnerabilityRow key={issue.id} item={issue} />)}
                </div>
              )) : <p className="ms-empty">No attributed vulnerabilities for this repository.</p>}
            </Panel>
          </>
        ) : null}

        <section className="ms-about"><Info size={18} /><p>Team security scores are calculated from manager-run repository analysis using existing security findings and developer security scores. Contributor attribution uses analysis-time user ownership for findings and metrics.</p></section>
      </main>

      <style>{`
        .ms-page { max-width: 960px; margin: 0 auto; padding: 32px 18px 56px; color: var(--text-primary); }
        .ms-header { display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; margin-bottom: 22px; }
        .ms-header h1 { margin: 0 0 6px; font-size: 28px; font-weight: 850; font-family: 'Inter', sans-serif; letter-spacing: 0; }
        .ms-header p, .ms-subtle { margin: 0; color: var(--text-secondary); font-size: 13.5px; }
        .ms-refresh { width: 42px; height: 42px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card); color: var(--text-secondary); display: inline-flex; align-items: center; justify-content: center; cursor: pointer; }
        .ms-hero, .ms-panel, .ms-filter, .ms-callout, .ms-about { border: 1px solid var(--border); background: var(--bg-card); border-radius: 8px; box-shadow: var(--shadow-card); }
        .ms-hero { display: flex; justify-content: space-between; gap: 24px; align-items: center; padding: 22px; margin-bottom: 18px; border-color: rgba(249,115,22,0.35); background: linear-gradient(120deg, rgba(255,247,237,0.88), rgba(254,242,242,0.72)); }
        [data-theme="dark"] .ms-hero { background: linear-gradient(120deg, rgba(124,45,18,0.26), rgba(127,29,29,0.18)); }
        .ms-hero-label { display: flex; align-items: center; gap: 9px; font-weight: 800; color: var(--text-primary); }
        .ms-hero-score, .ms-repo-score { display: flex; align-items: baseline; gap: 8px; margin: 16px 0 8px; }
        .ms-hero-score strong, .ms-repo-score strong { font-size: 38px; line-height: 1; color: var(--text-primary); }
        .ms-hero-score span, .ms-repo-score span { font-size: 20px; color: var(--text-secondary); }
        .ms-hero p { color: var(--text-secondary); margin: 0 0 18px; font-size: 13px; }
        .ms-hero-stats, .ms-repo-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
        .ms-repo-metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top: 18px; }
        .ms-mini { border: 1px solid rgba(249,115,22,0.25); border-radius: 8px; padding: 12px; min-width: 0; }
        .ms-mini strong { display: block; font-size: 19px; color: var(--text-primary); }
        .ms-mini span { color: var(--text-muted); font-size: 11.5px; }
        .ms-score-ring { --score: 0deg; position: relative; width: 108px; height: 108px; border-radius: 50%; background: conic-gradient(#f97316 var(--score), rgba(249,115,22,0.2) 0); display: grid; place-items: center; color: #f97316; flex: 0 0 auto; }
        .ms-score-ring:before { content: ""; position: absolute; inset: 11px; border-radius: 50%; background: var(--bg-card); }
        .ms-score-ring svg { position: relative; z-index: 1; }
        .ms-filter { display: flex; justify-content: space-between; align-items: center; gap: 18px; padding: 12px 16px; margin-bottom: 18px; background: rgba(59,130,246,0.08); border-color: rgba(59,130,246,0.22); }
        .ms-filter div { display: flex; align-items: center; gap: 10px; color: #3b82f6; }
        .ms-filter span { display: grid; color: var(--text-primary); }
        .ms-filter small { color: var(--text-secondary); font-size: 11px; }
        .ms-filter select { min-width: 250px; border: 1px solid var(--border); background: var(--bg-card); color: var(--text-primary); border-radius: 8px; padding: 10px 12px; font-weight: 700; }
        .ms-panel { padding: 20px; margin-bottom: 18px; }
        .ms-panel-title { display: flex; align-items: center; gap: 9px; margin-bottom: 18px; color: #7c3aed; }
        .ms-panel-title h2, .ms-callout h2 { margin: 0; font-size: 16px; font-weight: 850; color: var(--text-primary); }
        .ms-risk-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
        .ms-risk-card { border: 1px solid; border-radius: 8px; padding: 16px; }
        .ms-risk-top { display: flex; align-items: center; gap: 8px; }
        .ms-risk-top span { width: 30px; height: 30px; border-radius: 7px; display: grid; place-items: center; }
        .ms-risk-top strong { font-size: 25px; }
        .ms-risk-top small { color: var(--text-muted); }
        .ms-risk-card b { display: block; margin: 14px 0 8px; font-size: 12px; }
        .ms-risk-bar { height: 5px; border-radius: 999px; background: rgba(15,23,42,0.16); overflow: hidden; }
        .ms-risk-bar span { display: block; height: 100%; border-radius: inherit; }
        .ms-note { display: flex; gap: 6px; align-items: center; color: var(--text-muted); margin-top: 22px; font-size: 12px; }
        .ms-divider { height: 1px; background: var(--border); margin: 28px 0 18px; }
        .ms-panel h3 { font-size: 13px; margin: 0 0 12px; color: var(--text-primary); }
        .ms-chart { height: 180px; }
        .ms-list { display: grid; gap: 12px; }
        .ms-issue-row, .ms-vuln-row, .ms-member-row { display: grid; grid-template-columns: auto 1fr auto auto; gap: 14px; align-items: center; border: 1px solid var(--border); border-radius: 8px; padding: 14px; background: var(--bg-soft); }
        .ms-vuln-row { grid-template-columns: auto 1fr; align-items: flex-start; }
        .ms-issue-icon { width: 40px; height: 40px; border-radius: 9px; display: grid; place-items: center; }
        .ms-issue-row strong, .ms-vuln-row strong, .ms-member-row strong { font-size: 13.5px; color: var(--text-primary); }
        .ms-issue-row p, .ms-vuln-row p, .ms-member-row p { margin: 4px 0 0; color: var(--text-secondary); font-size: 12.5px; }
        .ms-vuln-row small { color: var(--text-muted); display: block; margin-top: 5px; font-size: 11.5px; }
        .ms-vuln-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
        .ms-pill, .ms-impact { border-radius: 999px; padding: 4px 8px; font-size: 11px; font-weight: 800; white-space: nowrap; }
        .ms-callout { display: flex; gap: 16px; padding: 18px; margin-bottom: 18px; }
        .ms-callout.blue { background: rgba(59,130,246,0.08); border-color: rgba(59,130,246,0.24); color: #6366f1; }
        .ms-callout.green { background: rgba(34,197,94,0.08); border-color: rgba(34,197,94,0.24); color: #22c55e; }
        .ms-callout p { color: var(--text-secondary); margin: 8px 0 0; font-size: 13px; line-height: 1.55; }
        .ms-callout p svg { vertical-align: -2px; margin-right: 7px; color: #22c55e; }
        .ms-member-row { grid-template-columns: auto 1fr auto; }
        .ms-avatar { width: 38px; height: 38px; border-radius: 50%; background: linear-gradient(135deg, #6366f1, #a855f7); color: white; display: grid; place-items: center; font-weight: 850; overflow: hidden; font-size: 12px; }
        .ms-avatar img { width: 100%; height: 100%; object-fit: cover; }
        .ms-member-row small { display: flex; gap: 8px; margin-top: 6px; color: var(--text-muted); }
        .ms-high { color: #ef4444; } .ms-med { color: #f97316; } .ms-low { color: #ca8a04; }
        .ms-member-score { text-align: right; }
        .ms-member-score strong { display: block; font-size: 20px; }
        .ms-member-score span { color: var(--text-muted); font-size: 12px; }
        .ms-contributor-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 18px; }
        .ms-contributor-card { border: 1px solid var(--border); border-radius: 8px; padding: 15px; background: var(--bg-soft); }
        .ms-contributor-head { display: flex; align-items: center; gap: 10px; }
        .ms-contributor-head p { margin: 3px 0 0; color: var(--text-secondary); font-size: 12px; }
        .ms-impact { margin-left: auto; background: rgba(148,163,184,0.18); color: var(--text-secondary); }
        .ms-impact.positive { background: rgba(34,197,94,0.13); color: #16a34a; }
        .ms-impact.risky { background: rgba(239,68,68,0.13); color: #ef4444; }
        .ms-contributor-stats { display: grid; gap: 7px; border-top: 1px solid var(--border); margin-top: 14px; padding-top: 14px; font-size: 12px; color: var(--text-secondary); }
        .ms-contributor-stats span { display: flex; align-items: center; gap: 6px; }
        .ms-contributor-stats b { margin-left: auto; color: var(--text-primary); }
        .ms-group { display: grid; gap: 10px; margin-top: 18px; }
        .ms-about { display: flex; gap: 12px; padding: 16px 18px; background: rgba(59,130,246,0.08); border-color: rgba(59,130,246,0.24); color: #3b82f6; }
        .ms-about p { margin: 0; color: var(--text-secondary); font-size: 12.5px; line-height: 1.55; }
        .ms-empty, .ms-loading, .ms-error { color: var(--text-secondary); font-size: 13px; }
        .ms-error { color: #ef4444; }
        :root { --chart-grid: rgba(148,163,184,0.22); }
        @media (max-width: 860px) {
          .ms-hero, .ms-filter, .ms-callout { flex-direction: column; align-items: stretch; }
          .ms-risk-grid, .ms-hero-stats, .ms-repo-metrics, .ms-contributor-grid { grid-template-columns: 1fr; }
          .ms-filter select { min-width: 0; width: 100%; }
          .ms-score-ring { align-self: center; }
          .ms-issue-row { grid-template-columns: auto 1fr; }
          .ms-issue-row > b, .ms-issue-row > .ms-pill { justify-self: start; }
        }
      `}</style>
    </DashboardLayout>
  );
}
