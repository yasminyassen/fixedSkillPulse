import { useEffect, useMemo, useRef, useState, type CSSProperties, type RefObject } from "react";
import api from "../../api/auth";
import DashboardLayout from "../DashboardLayout";

interface RepoSummary {
  analysis_id: number;
  repo_name: string;
  branch: string;
}

interface SkillsSummary {
  repos: RepoSummary[];
}

interface LearningResource {
  title?: string;
  type?: string;
  provider?: string;
  url?: string;
  reason?: string;
}

interface LearningRecommendation {
  skill?: string;
  why_needed?: string;
  priority?: "High" | "Medium" | "Low";
  learning_objectives?: string[];
  estimated_effort?: string;
  expected_improvement?: string;
  resources?: LearningResource[];
}

interface LearningPlan {
  analysis_run_id?: number;
  repo?: string;
  branch?: string;
  recommendations?: LearningRecommendation[];
  generated_at?: string;
  rag_metadata?: { enabled?: boolean; retrieved_count?: number; retriever?: string };
}

const priorityStyles: Record<"High" | "Medium" | "Low", { fg: string; bg: string; border: string }> = {
  High: { fg: "#fb7185", bg: "rgba(251,113,133,0.12)", border: "rgba(251,113,133,0.35)" },
  Medium: { fg: "#f59e0b", bg: "rgba(245,158,11,0.12)", border: "rgba(245,158,11,0.35)" },
  Low: { fg: "#34d399", bg: "rgba(52,211,153,0.12)", border: "rgba(52,211,153,0.35)" },
};

const normalizePriority = (value?: string): "High" | "Medium" | "Low" => (
  value === "High" || value === "Medium" || value === "Low" ? value : "Medium"
);

const typeLabel = (value?: string) => {
  if (!value) return "Resource";
  const normalized = value.toLowerCase();
  if (normalized.includes("video")) return "Video";
  if (normalized.includes("book")) return "Book";
  if (normalized.includes("article")) return "Article";
  if (normalized.includes("course")) return "Course";
  if (normalized.includes("doc")) return "Docs";
  return value;
};

const resourceIcon = (value?: string) => {
  const kind = typeLabel(value);
  if (kind === "Book") return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19a2 2 0 0 1 2-2h12" /><path d="M4 5a2 2 0 0 1 2-2h12v16H6a2 2 0 0 0-2 2z" />
    </svg>
  );
  if (kind === "Video") return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="5" width="14" height="14" rx="2" /><path d="M17 9l4-2v10l-4-2" />
    </svg>
  );
  if (kind === "Article" || kind === "Docs") return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 4h12l4 4v12a2 2 0 0 1-2 2H4z" /><path d="M14 4v4h4" /><path d="M8 13h8" /><path d="M8 17h6" />
    </svg>
  );
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 20s8-4 8-10a4 4 0 0 0-8-2 4 4 0 0 0-8 2c0 6 8 10 8 10z" />
    </svg>
  );
};

