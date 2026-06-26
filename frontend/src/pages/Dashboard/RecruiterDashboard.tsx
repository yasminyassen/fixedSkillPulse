import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import api from "../../api/auth";
import DashboardLayout from "../DashboardLayout";

type SonarState = "ready" | "sonar_unavailable" | "pending" | string;

type RepoItem = {
  candidate: string;
  repo_name: string;
  clone_path: string;
  html_url: string;
  default_branch: string;
  analysis_run_id?: number | null;
  analysis_status?: string | null;
  status?: string | null;
  analysis_error?: string | null;
  latest_commit_sha?: string | null;
  analyzed_at?: string | null;
  analysis_version?: string | null;
  skill_score?: number | null;
  skill_score_level?: string | null;
  sonar_health_score?: number | null;
  sonar_state?: SonarState | null;
  quality_gate?: string | null;
  bugs?: number | null;
  code_smells?: number | null;
  coverage?: number | null;
  duplication_percentage?: number | null;
  cognitive_complexity?: number | null;
  reliability_rating?: string | null;
  maintainability_rating?: string | null;
  technical_debt_minutes?: number | null;
  lines_of_code?: number | null;
};

type PreviewRow = {
  candidate_name: string;
  repo_url: string;
  full_name: string;
  repo_name: string;
  branch: string;
};

type SkippedItem = {
  repo_name?: string;
  candidate_name?: string;
  row?: number;
  reason: string;
};

type ProfileData = {
  talent_overview: {
    candidates_evaluated: number;
    high_priority: number;
    profiles_shortlisted: number;
  };
  recent_activity: Array<{
    candidate_name: string;
    repo_name: string;
    skill_score: number | null;
    skill_score_level: string;
    sonar_health_score: number | null;
    sonar_state: string;
    quality_gate: string | null;
    run_id: number;
    completed_at: string | null;
  }>;
};

type CandidateRow = {
  candidate_name: string;
  github_login: string;
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
  reliability_rating?: string | null;
  maintainability_rating?: string | null;
  technical_debt_minutes?: number | null;
  lines_of_code: number | null;
  security?: number | null;
  repo_count: number;
  contribution_count: number;
  run_id: number;
};

type ApiError = {
  response?: {
    data?: {
      detail?: unknown;
    };
  };
};

const progressSteps = [
  "Reading candidate list",
  "Confirming candidates",
  "Running SonarQube analysis",
  "Ranking candidates",
];

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

const safeNumber = (value: unknown): number | null => {
  if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
};

const fmt = (value: number | string | null | undefined, suffix = "") => {
  if (value === null || value === undefined || value === "") return "Unavailable";
  if (typeof value === "number") return `${Number.isInteger(value) ? value : value.toFixed(1)}${suffix}`;
  return `${value}${suffix}`;
};

const scoreColor = (score: number | null | undefined) => {
  if (score === null || score === undefined) return "#94a3b8";
  if (score >= 80) return "#34d399";
  if (score >= 60) return "#fbbf24";
  if (score >= 40) return "#fb923c";
  return "#f87171";
};

const qualityGateColor = (gate?: string | null) => {
  const value = String(gate || "").toUpperCase();
  if (value === "OK" || value === "PASS" || value === "PASSED") return "#34d399";
  if (value === "WARN" || value === "WARNING") return "#fbbf24";
  if (value === "ERROR" || value === "FAILED" || value === "FAIL") return "#f87171";
  return "#94a3b8";
};

const CheckIcon = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const UploadIcon = () => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);

const FileIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
  </svg>
);

const XIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

