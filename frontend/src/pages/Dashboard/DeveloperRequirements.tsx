import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Code2,
  FileText,
  GitBranch,
  RefreshCw,
  Search,
  Target,
  XCircle,
} from "lucide-react";
import DashboardLayout from "../DashboardLayout";
import api from "../../api/auth";

type RepoRow = {
  repo_id: number;
  repo_name: string;
  full_name?: string;
  branch?: string;
  status?: string;
};

type Evidence = {
  file_path?: string;
  symbol_name?: string;
  symbol_type?: string;
  start_line?: number;
  end_line?: number;
  chunk_id?: string;
  excerpt?: string;
};

type TaskCoverage = {
  status?: "COVERED" | "PARTIALLY_COVERED" | "NOT_COVERED" | string | null;
  score?: number | null;
  confidence?: number | null;
  reason?: string | null;
  matched_chunk_ids?: string[];
};

type Task = {
  task_id?: number;
  id?: number;
  story_id: number;
  description: string;
  type?: string;
  status?: string;
  ac_ids?: number[];
  due_date?: string | null;
  task_coverage?: TaskCoverage | null;
  task_evidence?: Evidence[];
};

type AcceptanceCriterion = {
  id?: number;
  ac_id?: number;
  text?: string;
  status?: string;
  confidence?: number;
};

type Story = {
  story_id: number;
  story_code?: string;
  title: string;
  description?: string;
  priority?: string;
  tasks: Task[];
  acceptance_criteria: AcceptanceCriterion[];
};

const taskId = (task: Task) => task.task_id ?? task.id ?? 0;
const statusOf = (task: Task, coverageDetected = false) => task.task_coverage?.status || (coverageDetected ? "COVERAGE_UNAVAILABLE" : "NOT_EVALUATED");
const confidencePct = (value?: number | null) => value == null ? "N/A" : `${Math.round(Number(value) * 100)}%`;
const withTimeout = <T,>(promise: Promise<T>, ms = 10000): Promise<T> =>
  Promise.race([
    promise,
    new Promise<T>((_, reject) => window.setTimeout(() => reject(new Error("Request timed out")), ms)),
  ]);

const COVERAGE_CFG: Record<string, { label: string; color: string; bg: string; border: string; icon: any }> = {
  COVERED: { label: "Covered", color: "#0f9f8f", bg: "#e9fbf7", border: "#9ee8dc", icon: CheckCircle2 },
  PARTIALLY_COVERED: { label: "Partial", color: "#b77900", bg: "#fff8df", border: "#f6d56b", icon: AlertCircle },
  NOT_COVERED: { label: "Not Implemented", color: "#d72f4b", bg: "#fff0f3", border: "#ffb6c2", icon: XCircle },
  NOT_EVALUATED: { label: "Not Evaluated", color: "#64748b", bg: "#f1f5f9", border: "#d9e2ec", icon: CircleDot },
  COVERAGE_UNAVAILABLE: { label: "Coverage unavailable for this task", color: "#a78bfa", bg: "rgba(167,139,250,0.12)", border: "rgba(167,139,250,0.24)", icon: AlertCircle },
};

function coverageConfig(status?: string | null) {
  return COVERAGE_CFG[status || "NOT_EVALUATED"] || COVERAGE_CFG.NOT_EVALUATED;
}

function CoverageBadge({ status }: { status?: string | null }) {
  const cfg = coverageConfig(status);
  const Icon = cfg.icon;
  return (
    <span className="devreq-badge" style={{ color: cfg.color, background: cfg.bg, borderColor: cfg.border }}>
      <Icon size={13} />
      {cfg.label}
    </span>
  );
}

function MetricCard({ label, value, icon, tone = "neutral" }: { label: string; value: number | string; icon: any; tone?: "neutral" | "good" | "warn" | "bad" | "blue" }) {
  const Icon = icon;
  return (
    <div className={`devreq-card devreq-metric devreq-${tone}`}>
      <div className="devreq-metric-icon"><Icon size={18} /></div>
      <div className="devreq-metric-value">{value}</div>
      <div className="devreq-muted">{label}</div>
    </div>
  );
}