export default function DeveloperLearning() {
  const role = localStorage.getItem("role") || "developer";
  const accent = role === "manager" ? "#8b5cf6" : role === "recruiter" ? "#a855f7" : "#6366f1";

  const [repos, setRepos] = useState<RepoSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [plan, setPlan] = useState<LearningPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [reposLoading, setReposLoading] = useState(true);
  const [error, setError] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) setDropdownOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  useEffect(() => {
    setReposLoading(true);
    api.get<SkillsSummary>("/analysis/skills/summary").then((res) => {
      const nextRepos = res.data.repos || [];
      setRepos(nextRepos);
      setSelectedId(nextRepos[0]?.analysis_id ?? null);
    }).catch(() => {
      setRepos([]);
      setSelectedId(null);
      setError(true);
    }).finally(() => setReposLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setPlan(null);
      return;
    }

    setLoading(true);
    setError(false);
    api.get<LearningPlan>(`/analysis/${selectedId}/learning-recommendations`)
      .then((res) => setPlan(res.data))
      .catch(() => {
        setPlan(null);
        setError(true);
      })
      .finally(() => setLoading(false));
  }, [selectedId]);

  const selected = repos.find((repo) => repo.analysis_id === selectedId) || repos[0];
  const recommendations = plan?.recommendations || [];
  const totalResources = useMemo(
    () => recommendations.reduce((sum, item) => sum + (item.resources?.length || 0), 0),
    [recommendations]
  );

  const chooseRepo = (id: number) => {
    setSelectedId(id);
    setDropdownOpen(false);
  };

  return (
    <DashboardLayout>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500;600;700&display=swap');

        .learning-page {
          min-height: 100vh;
          padding: 36px 40px 80px;
          color: var(--text-primary);
          font-family: 'DM Sans', system-ui, sans-serif;
          background: var(--bg-gradient);
        }
        .learning-shell { max-width: 1120px; margin: 0 auto; display: flex; flex-direction: column; gap: 22px; }
        .learning-eyebrow {
          display: inline-flex; align-items: center; gap: 8px;
          padding: 5px 14px; border-radius: 999px;
          border: 1px solid ${accent}40; background: ${accent}12;
          color: ${accent}; font-size: 11px; font-weight: 800;
          letter-spacing: 0.8px; text-transform: uppercase; width: fit-content;
        }
        .learning-card {
          background: var(--bg-card); border: 1px solid var(--border);
          border-radius: 18px; padding: 24px 28px;
          transition: border-color 0.2s, transform 0.2s, background 0.2s;
        }
        .learning-card:hover { border-color: var(--border-hover); }
        .learning-label {
          display: block; margin-bottom: 10px;
          color: rgba(167,139,250,0.95); font-size: 13px; font-weight: 800;
          text-transform: uppercase; letter-spacing: 0.8px;
        }
        .learning-hero {
          display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 18px; align-items: stretch;
        }
        .repo-trigger {
          width: 100%; border: 1px solid rgba(99,102,241,0.28);
          background: var(--bg-input); color: var(--text-primary);
          border-radius: 14px; padding: 13px 15px; cursor: pointer;
          display: flex; align-items: center; justify-content: space-between; gap: 14px;
          font-family: 'DM Sans', system-ui, sans-serif; text-align: left;
          transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
        }
        .repo-trigger:hover, .repo-trigger.open { border-color: ${accent}80; box-shadow: 0 0 0 4px ${accent}12; }
        .repo-menu {
          position: absolute; z-index: 50; top: calc(100% + 8px); left: 0; right: 0;
          background: #1a1a2e;
          border: 1px solid rgba(99,102,241,0.4);
          border-radius: 16px;
          box-shadow: 0 24px 60px rgba(0,0,0,0.6), 0 0 0 1px rgba(99,102,241,0.15), inset 0 1px 0 rgba(255,255,255,0.05);
          max-height: 280px; overflow: auto; padding: 8px;
          backdrop-filter: blur(20px);
        }
        .repo-option {
          width: 100%; border: none; cursor: pointer; border-radius: 12px;
          padding: 11px 12px; background: transparent; color: rgba(200,200,220,0.9);
          display: flex; align-items: center; justify-content: space-between; gap: 12px;
          font-family: 'DM Sans', system-ui, sans-serif; text-align: left;
          transition: background 0.15s, color 0.15s;
        }
        .repo-option:hover { background: rgba(99,102,241,0.15); color: #fff; }
        .repo-option.selected { background: rgba(99,102,241,0.2); color: #fff; }
        .metric-card {
          background: var(--bg-card-hover); border: 1px solid var(--border);
          border-radius: 16px; padding: 16px;
        }
        .metric-value { font-size: 32px; font-weight: 900; line-height: 1; color: var(--text-primary); }
        .priority-pill {
          display: inline-flex; align-items: center; gap: 6px;
          padding: 5px 12px; border-radius: 999px; font-size: 12px; font-weight: 800;
        }
        .learning-grid { display: grid; grid-template-columns: 1fr; gap: 16px; }
        .recommendation-card {
          position: relative; overflow: hidden;
          background: var(--bg-card); border: 1px solid var(--border);
          border-radius: 18px; padding: 0;
          transition: border-color 0.2s, transform 0.2s, background 0.2s;
          display: grid;
          grid-template-columns: 320px 1fr;
        }
        .recommendation-card:hover { border-color: var(--border-hover); transform: translateY(-2px); }
        .recommendation-card:before {
          content: ''; position: absolute; inset: 0 auto 0 0; width: 3px;
          background: linear-gradient(180deg, var(--accent), transparent);
        }
        .rec-card-left {
          padding: 22px 24px; border-right: 1px solid var(--border);
          display: flex; flex-direction: column; gap: 12px;
        }
        .rec-card-right {
          padding: 22px 24px;
          display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-content: start;
        }
        .rec-skill-icon {
          width: 44px; height: 44px; border-radius: 13px;
          display: grid; place-items: center; flex-shrink: 0;
          background: var(--bg-card-hover); border: 1px solid var(--border);
          color: var(--accent);
        }
        @media (max-width: 900px) {
          .recommendation-card { grid-template-columns: 1fr; }
          .rec-card-left { border-right: none; border-bottom: 1px solid var(--border); }
          .rec-card-right { grid-template-columns: 1fr; }
        }
        .info-block {
          background: var(--bg-card-hover); border: 1px solid var(--border);
          border-radius: 14px; padding: 13px 14px;
        }
        .resource-card {
          display: flex; gap: 13px; align-items: flex-start;
          padding: 14px; border: 1px solid var(--border); border-radius: 14px;
          background: var(--bg-card-hover); transition: border-color 0.2s, transform 0.2s, background 0.2s;
          text-decoration: none; color: inherit;
        }
        .resource-card:hover { border-color: var(--border-hover); background: var(--bg-card); transform: translateY(-1px); }
        .resource-icon {
          width: 42px; height: 42px; border-radius: 12px;
          display: grid; place-items: center; flex-shrink: 0;
          background: var(--bg-card); color: ${accent}; border: 1px solid var(--border);
        }
        .chip {
          display: inline-flex; align-items: center; gap: 5px;
          padding: 4px 10px; border-radius: 999px; font-size: 13px;
          color: rgba(190,190,215,0.95); background: var(--bg-card-hover); border: 1px solid var(--border);
        }
        .empty-state {
          border: 1px dashed var(--border-hover); border-radius: 18px; padding: 28px;
          background: var(--bg-card); color: var(--text-muted); text-align: center;
        }
        .sk {
          background: linear-gradient(90deg, var(--bg-card) 25%, var(--bg-card-hover) 50%, var(--bg-card) 75%);
          background-size: 400% 100%; animation: shimmer 1.4s ease-in-out infinite; border-radius: 10px;
        }
        @keyframes shimmer { 0%{background-position:100% 50%} 100%{background-position:0% 50%} }
        @media (max-width: 900px) {
          .learning-page { padding: 28px 20px 60px; }
          .learning-hero { grid-template-columns: 1fr; }
        }
      `}</style>

      <div className="learning-page">
        <div className="learning-shell">
          <header>
            <div className="learning-eyebrow">Learning Radar</div>
            <h1 style={{ fontFamily: "'Syne', sans-serif", fontSize: 30, fontWeight: 800, letterSpacing: "-0.6px", margin: "12px 0 6px" }}>
              Personalized Learning Recommendations
            </h1>
            <p style={{ color: "var(--text-muted)", margin: 0, maxWidth: 760, lineHeight: 1.65, fontSize: 15 }}>
              A focused learning path based on your repository analysis, suggested resources, and the highest-impact skills to improve next.
            </p>
          </header>

          <section className="learning-hero">
            <div className="learning-card">
              <label className="learning-label">Repository</label>
              <CustomRepoDropdown
                repos={repos}
                selected={selected}
                selectedId={selectedId}
                loading={reposLoading}
                open={dropdownOpen}
                setOpen={setDropdownOpen}
                onChoose={chooseRepo}
                refEl={dropdownRef}
                accent={accent}
              />
              {selected && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 }}>
                  <span className="chip">Repo: {selected.repo_name}</span>
                  <span className="chip">Branch: {selected.branch}</span>
                  {selectedId && <span className="chip">Analysis #{selectedId}</span>}
                </div>
              )}
            </div>

            <div className="learning-card" style={{ display: "flex", flexDirection: "column", justifyContent: "center", gap: 10 }}>
              <label className="learning-label">Analysis Overview</label>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div className="metric-card">
                  <div className="metric-value">{recommendations.length}</div>
                  <div style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 6 }}>Focus areas</div>
                </div>
                <div className="metric-card">
                  <div className="metric-value">{totalResources}</div>
                  <div style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 6 }}>Resources</div>
                </div>
              </div>
            </div>
          </section>

          {error && <StateCard title="Could not load learning recommendations" text="Please try again or run a new analysis." />}
          {!error && (reposLoading || loading) && <LoadingState />}
          {!error && !reposLoading && repos.length === 0 && <StateCard title="No analyzed repositories found" text="Run an analysis first to generate your personalized learning plan." />}
          {!error && !reposLoading && !loading && repos.length > 0 && recommendations.length === 0 && <StateCard title="No recommendations yet" text="This analysis does not have learning recommendations available yet." />}

          {!error && !reposLoading && !loading && recommendations.length > 0 && (
            <div className="learning-grid">
              {recommendations.map((item, index) => (
                <RecommendationCard key={`${item.skill || "recommendation"}-${index}`} item={item} accent={accent} />
              ))}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}

function CustomRepoDropdown({ repos, selected, selectedId, loading, open, setOpen, onChoose, refEl, accent }: {
  repos: RepoSummary[];
  selected?: RepoSummary;
  selectedId: number | null;
  loading: boolean;
  open: boolean;
  setOpen: (value: boolean) => void;
  onChoose: (id: number) => void;
  refEl: RefObject<HTMLDivElement | null>;
  accent: string;
}) {
  return (
    <div ref={refEl} style={{ position: "relative" }}>
      <button
        type="button"
        className={`repo-trigger ${open ? "open" : ""}`}
        disabled={loading || repos.length === 0}
        onClick={() => setOpen(!open)}
      >
        <span style={{ minWidth: 0 }}>
          <span style={{ display: "block", fontWeight: 800, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {loading ? "Loading repositories..." : selected?.repo_name || "Select a repository"}
          </span>
          <span style={{ display: "block", color: "var(--text-muted)", fontSize: 12.5, marginTop: 4 }}>
            {selected?.branch ? `Branch: ${selected.branch}` : "Choose an analyzed repository"}
          </span>
        </span>
        <span style={{ color: accent, transform: open ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s", flexShrink: 0 }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6" /></svg>
        </span>
      </button>

      {open && (
        <div className="repo-menu">
          {repos.map((repo) => (
            <button
              type="button"
              key={repo.analysis_id}
              className={`repo-option ${repo.analysis_id === selectedId ? "selected" : ""}`}
              onClick={() => onChoose(repo.analysis_id)}
            >
              <span style={{ minWidth: 0 }}>
                <span style={{ display: "block", fontWeight: 800, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{repo.repo_name}</span>
                <span style={{ display: "block", color: "var(--text-muted)", fontSize: 12, marginTop: 3 }}>Branch: {repo.branch}</span>
              </span>
              {repo.analysis_id === selectedId && <span style={{ color: accent, fontWeight: 900 }}>✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function RecommendationCard({ item, accent }: { item: LearningRecommendation; accent: string }) {
  const priority = normalizePriority(item.priority);
  const styles = priorityStyles[priority];
  const resources = item.resources || [];

  const skillIcon = (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
    </svg>
  );

  const clockIcon = (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
    </svg>
  );

  const targetIcon = (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>
    </svg>
  );

  return (
    <article className="recommendation-card" style={{ "--accent": accent } as CSSProperties}>
      {/* LEFT: skill identity + effort + improvement + objectives */}
      <div className="rec-card-left">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div className="rec-skill-icon" style={{ color: styles.fg, background: styles.bg, borderColor: styles.border }}>{skillIcon}</div>
          <span className="priority-pill" style={{ color: styles.fg, background: styles.bg, border: `1px solid ${styles.border}`, flexShrink: 0 }}>{priority}</span>
        </div>
        <h2 style={{ margin: 0, fontFamily: "'Syne', sans-serif", fontSize: 20, letterSpacing: "-0.3px", lineHeight: 1.25 }}>{item.skill || "Learning focus"}</h2>
        {item.why_needed && <p style={{ color: "rgba(180,180,210,0.95)", lineHeight: 1.7, margin: 0, fontSize: 14 }}>{item.why_needed}</p>}

        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 4 }}>
          <div className="info-block">
            <div style={{ display: "flex", alignItems: "center", gap: 6, color: "rgba(167,139,250,0.9)", fontSize: 11.5, textTransform: "uppercase", letterSpacing: "0.7px", fontWeight: 800, marginBottom: 5 }}>
              {clockIcon} Estimated Effort
            </div>
            <div style={{ color: "rgba(210,210,230,0.95)", fontSize: 14 }}>{item.estimated_effort || "Not specified"}</div>
          </div>
          <div className="info-block">
            <div style={{ display: "flex", alignItems: "center", gap: 6, color: "rgba(167,139,250,0.9)", fontSize: 11.5, textTransform: "uppercase", letterSpacing: "0.7px", fontWeight: 800, marginBottom: 5 }}>
              {targetIcon} Expected Improvement
            </div>
            <div style={{ color: "rgba(210,210,230,0.95)", fontSize: 14 }}>{item.expected_improvement || "Not specified"}</div>
          </div>
        </div>

        {item.learning_objectives?.length ? (
          <div style={{ marginTop: 4 }}>
            <label className="learning-label">Objectives</label>
            <ul style={{ margin: 0, paddingLeft: 20, color: "rgba(180,180,210,0.95)", lineHeight: 1.75, fontSize: 14 }}>
              {item.learning_objectives.map((objective) => <li key={objective}>{objective}</li>)}
            </ul>
          </div>
        ) : null}
      </div>

      {/* RIGHT: resources full width */}
      <div className="rec-card-right" style={{ gridTemplateColumns: "1fr" }}>
        {resources.length > 0 ? (
          <div>
            <label className="learning-label">Resources</label>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {resources.map((resource, index) => <ResourceCard key={`${resource.title || "resource"}-${resource.url || index}`} resource={resource} />)}
            </div>
          </div>
        ) : (
          <p style={{ color: "rgba(150,150,170,0.8)", margin: 0, fontSize: 14 }}>No resources available for this recommendation.</p>
        )}
      </div>
    </article>
  );
}

function ResourceCard({ resource }: { resource: LearningResource }) {
  const content = (
    <>
      <div className="resource-icon">{resourceIcon(resource.type)}</div>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <strong style={{ color: "var(--text-primary)", overflowWrap: "anywhere" }}>{resource.title || "Resource"}</strong>
          {resource.url && <span style={{ color: "#60a5fa", fontSize: 12, fontWeight: 800, whiteSpace: "nowrap" }}>Open →</span>}
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 7 }}>
          {resource.provider && <span className="chip">{resource.provider}</span>}
          <span className="chip">{typeLabel(resource.type)}</span>
        </div>
        {resource.reason && <p style={{ color: "rgba(180,180,210,0.95)", fontSize: 14, lineHeight: 1.55, margin: "9px 0 0" }}>{resource.reason}</p>}
      </div>
    </>
  );

  if (resource.url) {
    return <a className="resource-card" href={resource.url} target="_blank" rel="noreferrer">{content}</a>;
  }
  return <div className="resource-card">{content}</div>;
}

function StateCard({ title, text }: { title: string; text: string }) {
  return (
    <section className="empty-state">
      <h3 style={{ margin: "0 0 6px", color: "var(--text-primary)", fontFamily: "'Syne', sans-serif" }}>{title}</h3>
      <p style={{ margin: 0 }}>{text}</p>
    </section>
  );
}

function LoadingState() {
  return (
    <section className="learning-card" style={{ display: "grid", gap: 14 }}>
      <div className="sk" style={{ height: 18, width: "40%" }} />
      <div className="sk" style={{ height: 90, width: "100%" }} />
      <div className="sk" style={{ height: 90, width: "100%" }} />
    </section>
  );
}