function FileUploadZone({ file, onChange }: { file: File | null; onChange: (f: File | null) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) onChange(dropped);
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div>
      <label className="rec-label">Candidate file (.csv, .xlsx, .xls)</label>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.xlsx,.xls"
        style={{ display: "none" }}
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />

      {!file ? (
        <div
          onClick={() => inputRef.current?.click()}
          onDrop={handleDrop}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          className="rec-drop-zone"
          style={{
            borderColor: dragging ? "rgba(99,102,241,0.7)" : "rgba(99,102,241,0.25)",
            background: dragging ? "rgba(99,102,241,0.07)" : "rgba(99,102,241,0.03)",
          }}
        >
          <div className="rec-upload-icon"><UploadIcon /></div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
              Drop your file here, or <span style={{ color: "#a78bfa", textDecoration: "underline", textUnderlineOffset: 3 }}>browse</span>
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>Supports .csv, .xlsx, .xls</div>
          </div>
        </div>
      ) : (
        <div className="rec-selected-file">
          <div className="rec-file-icon"><FileIcon /></div>
          <div style={{ flex: 1, overflow: "hidden" }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{file.name}</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>{formatSize(file.size)}</div>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onChange(null);
              if (inputRef.current) inputRef.current.value = "";
            }}
            className="rec-remove-file"
          >
            <XIcon />
          </button>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, color = "var(--text-primary)", helper }: { label: string; value: string | number; color?: string; helper?: string }) {
  return (
    <div className="rec-metric-card">
      <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", fontWeight: 800 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 900, color, marginTop: 5, fontFamily: "'Inter',sans-serif" }}>{value}</div>
      {helper && <div style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 4 }}>{helper}</div>}
    </div>
  );
}

function Pill({ value, color }: { value: string; color: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", padding: "3px 8px", borderRadius: 999, color, background: `${color}18`, border: `1px solid ${color}35`, fontSize: 11, fontWeight: 800, textTransform: "capitalize" }}>
      {value}
    </span>
  );
}