function taskCoverageScore(task: Task, coverageDetected: boolean) {
  if (typeof task.task_coverage?.score === "number") return task.task_coverage.score;
  return statusOf(task, coverageDetected) === "COVERED" ? 1 : statusOf(task, coverageDetected) === "PARTIALLY_COVERED" ? 0.5 : 0;
}

function storyTaskCoverage(story: Story, coverageDetected: boolean) {
  if (!story.tasks?.length) return 0;
  return story.tasks.reduce((sum, task) => sum + taskCoverageScore(task, coverageDetected), 0) / story.tasks.length;
}

function evidenceLabel(ev: Evidence) {
  const symbol = ev.symbol_name || ev.symbol_type || "code chunk";
  const lines = ev.start_line || ev.end_line ? `lines ${ev.start_line || "?"}-${ev.end_line || "?"}` : "line unknown";
  return `${symbol} · ${lines}`;
}

function statusSearchText(status: string) {
  const cfg = coverageConfig(status);
  return `${status} ${cfg.label}`.toLowerCase();
}

function taskSearchText(task: Task, coverageDetected: boolean) {
  const coverage = task.task_coverage;
  const evidenceText = (task.task_evidence || [])
    .map(ev => `${ev.file_path || ""} ${ev.symbol_name || ""} ${ev.symbol_type || ""} ${ev.excerpt || ""}`)
    .join(" ");
  return [
    task.description,
    statusSearchText(statusOf(task, coverageDetected)),
    coverage?.reason || "",
    evidenceText,
  ].join(" ").toLowerCase();
}

function TaskEvidence({ task }: { task: Task }) {
  const evidence = task.task_evidence || [];
  if (!evidence.length) {
    return <div className="devreq-empty-soft">No implementation evidence has been stored for this task yet.</div>;
  }
  return (
    <div className="devreq-evidence-list">
      {evidence.map((ev, idx) => (
        <div className="devreq-evidence" key={`${ev.chunk_id || ev.file_path}-${idx}`}>
          <div className="devreq-evidence-head">
            <div>
              <div className="devreq-file"><Code2 size={13} /> {ev.file_path || "Unknown file"}</div>
              <div className="devreq-muted">{evidenceLabel(ev)}</div>
            </div>
          </div>
          {ev.excerpt && <pre className="devreq-code">{ev.excerpt}</pre>}
        </div>
      ))}
    </div>
  );
}