export default function RecruiterDashboard() {
  const location = useLocation();
  const navigate = useNavigate();
  const isCandidateView = location.pathname.includes("/candidates");

  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [previewRows, setPreviewRows] = useState<PreviewRow[]>([]);
  const [previewSkipped, setPreviewSkipped] = useState<SkippedItem[]>([]);
  const [showPreview, setShowPreview] = useState(false);
  const [forceReanalyze, setForceReanalyze] = useState(false);
  const [loading, setLoading] = useState(false);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeStep, setActiveStep] = useState<number | null>(null);
  const [repositories, setRepositories] = useState<RepoItem[]>([]);
  const [skipped, setSkipped] = useState<SkippedItem[]>([]);
  const [githubAuthUrl, setGithubAuthUrl] = useState<string | null>(null);
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [candidates, setCandidates] = useState<CandidateRow[]>([]);

  const pollingRef = useRef<number | null>(null);
  const repositoriesRef = useRef<RepoItem[]>([]);
  const restoredRef = useRef(false);

  const stopPolling = () => {
    if (pollingRef.current) {
      window.clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  };

  const loadDashboard = useCallback(async (showLoading = false) => {
    if (showLoading) setDashboardLoading(true);
    try {
      const [profileRes, candidatesRes] = await Promise.all([
        api.get<ProfileData>("/recruiter/profile-dashboard"),
        api.get<CandidateRow[]>("/analysis/recruiter/candidates"),
      ]);
      setProfile(profileRes.data);
      setCandidates(candidatesRes.data || []);
    } finally {
      if (showLoading) setDashboardLoading(false);
    }
  }, []);

  useEffect(() => { void loadDashboard(true); }, [loadDashboard]);
  useEffect(() => { repositoriesRef.current = repositories; }, [repositories]);
  useEffect(() => {
    if (repositories.length) localStorage.setItem("recruiter_candidate_repos", JSON.stringify(repositories));
  }, [repositories]);
  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;
    try {
      const raw = localStorage.getItem("recruiter_candidate_repos");
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) setRepositories(parsed);
      }
    } catch { /* ignore */ }
  }, []);
  useEffect(() => () => stopPolling(), []);

  const rankedCandidates = useMemo(() => {
    return [...candidates].sort((a, b) => (b.skill_score ?? -1) - (a.skill_score ?? -1));
  }, [candidates]);

  const candidateRows = useMemo(() => {
    const rows = repositories.map((repo) => ({
      candidate: repo.candidate,
      repo_name: repo.repo_name,
      skill_score: repo.skill_score ?? null,
      skill_score_level: repo.skill_score_level || "Unavailable",
      sonar_health_score: repo.sonar_health_score ?? null,
      quality_gate: repo.quality_gate ?? null,
      analysis_status: repo.analysis_status || repo.status || "pending",
      analyzed_at: repo.analyzed_at ?? null,
      latest_commit_sha: repo.latest_commit_sha ?? null,
      run_id: repo.analysis_run_id ?? null,
    }));
    return rows.sort((a, b) => (b.skill_score ?? -1) - (a.skill_score ?? -1));
  }, [repositories]);

  const isPendingRepo = useCallback((repo: RepoItem) => {
    const status = repo.analysis_status || repo.status || "pending";
    return Boolean(repo.analysis_run_id) && (status === "running" || status === "pending");
  }, []);

  const updateRepo = useCallback((target: RepoItem, patch: Partial<RepoItem>) =>
    setRepositories((prev) => prev.map((repo) => {
      const sameRun = target.analysis_run_id && repo.analysis_run_id === target.analysis_run_id;
      const sameCandidateRepo = repo.candidate === target.candidate && repo.repo_name === target.repo_name;
      if (!sameRun && !sameCandidateRepo) return repo;
      return { ...repo, ...patch };
    })), []);

  const pollAnalysisStatus = useCallback(async () => {
    const current = repositoriesRef.current;
    const pending = current.filter(isPendingRepo);
    if (pending.length === 0) {
      if (current.length > 0) setActiveStep(3);
      stopPolling();
      void loadDashboard(false);
      return;
    }

    await Promise.all(pending.map(async (repo) => {
      try {
        const res = await api.get(`/analysis/${repo.analysis_run_id}`);
        const status = res.data.status || "running";
        if (status === "completed") {
          updateRepo(repo, {
            analysis_status: "completed",
            status: "completed",
            skill_score: safeNumber(res.data.skill_score),
            skill_score_level: res.data.skill_score_level || "Unavailable",
            sonar_health_score: safeNumber(res.data.sonar_health_score),
            sonar_state: res.data.sonar_state || "ready",
            quality_gate: res.data.quality_gate ?? null,
            bugs: safeNumber(res.data.bugs),
            code_smells: safeNumber(res.data.code_smells),
            coverage: safeNumber(res.data.coverage),
            duplication_percentage: safeNumber(res.data.duplication_percentage),
            cognitive_complexity: safeNumber(res.data.cognitive_complexity),
            reliability_rating: res.data.reliability_rating ?? null,
            maintainability_rating: res.data.maintainability_rating ?? null,
            technical_debt_minutes: safeNumber(res.data.technical_debt_minutes),
            lines_of_code: safeNumber(res.data.lines_of_code),
            analyzed_at: res.data.completed_at ?? repo.analyzed_at,
          });
        } else if (status === "failed") {
          updateRepo(repo, {
            analysis_status: "failed",
            status: "failed",
            analysis_error: res.data?.message || "Analysis failed",
          });
        } else {
          updateRepo(repo, { analysis_status: status, status });
        }
      } catch {
        updateRepo(repo, {
          analysis_status: "failed",
          status: "failed",
          analysis_error: "Unable to fetch analysis status.",
        });
      }
    }));
  }, [isPendingRepo, loadDashboard, updateRepo]);

  const startPolling = useCallback((force = false) => {
    if (pollingRef.current && !force) return;
    stopPolling();
    void pollAnalysisStatus();
    pollingRef.current = window.setInterval(pollAnalysisStatus, 4000);
  }, [pollAnalysisStatus]);

  useEffect(() => {
    if (!repositories.some(isPendingRepo)) return;
    setActiveStep(2);
    startPolling();
  }, [isPendingRepo, repositories, startPolling]);

  const handleAuthError = (err: unknown) => {
    const detail = (err as ApiError)?.response?.data?.detail;
    const needsAuth = isRecord(detail) && Boolean(detail.requires_github_auth);
    if (needsAuth) {
      setGithubAuthUrl(typeof detail.auth_url === "string" ? detail.auth_url : null);
      setError("Connect GitHub to analyze candidate repositories.");
    } else {
      setError(typeof detail === "string" ? detail : "Request failed. Please try again.");
    }
  };

  const handleFileChange = (f: File | null) => {
    setUploadFile(f);
    setShowPreview(false);
    setPreviewRows([]);
    setPreviewSkipped([]);
    setError(null);
  };

  const handlePreview = async () => {
    if (!uploadFile) { setError("Upload a CSV or Excel file with candidate repositories."); return; }
    setError(null); setGithubAuthUrl(null); setLoading(true);
    setShowPreview(false); setActiveStep(0);
    try {
      const formData = new FormData();
      formData.append("file", uploadFile);
      const response = await api.post("/api/recruiter/bulk-analyze/preview", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPreviewRows(response.data.rows || []);
      setPreviewSkipped(response.data.skipped || []);
      setShowPreview(true);
      if ((response.data.rows || []).length === 0) setError("No valid candidate rows were found. Check the skipped rows below and fix your file.");
    } catch (err: unknown) {
      handleAuthError(err); setActiveStep(null);
    } finally { setLoading(false); }
  };

  const handleConfirmAnalysis = async () => {
    if (previewRows.length === 0) { setError("Add at least one valid candidate row before starting analysis."); return; }
    setError(null); setGithubAuthUrl(null); setLoading(true);
    setRepositories([]); setSkipped([]); setActiveStep(1); stopPolling();
    try {
      const response = await api.post("/api/recruiter/bulk-analyze/confirm", {
        force_reanalyze: forceReanalyze,
        candidates: previewRows.map((row) => ({
          candidate_name: row.candidate_name,
          repo_url: row.repo_url,
          branch: row.branch || "main",
        })),
      });
      const fetchedRepos: RepoItem[] = (response.data.repositories || []).map((repo: RepoItem) => ({
        ...repo,
        analysis_run_id: repo.analysis_run_id ?? null,
        analysis_status: repo.analysis_status || repo.status || "running",
        skill_score: repo.skill_score ?? null,
        skill_score_level: repo.skill_score_level || "Unavailable",
        sonar_health_score: repo.sonar_health_score ?? null,
        analysis_error: null,
      }));
      setRepositories(fetchedRepos);
      setSkipped(response.data.skipped || []);
      setShowPreview(false); setActiveStep(2); startPolling(true);
    } catch (err: unknown) {
      handleAuthError(err); setActiveStep(null);
    } finally { setLoading(false); }
  };

  const updatePreviewRow = (index: number, patch: Partial<PreviewRow>) =>
    setPreviewRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  const removePreviewRow = (index: number) =>
    setPreviewRows((prev) => prev.filter((_, i) => i !== index));

  const formatTimestamp = (value?: string | null) => {
    if (!value) return "-";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? "-" : parsed.toLocaleString();
  };

  const card = (content: React.ReactNode, extra?: React.CSSProperties) => (
    <div className="rec-card" style={extra}>{content}</div>
  );

  const sectionTitle = (text: string) => (
    <h2 style={{ fontFamily: "'Inter',sans-serif", fontSize: 18, fontWeight: 800, color: "var(--text-primary)", margin: "0 0 16px" }}>
      {text}
    </h2>
  );

  return (
    <DashboardLayout>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        input { outline: none; font-family: 'Inter', sans-serif; color: var(--text-primary); }
        input::placeholder { color: var(--text-faint); }
        .rec-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 24px 28px; }
        .rec-label { font-size: 12px; letter-spacing: 0.6px; text-transform: uppercase; color: rgba(167,139,250,0.8); font-weight: 700; display: block; margin-bottom: 10px; }
        .rec-input { background: var(--bg-input); border: 1px solid var(--border-input); color: var(--text-primary); border-radius: 10px; padding: 10px 12px; font-size: 13px; transition: border-color 0.2s; font-family: 'Inter', sans-serif; }
        .rec-input:focus { border-color: rgba(99,102,241,0.5); outline: none; }
        .rec-row-card { padding: 14px 16px; border-radius: 12px; border: 1px solid var(--border); background: var(--bg-card-hover); margin-bottom: 10px; transition: border-color 0.15s; }
        .rec-row-card:hover { border-color: var(--border-hover); }
        .rec-meta-label { font-size: 11px; color: var(--text-muted); margin-bottom: 3px; text-transform: uppercase; letter-spacing: 0.4px; }
        .rec-meta-value { font-size: 13px; font-weight: 800; color: var(--text-primary); }
        .rec-drop-zone { border: 2px dashed; border-radius: 14px; padding: 28px 20px; display: flex; flex-direction: column; align-items: center; gap: 10px; cursor: pointer; transition: all 0.2s; user-select: none; }
        .rec-drop-zone:hover { border-color: rgba(99,102,241,0.5) !important; background: rgba(99,102,241,0.06) !important; }
        .rec-upload-icon { width: 52px; height: 52px; border-radius: 50%; background: rgba(99,102,241,0.12); border: 1px solid rgba(99,102,241,0.2); display: flex; align-items: center; justify-content: center; color: rgba(167,139,250,0.8); }
        .rec-selected-file { border: 1px solid rgba(99,102,241,0.35); border-radius: 14px; padding: 14px 16px; display: flex; align-items: center; gap: 12px; background: rgba(99,102,241,0.06); }
        .rec-file-icon { width: 40px; height: 40px; border-radius: 10px; flex-shrink: 0; background: rgba(99,102,241,0.15); border: 1px solid rgba(99,102,241,0.25); display: flex; align-items: center; justify-content: center; color: #a78bfa; }
        .rec-remove-file { width: 28px; height: 28px; border-radius: 8px; border: 1px solid rgba(248,113,113,0.25); background: rgba(248,113,113,0.08); color: rgba(248,113,113,0.8); display: flex; align-items: center; justify-content: center; cursor: pointer; flex-shrink: 0; }
        .rec-remove-file:hover { background: rgba(248,113,113,0.18); color: #f87171; }
        .rec-metric-card { padding: 16px; border-radius: 12px; border: 1px solid var(--border); background: var(--bg-card); }
        .rec-table { width: 100%; border-collapse: collapse; min-width: 1180px; }
        .rec-table th { padding: 10px; border-bottom: 1px solid var(--border); text-align: left; color: var(--text-muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
        .rec-table td { padding: 11px 10px; border-bottom: 1px solid var(--border); font-size: 13px; }
      `}</style>

      <div style={{ minHeight: "100vh", padding: "36px 40px 80px", color: "var(--text-primary)", fontFamily: "'Inter', sans-serif", background: "var(--bg-gradient)" }}>
        <div style={{ maxWidth: 1160, margin: "0 auto", display: "flex", flexDirection: "column", gap: 24 }}>
          <div>
            <div className="rec-label" style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "5px 14px", borderRadius: 999, border: "1px solid rgba(99,102,241,0.4)", background: "rgba(99,102,241,0.12)", width: "fit-content", marginBottom: 10 }}>
              Recruiter Bulk Analysis
            </div>
            <h1 style={{ fontFamily: "'Inter',sans-serif", fontSize: 28, fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-0.5px", margin: "0 0 4px" }}>
              Analyze candidate submissions at scale
            </h1>
            <p style={{ fontSize: 13.5, color: "var(--text-muted)", margin: 0, lineHeight: 1.6 }}>
              Upload CSV or Excel candidate repositories, preview rows, then rank candidates with the new Skill Score and SonarQube metrics.
            </p>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12 }}>
            <Metric label="Candidates" value={profile?.talent_overview.candidates_evaluated ?? (dashboardLoading ? "…" : 0)} />
            <Metric label="High Priority" value={profile?.talent_overview.high_priority ?? (dashboardLoading ? "…" : 0)} color="#f87171" />
            <Metric label="Shortlisted" value={profile?.talent_overview.profiles_shortlisted ?? (dashboardLoading ? "…" : 0)} color="#34d399" />
            <Metric label="Score Unavailable" value={candidates.filter((candidate) => candidate.skill_score === null).length} color="#94a3b8" />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.1fr) minmax(280px,0.9fr)", gap: 22 }}>
            {card(
              <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                <FileUploadZone file={uploadFile} onChange={handleFileChange} />
                <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.6 }}>
                  Required columns: <code className="rec-code">candidate_name</code>, <code className="rec-code">repo_url</code>. Optional: <code className="rec-code">branch</code>.
                  <br />Accepted aliases include <code className="rec-code">Candidate</code>, <code className="rec-code">GitHub URL</code>, and <code className="rec-code">repository_url</code>.
                </div>
                <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12, color: "var(--text-secondary)", fontWeight: 600, cursor: "pointer" }}>
                  <input type="checkbox" checked={forceReanalyze} onChange={(e) => setForceReanalyze(e.target.checked)} style={{ width: 16, height: 16, accentColor: "#6366f1" }} />
                  Force reanalyze
                </label>
                {error && (
                  <div style={{ padding: "10px 12px", borderRadius: 10, background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.25)", color: "rgba(248,113,113,0.9)", fontSize: 12 }}>
                    {error}
                    {githubAuthUrl && (
                      <button onClick={() => { window.location.href = githubAuthUrl; }} style={{ marginTop: 10, height: 38, borderRadius: 9, width: "100%", border: "1px solid rgba(99,102,241,0.4)", background: "rgba(99,102,241,0.15)", color: "var(--text-primary)", fontWeight: 700, fontSize: 12, cursor: "pointer" }}>
                        Connect GitHub
                      </button>
                    )}
                  </div>
                )}
                <button onClick={handlePreview} disabled={!uploadFile || loading} className="rec-primary-btn" style={{ opacity: loading || !uploadFile ? 0.5 : 1, cursor: loading || !uploadFile ? "not-allowed" : "pointer" }}>
                  {loading && !showPreview ? "Reading file…" : "Preview candidates"}
                </button>
              </div>,
            )}

            {card(
              <>
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", marginBottom: 14 }}>Progress</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {progressSteps.map((step, idx) => {
                    const isDone = activeStep !== null && idx < activeStep;
                    const isActive = activeStep === idx;
                    return (
                      <div key={step} style={{ display: "flex", alignItems: "center", gap: 10, opacity: activeStep === null ? 0.45 : 1 }}>
                        <div style={{ width: 10, height: 10, borderRadius: "50%", flexShrink: 0, background: isDone ? "#a78bfa" : isActive ? "#ec4899" : "var(--border-hover)" }} />
                        <span style={{ fontSize: 12, color: isDone || isActive ? "var(--text-primary)" : "var(--text-muted)" }}>{step}</span>
                        {isDone && <span style={{ marginLeft: "auto", color: "#a78bfa" }}><CheckIcon /></span>}
                      </div>
                    );
                  })}
                </div>
                <div style={{ marginTop: 18, paddingTop: 14, borderTop: "1px solid var(--border)", fontSize: 12, color: "var(--text-muted)", lineHeight: 1.6 }}>
                  Ranking now uses Skill Score, Sonar Health, Quality Gate, Bugs, Code Smells, Coverage, Duplication, and Complexity.
                </div>
              </>,
            )}
          </div>

          {showPreview && card(
            <>
              {sectionTitle("Preview before analysis")}
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 14 }}>Review and edit the parsed rows. Invalid rows are skipped and will not be analyzed.</div>
              {previewRows.length === 0 ? (
                <div style={{ padding: 18, borderRadius: 12, border: "1px dashed var(--border-hover)", color: "rgba(248,113,113,0.85)", fontSize: 12, marginBottom: 16 }}>No valid rows to analyze.</div>
              ) : (
                <div style={{ display: "grid", gap: 10, marginBottom: 16 }}>
                  {previewRows.map((row, index) => (
                    <div key={`${row.candidate_name}-${index}`} style={{ display: "grid", gridTemplateColumns: "1fr 1.4fr 0.5fr auto", gap: 10, alignItems: "center" }}>
                      <input className="rec-input" value={row.candidate_name} onChange={(e) => updatePreviewRow(index, { candidate_name: e.target.value })} placeholder="Candidate name" />
                      <input className="rec-input" value={row.repo_url} onChange={(e) => updatePreviewRow(index, { repo_url: e.target.value })} placeholder="https://github.com/org/repo" />
                      <input className="rec-input" value={row.branch} onChange={(e) => updatePreviewRow(index, { branch: e.target.value })} placeholder="main" />
                      <button onClick={() => removePreviewRow(index)} className="rec-danger-btn">Remove</button>
                    </div>
                  ))}
                </div>
              )}
              {previewSkipped.length > 0 && (
                <div style={{ marginBottom: 16, fontSize: 12, color: "rgba(248,113,113,0.85)", lineHeight: 1.6 }}>
                  Skipped while reading file: {previewSkipped.map((item) => `${item.candidate_name || item.repo_name || `row ${item.row}`} (${item.reason})`).join("; ")}
                </div>
              )}
              <button onClick={handleConfirmAnalysis} disabled={previewRows.length === 0 || loading} className="rec-success-btn" style={{ opacity: previewRows.length === 0 || loading ? 0.6 : 1, cursor: previewRows.length === 0 || loading ? "not-allowed" : "pointer" }}>
                {loading ? "Starting analysis…" : `Start analysis (${previewRows.length})`}
              </button>
            </>,
          )}

          {isCandidateView ? (
            card(
              <>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
                  {sectionTitle("Candidate View")}
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{candidateRows.length} uploaded candidates</div>
                </div>
                {candidateRows.length === 0 && <div style={{ fontSize: 12, color: "var(--text-muted)" }}>No candidate scores available from the current upload yet.</div>}
                {candidateRows.map((row) => (
                  <div key={`${row.candidate}-${row.repo_name}-${row.run_id || "pending"}`} className="rec-row-card" style={{ display: "grid", gridTemplateColumns: "1fr 0.9fr 0.7fr 0.8fr 0.8fr auto", gap: 12, alignItems: "center" }}>
                    <div><div className="rec-meta-label">Candidate</div><div className="rec-meta-value">{row.candidate}</div></div>
                    <div><div className="rec-meta-label">Repository</div><div style={{ fontSize: 13, color: "var(--text-secondary)" }}>{row.repo_name}</div></div>
                    <div><div className="rec-meta-label">Status</div><Pill value={row.analysis_status} color={row.analysis_status === "completed" ? "#34d399" : row.analysis_status === "failed" ? "#f87171" : "#fbbf24"} /></div>
                    <div><div className="rec-meta-label">Skill Score</div><div className="rec-meta-value" style={{ color: scoreColor(row.skill_score) }}>{fmt(row.skill_score)}</div></div>
                    <div><div className="rec-meta-label">Sonar Health</div><div className="rec-meta-value" style={{ color: scoreColor(row.sonar_health_score) }}>{fmt(row.sonar_health_score)}</div></div>
                    <button disabled={!row.run_id} onClick={() => row.run_id && navigate(`/analysis/${row.run_id}`)} className="rec-view-btn">View</button>
                  </div>
                ))}
              </>,
            )
          ) : (
            card(
              <>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 16 }}>
                  {sectionTitle("Candidate Ranking")}
                  <button onClick={() => void loadDashboard(true)} className="rec-view-btn">Refresh</button>
                </div>
                {rankedCandidates.length === 0 && <p style={{ color: "var(--text-muted)", fontSize: 13 }}>No completed candidate analyses yet.</p>}
                <div style={{ overflowX: "auto" }}>
                  <table className="rec-table">
                    <thead>
                      <tr>
                        {[
                          "Candidate", "Skill Score", "Level", "Sonar Health", "Gate", "Bugs", "Code Smells", "Coverage", "Duplication", "Complexity", "Debt", "LOC", "Action",
                        ].map((header) => <th key={header}>{header}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {rankedCandidates.map((candidate) => (
                        <tr key={candidate.run_id}>
                          <td style={{ fontWeight: 800 }}>{candidate.candidate_name}<div style={{ color: "var(--text-muted)", fontWeight: 500, fontSize: 11 }}>{candidate.github_login}</div></td>
                          <td style={{ color: scoreColor(candidate.skill_score), fontWeight: 900 }}>{fmt(candidate.skill_score)}</td>
                          <td>{candidate.skill_score_level || "Unavailable"}</td>
                          <td style={{ color: scoreColor(candidate.sonar_health_score), fontWeight: 800 }}>{fmt(candidate.sonar_health_score)}</td>
                          <td><Pill value={candidate.quality_gate || "N/A"} color={qualityGateColor(candidate.quality_gate)} /></td>
                          <td>{fmt(candidate.bugs)}</td>
                          <td>{fmt(candidate.code_smells)}</td>
                          <td>{fmt(candidate.coverage, candidate.coverage == null ? "" : "%")}</td>
                          <td>{fmt(candidate.duplication_percentage, candidate.duplication_percentage == null ? "" : "%")}</td>
                          <td>{fmt(candidate.cognitive_complexity)}</td>
                          <td>{fmt(candidate.technical_debt_minutes, candidate.technical_debt_minutes == null ? "" : "m")}</td>
                          <td>{fmt(candidate.lines_of_code)}</td>
                          <td><button onClick={() => navigate(`/analysis/${candidate.run_id}`)} className="rec-view-btn">View</button></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>,
            )
          )}

          {(skipped.length > 0 || profile?.recent_activity?.length) && (
            <div style={{ display: "grid", gridTemplateColumns: skipped.length > 0 ? "1fr 1fr" : "1fr", gap: 18 }}>
              {skipped.length > 0 && card(
                <>
                  {sectionTitle("Skipped repositories")}
                  {skipped.map((item, index) => (
                    <div key={`${item.candidate_name || item.repo_name}-${index}`} className="rec-row-card">
                      <div style={{ fontSize: 13, fontWeight: 800 }}>{item.candidate_name || item.repo_name || `Row ${item.row}`}</div>
                      <div style={{ fontSize: 12, color: "rgba(248,113,113,0.9)", marginTop: 4 }}>{item.reason}</div>
                    </div>
                  ))}
                </>,
              )}
              {profile?.recent_activity?.length ? card(
                <>
                  {sectionTitle("Recent Activity")}
                  {profile.recent_activity.map((activity) => (
                    <button key={activity.run_id} onClick={() => navigate(`/analysis/${activity.run_id}`)} className="rec-activity-row">
                      <strong>{activity.candidate_name}</strong> · {activity.repo_name}
                      <span style={{ marginLeft: 10, color: scoreColor(activity.skill_score), fontWeight: 900 }}>{fmt(activity.skill_score)} · {activity.skill_score_level}</span>
                      <span style={{ marginLeft: 10, color: scoreColor(activity.sonar_health_score), fontWeight: 800 }}>Sonar {fmt(activity.sonar_health_score)}</span>
                      <span style={{ float: "right", color: "var(--text-muted)" }}>{formatTimestamp(activity.completed_at)}</span>
                    </button>
                  ))}
                </>,
              ) : null}
            </div>
          )}
        </div>
      </div>
      <style>{`
        .rec-code { background: var(--bg-card-hover); padding: 1px 5px; border-radius: 4px; font-size: 11px; }
        .rec-primary-btn { height: 46px; border-radius: 12px; border: none; background: linear-gradient(135deg,#6366f1,#ec4899); color: white; font-weight: 700; font-size: 14px; }
        .rec-success-btn { height: 44px; border-radius: 12px; border: none; background: linear-gradient(135deg,#22c55e,#16a34a); color: white; font-weight: 700; font-size: 14px; padding: 0 18px; }
        .rec-danger-btn { height: 38px; border-radius: 10px; border: 1px solid rgba(248,113,113,0.25); background: rgba(248,113,113,0.08); color: rgba(248,113,113,0.9); cursor: pointer; font-size: 12px; }
        .rec-view-btn { padding: 8px 12px; border-radius: 9px; border: 1px solid rgba(99,102,241,0.3); background: rgba(99,102,241,0.1); color: #a78bfa; cursor: pointer; font-weight: 800; font-size: 12px; }
        .rec-view-btn:disabled { opacity: 0.45; cursor: not-allowed; }
        .rec-activity-row { display: block; width: 100%; text-align: left; padding: 11px 0; border: 0; border-top: 1px solid var(--border); background: transparent; color: var(--text-primary); cursor: pointer; font-size: 13px; }
      `}</style>
    </DashboardLayout>
  );
}