function StoryCard({
  story,
  expanded,
  coverageDetected,
  expandedTaskIds,
  onToggle,
  onToggleTaskEvidence,
}: {
  story: Story;
  expanded: boolean;
  coverageDetected: boolean;
  expandedTaskIds: Set<number>;
  onToggle: () => void;
  onToggleTaskEvidence: (id: number) => void;
}) {
  const coverage = storyTaskCoverage(story, coverageDetected);
  const coveredTasks = (story.tasks || []).filter(task => statusOf(task, coverageDetected) === "COVERED").length;
  return (
    <article className="devreq-card devreq-story">
      <button className="devreq-story-main" onClick={onToggle}>
        <div className="devreq-story-id">{story.story_code || `Story #${story.story_id}`}</div>
        <div className="devreq-story-title">{story.title}</div>
        <div className="devreq-story-stats">
          <span>{story.tasks?.length || 0} tasks</span>
          <span>{coveredTasks}/{story.tasks?.length || 0} covered</span>
        </div>
        <div className="devreq-progress">
          <div style={{ width: `${Math.round(coverage * 100)}%` }} />
        </div>
      </button>
      <div className="devreq-story-side">
        <div className="devreq-coverage-number">{Math.round(coverage * 100)}%</div>
        <div className="devreq-muted">task coverage</div>
        <button className="devreq-icon-btn" onClick={onToggle} aria-label={expanded ? "Collapse story" : "Expand story"}>
          {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        </button>
      </div>

      {expanded && (
        <div className="devreq-details">
          {story.description && <p className="devreq-description">{story.description}</p>}

          <section>
            <h3>My Tasks</h3>
            <div className="devreq-task-list">
              {(story.tasks || []).map(task => {
                const result = task.task_coverage;
                return (
                  <div className="devreq-task" key={taskId(task)}>
                    <div className="devreq-task-top">
                      <div>
                        <div className="devreq-task-title">{task.description}</div>
                        <div className="devreq-task-meta">
                          <span>Confidence: {confidencePct(result?.confidence)}</span>
                        </div>
                      </div>
                      <div className="devreq-task-actions">
                        <CoverageBadge status={statusOf(task, coverageDetected)} />
                      </div>
                    </div>

                    <div className="devreq-task-summary">
                      <Target size={15} />
                      <span>{result?.reason || "Task coverage has not been evaluated for this run yet."}</span>
                    </div>

                    <button className="devreq-btn slim" onClick={() => onToggleTaskEvidence(taskId(task))}>
                      {expandedTaskIds.has(taskId(task)) ? "Hide Evidence" : "View Evidence"}
                    </button>
                    {expandedTaskIds.has(taskId(task)) && <TaskEvidence task={task} />}
                  </div>
                );
              })}
            </div>
          </section>
        </div>
      )}
    </article>
  );
}

export default function DeveloperRequirements() {
  const [repos, setRepos] = useState<RepoRow[]>([]);
  const [selectedRepo, setSelectedRepo] = useState("");
  const [assignments, setAssignments] = useState<any>(null);
  const [coverage, setCoverage] = useState<any>(null);
  const [stories, setStories] = useState<Story[]>([]);
  const [expandedStoryIds, setExpandedStoryIds] = useState<Set<number>>(new Set());
  const [expandedTaskIds, setExpandedTaskIds] = useState<Set<number>>(new Set());
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(false);
  const [repoLoading, setRepoLoading] = useState(false);
  const [repoLoadError, setRepoLoadError] = useState("");
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok });
    window.setTimeout(() => setToast(null), 3000);
  };

  const loadRepos = useCallback(async () => {
    setRepoLoading(true);
    setRepoLoadError("");
    try {
      const res = await withTimeout(api.get("/requirements/repositories/developer/assigned"));
      const assignedRepos = res.data || [];
      setRepos(assignedRepos);
      setSelectedRepo(prev =>
        prev && assignedRepos.some((repo: RepoRow) => String(repo.repo_id) === prev) ? prev : ""
      );
      return assignedRepos as RepoRow[];
    } catch (err: any) {
      setRepos([]);
      setSelectedRepo("");
      const detail = err?.response?.data?.detail || err?.message || "Failed to load assigned repositories";
      setRepoLoadError(String(detail));
      showToast(String(detail), false);
      return [] as RepoRow[];
    } finally {
      setRepoLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRepos();
  }, [loadRepos]);

  const mergeStories = (assignmentStories: Story[], coverageStories: Story[]) => {
    const coverageById = new Map((coverageStories || []).map(story => [story.story_id, story]));
    return (assignmentStories || []).map(story => {
      const covered = coverageById.get(story.story_id);
      if (!covered) return story;
      const coverageAcs = new Map((covered.acceptance_criteria || []).map((ac: any) => [ac.ac_id, ac]));
      const coverageTasks = new Map((covered.tasks || []).map((task: Task) => [taskId(task), task]));
      return {
        ...story,
        tasks: (story.tasks || []).map(task => {
          const coverageTask = coverageTasks.get(taskId(task));
          return {
            ...task,
            task_coverage: coverageTask?.task_coverage || task.task_coverage || null,
            task_evidence: coverageTask?.task_evidence || task.task_evidence || [],
          };
        }),
        acceptance_criteria: (story.acceptance_criteria || []).map((ac: any) => coverageAcs.get(ac.id) || ac),
      };
    });
  };

  const loadData = useCallback(async (repoId: string) => {
    setLoading(true);
    try {
      const [assignmentsRes, coverageRes] = await Promise.all([
        api.get(`/requirements/repositories/${repoId}/developer`).catch(() => ({ data: null })),
        api.get(`/requirements/coverage/repositories/${repoId}/developer`).catch(() => ({ data: null })),
      ]);
      setAssignments(assignmentsRes.data);
      setCoverage(coverageRes.data);
      setStories(mergeStories(assignmentsRes.data?.stories || [], coverageRes.data?.stories || []));
      setExpandedStoryIds(new Set());
      setExpandedTaskIds(new Set());
    } catch {
      showToast("Failed to load assigned requirements", false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!selectedRepo) {
      setAssignments(null);
      setCoverage(null);
      setStories([]);
      return;
    }
    loadData(selectedRepo);
  }, [selectedRepo, loadData]);

  const refresh = async () => {
    const assignedRepos = await loadRepos();
    const stillAssigned = selectedRepo && assignedRepos.some((repo: RepoRow) => String(repo.repo_id) === selectedRepo);
    if (stillAssigned) {
      loadData(selectedRepo);
    } else {
      setAssignments(null);
      setCoverage(null);
      setStories([]);
    }
  };

  const toggleStory = (id: number) => {
    setExpandedStoryIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleTaskEvidence = (id: number) => {
    setExpandedTaskIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const coverageDetected = Boolean(coverage?.run?.id);

  const filteredStories = useMemo(() => {
    const q = query.trim().toLowerCase();
    return stories
      .map(story => {
        const storyText = [
          story.title,
          story.story_code || "",
          story.description || "",
        ].join(" ").toLowerCase();
        const storyMatchesQuery = Boolean(q) && storyText.includes(q);
        const tasks = (story.tasks || []).filter(task => {
          const matchesStatus = statusFilter === "all" || statusOf(task, coverageDetected) === statusFilter;
          if (!matchesStatus) return false;
          if (!q) return true;
          return storyMatchesQuery || taskSearchText(task, coverageDetected).includes(q);
        });
        return { ...story, tasks };
      })
      .filter(story => (story.tasks || []).length > 0);
  }, [stories, query, statusFilter, coverageDetected]);

  const allTasks = useMemo(() => stories.flatMap(story => story.tasks || []), [stories]);
  const taskCounts = useMemo(() => ({
    covered: allTasks.filter(task => statusOf(task, coverageDetected) === "COVERED").length,
    partial: allTasks.filter(task => statusOf(task, coverageDetected) === "PARTIALLY_COVERED").length,
    missing: allTasks.filter(task => statusOf(task, coverageDetected) === "NOT_COVERED").length,
  }), [allTasks, coverageDetected]);

  return (
    <DashboardLayout>
      <style>{`
        .devreq-page{min-height:100vh;background:var(--bg-base);color:white;padding:28px clamp(18px,3vw,42px);font-family:'Inter',sans-serif}
        .devreq-title{font-family:'Inter',sans-serif;font-size:26px;margin:0;color:white}
        .devreq-subtitle{margin:7px 0 0;color:rgba(255,255,255,.48);font-size:13px;line-height:1.5}
        .devreq-card{background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.07);border-radius:12px}
        .rq-panel{background:rgba(255,255,255,0.025);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:14px}
        .devreq-toolbar{display:grid;grid-template-columns:minmax(220px,320px) 1fr 190px auto;gap:14px;align-items:end;padding:14px;margin:22px 0 18px}
        .devreq-label{font-size:10px;font-weight:900;color:rgba(255,255,255,.36);text-transform:uppercase;letter-spacing:.7px;margin-bottom:7px}
        .rq-input,.rq-select{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:9px;color:white;font-family:'Inter',sans-serif;font-size:13px;outline:none;padding:8px 10px;box-sizing:border-box}
        .rq-input:focus,.rq-select:focus{border-color:#6366f180;background:rgba(255,255,255,0.06)}
        .rq-select option{background:#1a1a2e;color:white}
        .rq-select{height:38px;width:100%}.rq-input{height:38px;width:100%}
        .devreq-search{position:relative}.devreq-search svg{position:absolute;left:10px;top:35px;color:rgba(255,255,255,.35)}.devreq-search input{padding-left:30px}
        .devreq-btn{height:38px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.04);border-radius:9px;color:rgba(255,255,255,.74);display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:0 13px;font-weight:800;font-size:12px;cursor:pointer}
        .devreq-btn:hover{border-color:rgba(99,102,241,.45);background:rgba(255,255,255,.065);color:white}
        .devreq-btn.slim{height:34px;margin-top:2px;width:max-content}
        .rq-btn-ghost,.rq-btn-primary{display:inline-flex;align-items:center;gap:7px;padding:8px 13px;border-radius:9px;font-family:'Inter',sans-serif;font-size:12px;font-weight:800;cursor:pointer}
        .rq-btn-ghost{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);color:rgba(255,255,255,0.7)}
        .rq-btn-primary{background:#7c3aed;border:1px solid #7c3aed;color:white}
        .devreq-metrics{display:grid;grid-template-columns:repeat(5,minmax(130px,1fr));gap:16px;margin-bottom:24px}
        .devreq-metric{padding:18px;min-height:112px}.devreq-metric-icon{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;margin-bottom:14px}
        .devreq-metric-value{font-size:25px;font-weight:900;letter-spacing:0;color:white}
        .devreq-neutral .devreq-metric-icon{background:rgba(167,139,250,.14);color:#a78bfa}.devreq-blue .devreq-metric-icon{background:rgba(96,165,250,.14);color:#60a5fa}.devreq-good .devreq-metric-icon{background:rgba(52,211,153,.14);color:#34d399}.devreq-warn .devreq-metric-icon{background:rgba(251,191,36,.14);color:#fbbf24}.devreq-bad .devreq-metric-icon{background:rgba(248,113,113,.14);color:#f87171}
        .devreq-muted{color:rgba(255,255,255,.45);font-size:12px;line-height:1.45}
        .devreq-section{padding:22px;margin-bottom:22px}.devreq-section-head{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:18px}
        .devreq-section h2{margin:0;font-size:18px;color:white}.devreq-story-list{display:grid;gap:12px}
        .devreq-story{display:grid;grid-template-columns:1fr 150px;overflow:hidden}.devreq-story-main{border:0;background:transparent;text-align:left;padding:18px;cursor:pointer}
        .devreq-story-id{display:inline-flex;border:1px solid rgba(255,255,255,.08);border-radius:7px;padding:3px 8px;color:#a78bfa;font-size:11px;font-weight:900;background:rgba(167,139,250,.1);margin-bottom:10px}
        .devreq-story-title{font-size:15px;font-weight:900;color:white;margin-bottom:7px}.devreq-story-stats{display:flex;gap:14px;flex-wrap:wrap;color:rgba(255,255,255,.45);font-size:12px;margin-bottom:12px}
        .devreq-progress{height:8px;border-radius:999px;background:rgba(255,255,255,.08);overflow:hidden}.devreq-progress div{height:100%;border-radius:999px;background:#34d399}
        .devreq-story-side{border-left:1px solid rgba(255,255,255,.07);display:grid;grid-template-columns:1fr 42px;align-content:center;gap:2px;padding:16px}
        .devreq-coverage-number{font-size:26px;font-weight:900;color:#34d399}.devreq-icon-btn{grid-row:1 / span 2;grid-column:2;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.04);border-radius:9px;height:36px;width:36px;display:grid;place-items:center;cursor:pointer;color:rgba(255,255,255,.7)}
        .devreq-details{grid-column:1 / -1;border-top:1px solid rgba(255,255,255,.07);padding:20px;background:rgba(0,0,0,.16);display:grid;gap:20px}
        .devreq-description{margin:0;color:rgba(255,255,255,.48);line-height:1.6;font-size:13px}.devreq-details h3{margin:0 0 12px;font-size:15px;color:white}
        .devreq-task-list{display:grid;gap:12px}.devreq-task{border:1px solid rgba(255,255,255,.07);border-radius:10px;background:rgba(255,255,255,.025);padding:16px}
        .devreq-task-top{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.devreq-task-title{font-size:14px;font-weight:900;color:white;line-height:1.45}
        .devreq-task-meta{display:flex;gap:12px;flex-wrap:wrap;color:rgba(255,255,255,.45);font-size:12px;margin-top:7px}.devreq-task-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
        .devreq-badge{display:inline-flex;align-items:center;gap:6px;border:1px solid;border-radius:999px;padding:5px 9px;font-size:12px;font-weight:900;white-space:nowrap}
        .devreq-task-summary{display:flex;gap:9px;align-items:flex-start;margin:14px 0;color:rgba(255,255,255,.56);background:rgba(0,0,0,.18);border:1px solid rgba(255,255,255,.06);border-radius:9px;padding:10px;font-size:13px;line-height:1.5}
        .devreq-evidence-list{display:grid;gap:10px;margin-top:12px}.devreq-evidence{border:1px solid rgba(255,255,255,.07);border-radius:9px;background:rgba(0,0,0,.18);padding:12px}.devreq-evidence-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
        .devreq-file{display:flex;align-items:center;gap:7px;font-size:13px;font-weight:900;color:rgba(255,255,255,.86)}
        .devreq-code{margin:10px 0 0;white-space:pre-wrap;word-break:break-word;background:rgba(0,0,0,.22);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:10px;color:rgba(255,255,255,.54);font-size:12px;line-height:1.45;max-height:180px;overflow:auto}
        .devreq-empty{padding:28px;text-align:center;color:rgba(255,255,255,.5)}.devreq-empty-soft{border:1px dashed rgba(255,255,255,.14);border-radius:9px;background:rgba(255,255,255,.025);color:rgba(255,255,255,.52);padding:12px;font-size:13px}
        .devreq-toast{position:fixed;right:24px;top:20px;z-index:500;padding:11px 14px;border-radius:10px;font-weight:800;font-size:13px;background:#10101b;border:1px solid rgba(255,255,255,.1)}
        @media (max-width:1100px){.devreq-toolbar{grid-template-columns:1fr 1fr}.devreq-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.devreq-story{grid-template-columns:1fr}.devreq-story-side{border-left:0;border-top:1px solid rgba(255,255,255,.07);grid-template-columns:1fr 42px}}
        @media (max-width:680px){.devreq-page{padding:20px 14px}.devreq-toolbar,.devreq-metrics{grid-template-columns:1fr}.devreq-task-top{display:grid}.devreq-task-actions{justify-content:flex-start}}
      `}</style>

      {toast && (
        <div className="devreq-toast" style={{ color: toast.ok ? "#0f9f8f" : "#d72f4b" }}>
          {toast.msg}
        </div>
      )}

      <main className="devreq-page">
        <header>
          <h1 className="devreq-title">My Requirements</h1>
          <p className="devreq-subtitle">Track your assigned implementation work, task coverage, matched code, and evaluator reasoning.</p>
        </header>

        {!selectedRepo ? (
          <div className="rq-panel" style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 18 }}>
            <select className="rq-select" value={selectedRepo} onChange={e => setSelectedRepo(e.target.value)} disabled={repoLoading} style={{ minWidth: 250, width: 312, flex: "0 0 312px" }}>
              <option value="">{repoLoading ? "Loading repositories" : "Select repository"}</option>
              {repos.map(repo => (
                <option key={repo.repo_id} value={repo.repo_id}>{repo.repo_name || repo.full_name}</option>
              ))}
            </select>
            <button className="rq-btn-ghost" onClick={refresh}><RefreshCw size={13} /> Refresh</button>
          </div>
        ) : (
          <section className="devreq-card devreq-toolbar">
            <div>
              <div className="devreq-label">Repository</div>
              <select className="rq-select" value={selectedRepo} onChange={e => setSelectedRepo(e.target.value)} disabled={repoLoading}>
                <option value="">{repoLoading ? "Loading repositories" : "Select repository"}</option>
                {repos.map(repo => (
                  <option key={repo.repo_id} value={repo.repo_id}>{repo.repo_name || repo.full_name}</option>
                ))}
              </select>
            </div>
            <div className="devreq-search">
              <div className="devreq-label">Search</div>
              <Search size={15} />
              <input className="rq-input" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search tasks, status, reasoning, files, or symbols" />
            </div>
            <div>
              <div className="devreq-label">Task Coverage</div>
              <select className="rq-select" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
                <option value="all">All Statuses</option>
                <option value="COVERED">Covered</option>
                <option value="PARTIALLY_COVERED">Partial</option>
                <option value="NOT_COVERED">Not Implemented</option>
                <option value="NOT_EVALUATED">Not Evaluated</option>
                <option value="COVERAGE_UNAVAILABLE">Coverage unavailable</option>
              </select>
            </div>
            <button className="devreq-btn" onClick={refresh}><RefreshCw size={15} /> Refresh</button>
          </section>
        )}

        {!repoLoading && !repos.length && (
          <section className="devreq-card devreq-empty">
            <GitBranch size={22} />
            <h2>{repoLoadError ? "Could not load assigned repositories" : "No assigned requirement repositories"}</h2>
            <p>{repoLoadError || "You will only see repositories where a manager has assigned technical tasks to you."}</p>
          </section>
        )}

        {selectedRepo && (
          <>
            <section className="devreq-metrics">
              <MetricCard label="Assigned Implementation Work" value={assignments?.summary?.assigned_stories ?? stories.length} icon={Target} tone="neutral" />
              <MetricCard label="Assigned Tasks" value={assignments?.summary?.assigned_tasks ?? allTasks.length} icon={FileText} tone="blue" />
              <MetricCard label="Covered Tasks" value={taskCounts.covered} icon={CheckCircle2} tone="good" />
              <MetricCard label="Partial Tasks" value={taskCounts.partial} icon={AlertCircle} tone="warn" />
              <MetricCard label="Not Implemented Tasks" value={taskCounts.missing} icon={XCircle} tone="bad" />
            </section>

            {!loading && !coverageDetected && allTasks.length > 0 && (
              <div className="devreq-card devreq-empty-soft" style={{ marginBottom: 18 }}>
                Coverage has not been detected yet. Assigned tasks are visible, but task implementation judgments are not available.
              </div>
            )}

            <section className="devreq-card devreq-section">
              <div className="devreq-section-head">
                <div>
                  <h2>Assigned Implementation Work</h2>
                  <div className="devreq-muted">Open a requirement to review task coverage, matched code, and evaluator reasoning.</div>
                </div>
                <div className="devreq-muted">{filteredStories.length} visible</div>
              </div>

              {loading && <div className="devreq-empty-soft">Loading assigned requirements...</div>}

              {!loading && filteredStories.length === 0 && (
                <div className="devreq-empty-soft">No implementation requirements match the current filters.</div>
              )}

              {!loading && filteredStories.length > 0 && (
                <div className="devreq-story-list">
                  {filteredStories.map(story => (
                    <StoryCard
                      key={story.story_id}
                      story={story}
                      expanded={expandedStoryIds.has(story.story_id)}
                      coverageDetected={coverageDetected}
                      expandedTaskIds={expandedTaskIds}
                      onToggle={() => toggleStory(story.story_id)}
                      onToggleTaskEvidence={toggleTaskEvidence}
                    />
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </main>
    </DashboardLayout>
  );
}
