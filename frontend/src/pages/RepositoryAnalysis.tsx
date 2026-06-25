import { useState, useEffect, useRef } from "react";
import api from "../api/auth";
import DashboardLayout from "./DashboardLayout";
import { ExtractedRequirementsReviewModal, PrdUploadDropZone } from "../components/requirements/PrdWorkflow";

interface Analysis {
  analysis_id: number;
  repo_id: number;
  repo_name: string;
  branch: string;
  status: string;
  triggered_at: string;
  skill_score: number | null;
  skill_score_level: string;
  sonar_health_score: number | null;
  sonar_state: string;
  quality_gate: string | null;
  analysis_scope?: string;
}

interface TechnicalTask {
  id: number;
  description: string;
  type: string;
  status: string;
  assigned_to?: number | null;
  ac_ids: number[];
  due_date?: string | null;
}

interface UserStory {
  id: number;
  story_code: string;
  title: string;
  description: string;
  role: string;
  feature: string;
  benefit: string;
  acceptance_criteria: { id: number; text: string }[];
  technical_tasks: TechnicalTask[];
}

interface EditState {
  isOpen: boolean;
  type: 'story' | 'story_desc' | 'ac' | 'task';
  storyId: number;
  itemId?: number;
  text: string;
  title: string;
}

interface Contributor {
  id: number;
  username: string;
  full_name: string;
  email?: string;
  specialization?: string | null;
}

const withTimeout = <T,>(promise: Promise<T>, ms = 10000): Promise<T> =>
  Promise.race([
    promise,
    new Promise<T>((_, reject) => window.setTimeout(() => reject(new Error("Request timed out")), ms)),
  ]);

const scoreColor = (s: number | null) => {
  if (s === null) return "rgba(148,163,184,0.6)";
  if (s >= 80) return "#34d399";
  if (s >= 50) return "#fbbf24";
  return "#f87171";
};

const scoreLabel = (s: number | null) => {
  if (s === null) return "—";
  if (s >= 80) return "Excellent";
  if (s >= 60) return "Good";
  if (s >= 40) return "Fair";
  return "Needs work";
};

const formatScore = (s: number | null) => {
  if (s === null || s === undefined) return "N/A";
  return Number.isInteger(s) ? String(s) : s.toFixed(1);
};

const formatState = (value: string | null | undefined) => {
  if (!value) return "N/A";
  return value.replace(/_/g, " ");
};

const statusConfig: Record<string, { color: string; bg: string; dot: string; label: string }> = {
  completed: { color: "#34d399", bg: "rgba(52,211,153,0.1)",   dot: "#34d399", label: "Completed" },
  failed:    { color: "#f87171", bg: "rgba(248,113,113,0.1)",  dot: "#f87171", label: "Failed"    },
  running:   { color: "#fbbf24", bg: "rgba(251,191,36,0.1)",   dot: "#fbbf24", label: "Running"   },
  pending:   { color: "#94a3b8", bg: "rgba(148,163,184,0.1)",  dot: "#94a3b8", label: "Pending"   },
};

const timeAgo = (iso: string) => {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
};

export default function RepositoryAnalysis() {
  const [repoUrl, setRepoUrl]   = useState("");
  const [programmingLanguage, setProgrammingLanguage] = useState("python");
  const [branch, setBranch]     = useState("main");
  const [file, setFile]         = useState<File | null>(null);
  const [coverageFile, setCoverageFile] = useState<File | null>(null);
  const [coverageFileError, setCoverageFileError] = useState("");
  const [loading, setLoading]   = useState(false);
  const [runId, setRunId]       = useState<number | null>(null);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [urlError, setUrlError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const coverageInputRef = useRef<HTMLInputElement>(null);
  const role = localStorage.getItem("role") || "developer";

  const [pendingAutoRun, setPendingAutoRun] = useState<{ url: string; branch: string; programmingLanguage?: string } | null>(null);
  const [uploadingPrd, setUploadingPrd]     = useState(false);
  const [prdDocId, setPrdDocId]             = useState<number | null>(null);
  const [prdStories, setPrdStories]         = useState<UserStory[]>([]);
  const [showPrdModal, setShowPrdModal]     = useState(false);
  const [selectedRepoForPrd, setSelectedRepoForPrd] = useState<number | "">("");
  const [analysisMode, setAnalysisMode] = useState<"analyze" | "requirements">("analyze");
  const [requirementsRepoId, setRequirementsRepoId] = useState<number | null>(null);
  const [requirementsAnalysisReady, setRequirementsAnalysisReady] = useState(false);
  const [requirementsAnalysisMsg, setRequirementsAnalysisMsg] = useState("");
  const [reviewContributors, setReviewContributors] = useState<Contributor[]>([]);
  const [requirementsConfirmed, setRequirementsConfirmed] = useState(false);

  const [editModal, setEditModal]   = useState<EditState>({ isOpen: false, type: 'story', storyId: 0, text: "", title: "" });
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const [toast, setToast]           = useState<{ show: boolean; msg: string; type: 'success' | 'error' }>({ show: false, msg: '', type: 'success' });
  const [selectedTaskIds, setSelectedTaskIds] = useState<number[]>([]);
  const [mergeModal, setMergeModal] = useState({ isOpen: false, storyId: 0, text: "" });
  const [githubAuthUrl, setGithubAuthUrl] = useState<string | null>(null);
  const [failedMsg, setFailedMsg]   = useState<string | null>(null);
  const [cachedMsg, setCachedMsg]   = useState<{ runId: number; repoName: string; scope?: string; cachedForCurrentUser?: boolean } | null>(null);

  const accent = role === "manager" ? "#8b5cf6" : role === "recruiter" ? "#a855f7" : "#6366f1";

  const showToast = (msg: string, type: 'success' | 'error' = 'success') => {
    setToast({ show: true, msg, type });
    setTimeout(() => setToast({ show: false, msg: '', type: 'success' }), 4000);
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("github_connected") === "true") {
      const saved = localStorage.getItem("pending_repo");
      if (saved) {
        const { repoUrl: savedUrl, branch: savedBranch, programmingLanguage: savedLanguage } = JSON.parse(saved);
        setRepoUrl(savedUrl);
        setBranch(savedBranch || "main");
        if (savedLanguage) setProgrammingLanguage(savedLanguage);
        localStorage.removeItem("pending_repo");
        window.history.replaceState({}, document.title, window.location.pathname);
        setPendingAutoRun({ url: savedUrl, branch: savedBranch || "main", programmingLanguage: savedLanguage || "python" });
      }
    }
    fetchHistory();
  }, []);

  useEffect(() => {
    if (pendingAutoRun) { startAnalysis(pendingAutoRun.url, pendingAutoRun.branch); setPendingAutoRun(null); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingAutoRun]);

  const fetchHistory = async (showLoading = true) => {
    if (showLoading) setHistoryLoading(true);
    setHistoryError("");
    try {
      const res = await withTimeout(api.get("/analysis/history?limit=50"));
      setAnalyses(res.data.history);
    } catch (err: any) {
      if (err.response?.status === 401) { localStorage.clear(); window.location.href = "/login"; }
      const detail = err?.response?.data?.detail || err?.message || "Could not load analysis history";
      setHistoryError(String(detail));
    } finally { if (showLoading) setHistoryLoading(false); }
  };

  const updateHistoryRunStatus = (analysisId: number, data: any) => {
    setAnalyses(prev => prev.map(item => {
      if (item.analysis_id !== analysisId) return item;
      return {
        ...item,
        status: data.status ?? item.status,
        skill_score: data.skill_score ?? item.skill_score,
        skill_score_level: data.skill_score_level ?? item.skill_score_level,
        sonar_health_score: data.sonar_health_score ?? item.sonar_health_score,
        sonar_state: data.sonar_state ?? item.sonar_state,
        quality_gate: data.quality_gate ?? item.quality_gate,
      };
    }));
  };

  const fetchReviewContributors = async (repoId: number) => {
    try {
      await api.post(`/requirements/repositories/${repoId}/sync-contributors`);
    } catch (err) {
      console.warn("Contributor sync skipped or failed:", err);
    }
    try {
      const res = await api.get(`/requirements/repositories/${repoId}/contributors`);
      setReviewContributors(res.data || []);
    } catch (err) {
      console.warn("Could not load contributors:", err);
      setReviewContributors([]);
    }
  };

  const handleReviewTaskPatch = async (taskId: number, patch: Partial<TechnicalTask>) => {
    try {
      const res = await api.patch(`/requirements/tasks/${taskId}`, patch);
      const updated = res.data;
      setPrdStories(prev => prev.map(story => ({
        ...story,
        technical_tasks: story.technical_tasks.map(task => task.id === taskId ? { ...task, ...updated } : task),
      })));
      showToast("Task updated");
    } catch (err) {
      console.error(err);
      showToast("Failed to update task.", "error");
    }
  };

  const handlePrdUpload = async (f: File) => {
    if (analysisMode === "requirements" && !repoUrl.trim()) { alert("Enter a GitHub repository URL before uploading the PRD."); return; }
    setFile(f); setUploadingPrd(true);
    try {
      const formData = new FormData();
      formData.append("file", f);
      if (requirementsRepoId) formData.append("repository_id", requirementsRepoId.toString());
      else formData.append("repo_url", repoUrl.trim());
      const uploadRes = await api.post("/requirements/upload", formData, { headers: { "Content-Type": "multipart/form-data" } });
      const docId = uploadRes.data.document_id;
      setPrdDocId(docId);
      const storiesRes = await api.get(`/requirements/${docId}/stories`);
      setPrdStories(storiesRes.data);
      const firstStory = storiesRes.data?.[0];
      if (firstStory?.document_id) {
        // Repository id is returned indirectly by the selected workflow after upload; contributors may be empty until analysis.
        setRequirementsAnalysisMsg("Requirements extracted. Review and confirm, then analyze repository and detect coverage.");
      }
      setShowPrdModal(true);
    } catch (err) { console.error(err); alert("Failed to upload and extract PRD."); setFile(null); }
    finally { setUploadingPrd(false); }
  };

  const openEditModal  = (type: 'story' | 'ac' | 'story_desc' | 'task', storyId: number, text: string, title: string, itemId?: number) =>
    setEditModal({ isOpen: true, type, storyId, itemId, text, title });
  const closeEditModal = () => setEditModal({ isOpen: false, type: 'story', storyId: 0, text: "", title: "" });

  const handleSaveEdit = async () => {
    if (!editModal.text.trim()) return;
    setIsSavingEdit(true);
    try {
      if (editModal.type === 'story') {
        await api.patch(`/requirements/stories/${editModal.storyId}`, { title: editModal.text });
        setPrdStories(prev => prev.map(s => s.id === editModal.storyId ? { ...s, title: editModal.text } : s));
      } else if (editModal.type === 'story_desc') {
        await api.patch(`/requirements/stories/${editModal.storyId}`, { description: editModal.text });
        setPrdStories(prev => prev.map(s => s.id === editModal.storyId ? { ...s, description: editModal.text } : s));
      } else if (editModal.type === 'ac' && editModal.itemId !== undefined) {
        const story = prdStories.find(s => s.id === editModal.storyId);
        if (story) {
          const updatedACs = story.acceptance_criteria.map(ac => ac.id === editModal.itemId ? { ...ac, text: editModal.text } : ac);
          await api.patch(`/requirements/stories/${editModal.storyId}`, { acceptance_criteria: updatedACs });
          setPrdStories(prev => prev.map(s => s.id === editModal.storyId ? { ...s, acceptance_criteria: updatedACs } : s));
        }
      } else if (editModal.type === 'task' && editModal.itemId !== undefined) {
        await api.patch(`/requirements/tasks/${editModal.itemId}`, { description: editModal.text });
        setPrdStories(prev => prev.map(story => ({ ...story, technical_tasks: story.technical_tasks.map(t => t.id === editModal.itemId ? { ...t, description: editModal.text } : t) })));
      }
      closeEditModal(); showToast("Changes saved successfully!");
    } catch (err) { console.error(err); showToast("Failed to save changes.", "error"); }
    finally { setIsSavingEdit(false); }
  };

  const confirmPRD = async () => {
    if (!prdDocId) return;
    try {
      await api.post(`/requirements/${prdDocId}/confirm`);
      setShowPrdModal(false); setFile(null); setSelectedRepoForPrd("");
      setRequirementsConfirmed(true);
      showToast("Requirements confirmed. You can now analyze the repository and detect coverage.", "success");
    } catch (err: any) { showToast(`Failed to confirm: ${err.response?.data?.detail || err.message}`, "error"); }
  };

  const handleOpenMergeModal = (storyId: number) => {
    const story = prdStories.find(s => s.id === storyId);
    if (!story) return;
    const combinedText = story.technical_tasks.filter(t => selectedTaskIds.includes(t.id)).map(t => `- [${t.type.toUpperCase()}] ${t.description}`).join("\n\n");
    setMergeModal({ isOpen: true, storyId, text: combinedText });
  };

  const handleConfirmMerge = async () => {
    setIsSavingEdit(true);
    try {
      const story = prdStories.find(s => s.id === mergeModal.storyId);
      if (!story) return;
      const storyTaskIds = story.technical_tasks.map(t => t.id);
      const idsToMerge   = selectedTaskIds.filter(id => storyTaskIds.includes(id));
      const res          = await api.post(`/requirements/stories/${mergeModal.storyId}/tasks/merge`, { task_ids: idsToMerge, new_description: mergeModal.text });
      const newTask      = res.data;
      setPrdStories(prev => prev.map(s => { if (s.id !== mergeModal.storyId) return s; return { ...s, technical_tasks: [...s.technical_tasks.filter(t => !idsToMerge.includes(t.id)), newTask] }; }));
      setSelectedTaskIds(prev => prev.filter(id => !idsToMerge.includes(id)));
      setMergeModal({ isOpen: false, storyId: 0, text: "" });
    } catch (err) { console.error(err); alert("Failed to merge tasks."); }
    finally { setIsSavingEdit(false); }
  };

  const handleCoverageFileChange = (selected: File | null) => {
    setCoverageFileError("");
    if (!selected) {
      setCoverageFile(null);
      return;
    }

    const isXml = selected.name.toLowerCase().endsWith(".xml") || selected.type === "text/xml" || selected.type === "application/xml";
    if (!isXml) {
      setCoverageFile(null);
      setCoverageFileError("Please upload a valid coverage.xml file.");
      return;
    }

    const maxSize = 10 * 1024 * 1024;
    if (selected.size > maxSize) {
      setCoverageFile(null);
      setCoverageFileError("coverage.xml must be 10MB or smaller.");
      return;
    }

    setCoverageFile(selected);
  };

  const submitAnalysisRun = async (url: string, selectedBranch: string) => {
    if (coverageFile) {
      const formData = new FormData();
      formData.append("repo_url", url);
      formData.append("branch", selectedBranch);
      formData.append("programming_language", programmingLanguage);
      formData.append("coverage_file", coverageFile);

      for (const pair of formData.entries()) {
        console.log(pair[0], pair[1]);
      }

      return api.post("/analysis/run/with-coverage", formData);
    }

    return api.post("/analysis/run", {
      repo_url: url,
      branch: selectedBranch,
      programming_language: programmingLanguage,
    });
  };

  const startAnalysis = async (url: string, br: string) => {
    if (!url) { setUrlError("Please enter a GitHub repository URL"); return; }
    if (!/^https:\/\/github\.com\/.+/.test(url)) { setUrlError("URL must start with https://github.com/…"); return; }
    const selectedBranch = (br || "main").trim() || "main";
    setUrlError(""); setGithubAuthUrl(null); setFailedMsg(null); setCachedMsg(null); setLoading(true);
    if (analysisMode === "requirements") {
      setRequirementsAnalysisReady(false);
      setRequirementsAnalysisMsg("Analyzing repository before requirements can be uploaded.");
      setRequirementsRepoId(null);
      setReviewContributors([]);
    }
    try {
      const res = await submitAnalysisRun(url, selectedBranch);
      if (res.data.cached) {
        setLoading(false);
        const repoName = url.replace("https://github.com/", "").split("/").pop() || url;
        setCachedMsg({ runId: res.data.analysis_run_id, repoName, scope: res.data.cached_scope, cachedForCurrentUser: res.data.cached_for_current_user ?? true });
        if (analysisMode === "requirements" && res.data.repo_id) {
          setRequirementsRepoId(res.data.repo_id);
          setRequirementsAnalysisReady(true);
          setRequirementsAnalysisMsg("Repository analysis is ready. Upload a PRD to extract requirements.");
          fetchReviewContributors(res.data.repo_id);
        }
        fetchHistory(false); return;
      }
      if (analysisMode === "requirements" && res.data.repo_id) {
        setRequirementsRepoId(res.data.repo_id);
      }
      setRunId(res.data.analysis_run_id);
      fetchHistory(false);
    } catch (err: any) {
      setLoading(false);
      if (analysisMode === "requirements") {
        setRequirementsAnalysisReady(false);
        setRequirementsAnalysisMsg("Repository analysis failed. Resolve the repository issue before uploading, assigning, or confirming requirements.");
      }
      const status = err.response?.status;
      const detail = err.response?.data?.detail;
      const needsAuth = (typeof detail === "object" && detail?.requires_github_auth) || err.response?.data?.requires_github_auth;
      if (status === 403 && (detail?.recruiter_private_repo || role === "recruiter")) { setUrlError("Private repositories are not supported for Recruiter accounts."); return; }
      if (needsAuth) { const authUrl = (typeof detail === "object" ? detail?.auth_url : null) ?? err.response?.data?.auth_url; localStorage.setItem("pending_repo", JSON.stringify({ repoUrl: url, branch: selectedBranch, programmingLanguage })); setGithubAuthUrl(authUrl); return; }
      if (status === 403 && detail?.no_developer_contributions) { setUrlError(detail.message || "No commits found."); return; }
      if (status === 400 && detail?.no_python_contributions)   { setUrlError(detail.message || "No Python files found."); return; }
      if (status === 404 && detail?.branch_not_found)          { setUrlError("Repository found, but this branch does not exist."); return; }
      if (status === 404) { setUrlError("Repository or branch not found."); return; }
      if (status === 400) { setUrlError("Invalid GitHub repository URL."); return; }
      if (status === 429) { setUrlError("Too many requests. Please wait a moment."); return; }
      if (status === 503) { setUrlError("GitHub API rate limit reached."); return; }
      setUrlError("Something went wrong. Please try again.");
    }
  };

  const analyzeAndDetectCoverage = async () => {
    if (!repoUrl) { setUrlError("Please enter a GitHub repository URL"); return; }
    if (!requirementsConfirmed) { showToast("Confirm requirements before analysis and coverage detection.", "error"); return; }
    const selectedBranch = (branch || "main").trim() || "main";
    setLoading(true);
    try {
      const res = await submitAnalysisRun(repoUrl, selectedBranch);
      const repoId = res.data.repo_id || requirementsRepoId;
      if (!repoId) throw new Error("Repository id was not returned.");
      setRequirementsRepoId(repoId);
      if (!res.data.cached && res.data.analysis_run_id) {
        setRunId(res.data.analysis_run_id);
        setRequirementsAnalysisMsg("Repository analysis is running. Coverage detection will be available when analysis completes.");
      } else {
        await api.post(`/requirements/coverage/repositories/${repoId}/detect`);
        setRequirementsAnalysisReady(true);
        setRequirementsAnalysisMsg("Repository analysis is complete. Coverage detection started.");
        showToast("Coverage detection started");
      }
      fetchHistory(false);
    } catch (err: any) {
      setLoading(false);
      showToast(err.response?.data?.detail || err.message || "Analyze and coverage detection failed", "error");
    }
  };

  useEffect(() => {
    if (!runId) return;
    const iv = setInterval(async () => {
      try {
        const res = await api.get(`/analysis/${runId}`);
        updateHistoryRunStatus(runId, res.data);
        if (res.data.status === "completed") {
          clearInterval(iv); setLoading(false); setRunId(null);
          if (analysisMode === "requirements" && requirementsRepoId) {
            setRequirementsAnalysisReady(true);
            setRequirementsAnalysisMsg("Repository analysis is complete. Starting coverage detection.");
            fetchReviewContributors(requirementsRepoId);
            try {
              await api.post(`/requirements/coverage/repositories/${requirementsRepoId}/detect`);
              showToast("Coverage detection started");
            } catch (err: any) {
              showToast(err.response?.data?.detail || "Coverage detection failed", "error");
            }
          }
          fetchHistory(false);
        }
        else if (res.data.status === "failed") {
          clearInterval(iv); setLoading(false); setRunId(null);
          if (analysisMode === "requirements") {
            setRequirementsAnalysisReady(false);
            setRequirementsAnalysisMsg("Repository analysis failed. Resolve the repository issue before uploading, assigning, or confirming requirements.");
          }
          const reason = res.data.error_reason;
          if (reason === "rate_limit") setFailedMsg("__rate_limit__");
          else if (reason === "not_found") setFailedMsg("Repository or branch not found.");
          else setFailedMsg("Analysis failed. Check the URL and branch, then try again.");
          fetchHistory(false);
        }
      } catch { clearInterval(iv); setLoading(false); }
    }, 3000);
    return () => clearInterval(iv);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  const handleDrop = (e: React.DragEvent) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) handlePrdUpload(f); };

  const card = (content: React.ReactNode, extra?: React.CSSProperties) => (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border)",
      borderRadius: 16, padding: "24px 28px",
      ...extra,
    }}>{content}</div>
  );

  return (
    <DashboardLayout>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500;600;700&display=swap');
        input, select, textarea { font-family: 'DM Sans', sans-serif; }

        .ra-input {
          width: 100%; padding: 12px 14px;
          background: var(--bg-input);
          border: 1px solid rgba(99,102,241,0.25);
          border-radius: 12px; color: var(--text-primary);
          font-size: 14px; outline: none;
          transition: border-color 0.2s, background 0.2s;
          box-sizing: border-box;
        }
        .ra-input::placeholder { color: var(--text-faint); }
        .ra-input:focus { border-color: ${accent}80; background: var(--bg-input-focus); }
        .ra-input.error { border-color: rgba(248,113,113,0.5); }

        .ra-select {
          width: 100%; padding: 12px 14px;
          background: var(--bg-input);
          border: 1px solid rgba(99,102,241,0.25);
          border-radius: 12px; color: var(--text-primary);
          font-size: 14px; outline: none; cursor: pointer;
          transition: border-color 0.2s;
        }
        .ra-select:focus { border-color: ${accent}80; }
        .ra-select option { background: var(--bg-base); color: var(--text-primary); }

        .ra-btn-primary {
          display: inline-flex; align-items: center; gap: 8px;
          padding: 11px 24px;
          background: linear-gradient(135deg, ${accent}, #ec4899);
          border: none; border-radius: 12px; color: white;
          font-family: 'DM Sans', sans-serif; font-size: 14px; font-weight: 700;
          cursor: pointer; transition: all 0.2s;
          box-shadow: 0 4px 16px ${accent}30;
        }
        .ra-btn-primary:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 8px 24px ${accent}40; }
        .ra-btn-primary:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

        .ra-btn-ghost {
          display: inline-flex; align-items: center; gap: 7px;
          padding: 9px 16px;
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: 9px; color: var(--text-secondary);
          font-family: 'DM Sans', sans-serif; font-size: 13px; font-weight: 500;
          cursor: pointer; transition: all 0.2s;
        }
        .ra-btn-ghost:hover { background: var(--bg-card-hover); color: var(--text-primary); border-color: var(--border-hover); }
        .ra-btn-ghost:disabled { opacity: 0.4; cursor: not-allowed; }

        .ra-label {
          font-size: 12px; font-weight: 700;
          color: rgba(167,139,250,0.8);
          text-transform: uppercase; letter-spacing: 0.8px;
          margin-bottom: 8px; display: block;
        }


        .coverage-upload {
          border: 1px dashed rgba(99,102,241,0.38);
          background: linear-gradient(135deg, rgba(99,102,241,0.09), rgba(236,72,153,0.05));
          border-radius: 14px;
          padding: 14px 16px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 14px;
        }
        .coverage-upload:hover { border-color: ${accent}80; background: ${accent}10; }
        .coverage-file-pill {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 7px 10px;
          border-radius: 999px;
          border: 1px solid rgba(52,211,153,0.24);
          background: rgba(52,211,153,0.08);
          color: #34d399;
          font-size: 12px;
          font-weight: 700;
          max-width: 100%;
        }

        .ra-row {
          display: flex; align-items: center; gap: 16px;
          padding: 14px 8px;
          border-bottom: 1px solid var(--border);
          border-radius: 8px; transition: background 0.15s;
        }
        .ra-row:last-child { border-bottom: none; }
        .ra-row:hover { background: var(--bg-card-hover); }

        .skeleton {
          background: linear-gradient(90deg, var(--bg-card) 25%, var(--bg-card-hover) 50%, var(--bg-card) 75%);
          background-size: 400% 100%; animation: shimmer 1.5s ease-in-out infinite; border-radius: 8px;
        }
        @keyframes shimmer { 0%{background-position:100% 50%} 100%{background-position:0% 50%} }

        .pulse-dot { width: 8px; height: 8px; border-radius: 50%; background: #fbbf24; animation: pulse 1.4s ease-in-out infinite; }
        @keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.4;transform:scale(0.8)} }

        .drop-zone {
          border: 1.5px dashed var(--border-hover);
          border-radius: 12px; padding: 32px 20px; text-align: center;
          cursor: pointer; transition: all 0.2s;
        }
        .drop-zone:hover, .drop-zone.active { border-color: ${accent}60; background: ${accent}08; }

        .ra-modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.75); backdrop-filter: blur(8px); z-index: 100; display: flex; align-items: center; justify-content: center; padding: 20px; animation: fadeIn 0.2s ease-out; }
        .ra-modal { background: var(--bg-base); border: 1px solid var(--border); border-radius: 16px; width: 100%; max-width: 900px; max-height: 90vh; display: flex; flex-direction: column; box-shadow: var(--shadow-card); overflow: hidden; animation: slideUp 0.3s ease-out; }
        .ra-modal-header { padding: 24px 30px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; background: var(--bg-card); }
        .ra-modal-body { padding: 30px; overflow-y: auto; flex: 1; }
        .ra-modal-footer { padding: 20px 30px; border-top: 1px solid var(--border); background: var(--bg-card); display: flex; justify-content: flex-end; gap: 12px; }
        .story-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 20px; }
        .task-badge { display: inline-flex; align-items: center; padding: 3px 8px; border-radius: 6px; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
        .task-badge.backend  { background: rgba(139,92,246,0.15); color: #a78bfa; }
        .task-badge.frontend { background: rgba(59,130,246,0.15);  color: #60a5fa; }
        .task-badge.qa       { background: rgba(245,158,11,0.15);   color: #fbbf24; }
        .edit-modal { background: var(--bg-sidebar); border: 1px solid var(--border-hover); border-radius: 16px; width: 100%; max-width: 500px; padding: 24px; box-shadow: var(--shadow-card); animation: zoomIn 0.2s ease-out; }
        .edit-textarea { width: 100%; min-height: 100px; padding: 12px 14px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 10px; color: var(--text-primary); font-family: 'DM Sans', sans-serif; font-size: 14px; outline: none; transition: border-color 0.2s; resize: vertical; box-sizing: border-box; }
        .edit-textarea:focus { border-color: ${accent}80; }
        .edit-textarea::placeholder { color: var(--text-faint); }

        @keyframes fadeIn  { from{opacity:0}             to{opacity:1}           }
        @keyframes slideUp { from{opacity:0;transform:translateY(20px)} to{opacity:1;transform:translateY(0)} }
        @keyframes zoomIn  { from{opacity:0;transform:scale(0.95)}      to{opacity:1;transform:scale(1)}      }
      `}</style>

      {/* Toast */}
      {toast.show && (
        <div style={{ position: "fixed", bottom: 28, right: 28, zIndex: 999, display: "flex", alignItems: "center", gap: 10, padding: "14px 20px", borderRadius: 12, background: toast.type === "success" ? "rgba(52,211,153,0.12)" : "rgba(248,113,113,0.12)", border: `1px solid ${toast.type === "success" ? "rgba(52,211,153,0.3)" : "rgba(248,113,113,0.3)"}`, backdropFilter: "blur(12px)", boxShadow: "var(--shadow-card)", maxWidth: 360 }}>
          {toast.type === "success"
            ? <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#34d399" strokeWidth="2.5" strokeLinecap="round"><polyline points="20 6 9 17 4 12"/></svg>
            : <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f87171" strokeWidth="2.5" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          }
          <span style={{ fontSize: 13.5, fontWeight: 500, color: toast.type === "success" ? "#34d399" : "#f87171" }}>{toast.msg}</span>
        </div>
      )}

      {/* Edit Modal */}
      {editModal.isOpen && (
        <div className="ra-modal-overlay" style={{ zIndex: 200 }}>
          <div className="edit-modal">
            <h3 style={{ margin: "0 0 16px", fontSize: 18, color: "var(--text-primary)", fontFamily: "'Syne', sans-serif" }}>{editModal.title}</h3>
            <textarea className="edit-textarea" value={editModal.text} onChange={e => setEditModal({ ...editModal, text: e.target.value })} placeholder="Type your changes here..." autoFocus />
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, marginTop: 20 }}>
              <button className="ra-btn-ghost" onClick={closeEditModal} disabled={isSavingEdit}>Cancel</button>
              <button className="ra-btn-primary" onClick={handleSaveEdit} disabled={isSavingEdit}>{isSavingEdit ? "Saving..." : "Save Changes"}</button>
            </div>
          </div>
        </div>
      )}

      {/* Merge Modal */}
      {mergeModal.isOpen && (
        <div className="ra-modal-overlay" style={{ zIndex: 200 }}>
          <div className="edit-modal">
            <h3 style={{ margin: "0 0 16px", fontSize: 18, color: "var(--text-primary)", fontFamily: "'Syne', sans-serif" }}>Merge Technical Tasks</h3>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>Edit the combined description. The tasks will be merged into a single task covering all their Acceptance Criteria.</div>
            <textarea className="edit-textarea" value={mergeModal.text} onChange={e => setMergeModal({ ...mergeModal, text: e.target.value })} style={{ minHeight: 150 }} autoFocus />
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, marginTop: 20 }}>
              <button className="ra-btn-ghost" onClick={() => setMergeModal({ isOpen: false, storyId: 0, text: "" })} disabled={isSavingEdit}>Cancel</button>
              <button className="ra-btn-primary" onClick={handleConfirmMerge} disabled={isSavingEdit}>{isSavingEdit ? "Merging..." : "Confirm Merge"}</button>
            </div>
          </div>
        </div>
      )}

      <ExtractedRequirementsReviewModal
        accent={accent}
        stories={showPrdModal ? prdStories as any : []}
        contributors={reviewContributors}
        selectedTaskIds={selectedTaskIds}
        setSelectedTaskIds={setSelectedTaskIds}
        onClose={() => setShowPrdModal(false)}
        onConfirm={confirmPRD}
        onEdit={openEditModal}
        onMerge={handleOpenMergeModal}
        onTaskUpdate={handleReviewTaskPatch as any}
      />

      {/* Legacy PRD Review Modal replaced by shared workflow component */}
      {false && showPrdModal && (
        <div className="ra-modal-overlay">
          <div className="ra-modal">
            <div className="ra-modal-header">
              <div>
                <h2 style={{ margin: 0, fontSize: 20, color: "var(--text-primary)", fontFamily: "'Syne', sans-serif" }}>Review Extracted Requirements</h2>
                <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>AI has extracted {prdStories.length} user stories. Review, edit if needed, and confirm to proceed.</div>
              </div>
              <button onClick={() => setShowPrdModal(false)} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 20, lineHeight: 1 }}>✕</button>
            </div>
            <div className="ra-modal-body">
              {prdStories.map(story => {
                const selectedInStory = story.technical_tasks.filter(t => selectedTaskIds.includes(t.id));
                return (
                  <div key={story.id} className="story-card">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ color: accent, fontWeight: 700, fontSize: 14 }}>{story.story_code}</span>
                        <span style={{ color: "var(--text-primary)", fontSize: 16, fontWeight: 600 }}>{story.title}</span>
                        <button onClick={() => openEditModal('story', story.id, story.title, "Edit Story Title")} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        </button>
                      </div>
                    </div>
                    <div style={{ fontSize: 13.5, color: "var(--text-secondary)", marginBottom: 16, background: "var(--bg-input)", padding: 12, borderRadius: 8, display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                      <div style={{ flex: 1, lineHeight: 1.6 }}>{story.description}</div>
                      <button onClick={() => openEditModal('story_desc', story.id, story.description, "Edit Story Description")} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", marginLeft: 12, flexShrink: 0 }}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                      </button>
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
                      <div>
                        <div style={{ fontSize: 12, fontWeight: 700, color: "rgba(167,139,250,0.8)", textTransform: "uppercase", letterSpacing: "0.8px", marginBottom: 8 }}>Acceptance Criteria</div>
                        <ul style={{ paddingLeft: 0, margin: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 6 }}>
                          {story.acceptance_criteria.map(ac => (
                            <li key={ac.id} style={{ display: "flex", alignItems: "flex-start", gap: 8, color: "var(--text-secondary)", fontSize: 13, lineHeight: 1.6, background: "var(--bg-card-hover)", padding: "6px 8px", borderRadius: 6 }}>
                              <span style={{ color: accent, marginTop: 2 }}>•</span>
                              <span style={{ flex: 1 }}>{ac.text}</span>
                              <button onClick={() => openEditModal('ac', story.id, ac.text, "Edit Acceptance Criteria", ac.id)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", marginTop: 2, flexShrink: 0 }}>
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                              </button>
                            </li>
                          ))}
                        </ul>
                      </div>
                      <div>
                        <div style={{ fontSize: 12, fontWeight: 700, color: "rgba(167,139,250,0.8)", textTransform: "uppercase", letterSpacing: "0.8px", marginBottom: 8, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span>Technical Tasks</span>
                          {selectedInStory.length >= 2 && (
                            <button className="ra-btn-primary" style={{ padding: "4px 10px", fontSize: 11, height: "auto" }} onClick={() => handleOpenMergeModal(story.id)}>
                              Merge {selectedInStory.length}
                            </button>
                          )}
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                          {story.technical_tasks.map(task => (
                            <div key={task.id} style={{ background: "var(--bg-card-hover)", padding: "10px 12px", borderRadius: 8, border: "1px solid var(--border)" }}>
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                  <input type="checkbox" checked={selectedTaskIds.includes(task.id)} onChange={e => { if (e.target.checked) setSelectedTaskIds([...selectedTaskIds, task.id]); else setSelectedTaskIds(selectedTaskIds.filter(id => id !== task.id)); }} style={{ width: 14, height: 14, cursor: "pointer", accentColor: accent }} />
                                  <span className={`task-badge ${task.type}`}>{task.type}</span>
                                </div>
                                <button onClick={() => openEditModal('task', story.id, task.description, "Edit Technical Task", task.id)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>
                                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                                </button>
                              </div>
                              <div style={{ fontSize: 13, color: "var(--text-primary)", lineHeight: 1.4 }}>{task.description}</div>
                              {task.ac_ids.length > 0 && <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>Covers AC: {task.ac_ids.map(id => `#${id}`).join(", ")}</div>}
                              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 10 }}>
                                <select
                                  className="ra-select"
                                  value={task.assigned_to ?? ""}
                                  onChange={e => handleReviewTaskPatch(task.id, { assigned_to: e.target.value ? Number(e.target.value) : null })}
                                  style={{ padding: "7px 9px", fontSize: 12 }}
                                >
                                  <option value="">Unassigned</option>
                                  {reviewContributors.filter(c => !task.type || !c.specialization || c.specialization === task.type).map(c => (
                                    <option key={c.id} value={c.id}>{c.full_name || c.username}</option>
                                  ))}
                                </select>
                                <select
                                  className="ra-select"
                                  value={task.status || "todo"}
                                  onChange={e => handleReviewTaskPatch(task.id, { status: e.target.value })}
                                  style={{ padding: "7px 9px", fontSize: 12 }}
                                >
                                  <option value="todo">To Do</option>
                                  <option value="in_progress">In Progress</option>
                                  <option value="done">Done</option>
                                </select>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="ra-modal-footer">
              <button className="ra-btn-ghost" onClick={() => setShowPrdModal(false)}>Cancel</button>
              <button className="ra-btn-primary" onClick={confirmPRD}>Confirm & Publish</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Page ── */}
      <div style={{
        minHeight: "100vh",
        padding: "36px 40px 80px",
        color: "var(--text-primary)",
        fontFamily: "'DM Sans', sans-serif",
        background: "var(--bg-gradient)",
      }}>
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
              Repository Analysis
            </div>
            <h1 style={{ fontFamily: "'Syne', sans-serif", fontSize: 26, fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-0.5px", margin: "0 0 4px" }}>
              Analyze GitHub repositories
            </h1>
            <p style={{ fontSize: 13.5, color: "var(--text-muted)", margin: 0, lineHeight: 1.6 }}>
              Convert source code into SonarQube health metrics and track repository health over time.
            </p>
          </div>

          {/* ── Analyze card ── */}
          {card(
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 34, height: 34, borderRadius: 10, background: `${accent}18`, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                </div>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>{analysisMode === "requirements" ? "Analyze + Requirements" : "Analyze Only"}</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{analysisMode === "requirements" ? "Upload a PRD, review and confirm requirements, then analyze the repository and detect coverage." : "Enter a public or private GitHub repository to analyze developer skills."}</div>
                </div>
              </div>

              {role === "manager" && (
                <div style={{ display: "inline-flex", gap: 8, padding: 4, background: "var(--bg-input)", border: "1px solid var(--border)", borderRadius: 12, width: "fit-content" }}>
                  <button
                    onClick={() => setAnalysisMode("analyze")}
                    style={{
                      padding: "8px 14px",
                      border: "none",
                      borderRadius: 9,
                      cursor: "pointer",
                      background: analysisMode === "analyze" ? `${accent}24` : "transparent",
                      color: analysisMode === "analyze" ? accent : "var(--text-muted)",
                      fontWeight: 700,
                    }}
                  >
                    Analyze Only
                  </button>
                  <button
                    onClick={() => setAnalysisMode("requirements")}
                    style={{
                      padding: "8px 14px",
                      border: "none",
                      borderRadius: 9,
                      cursor: "pointer",
                      background: analysisMode === "requirements" ? `${accent}24` : "transparent",
                      color: analysisMode === "requirements" ? accent : "var(--text-muted)",
                      fontWeight: 700,
                    }}
                  >
                    Analyze + Requirements
                  </button>
                </div>
              )}

              <div>
                <label className="ra-label">GitHub Repository URL</label>
                <div style={{ position: "relative" }}>
                  <div style={{ position: "absolute", left: 13, top: "50%", transform: "translateY(-50%)", color: "var(--text-faint)" }}>
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
                  </div>
                  <input type="text" className={`ra-input${urlError ? " error" : ""}`} style={{ paddingLeft: 38 }} placeholder="https://github.com/owner/repository" value={repoUrl} onChange={e => { setRepoUrl(e.target.value); setUrlError(""); }} />
                </div>
                {urlError && (
                  <div style={{ marginTop: 6, fontSize: 12.5, color: "#f87171", display: "flex", alignItems: "center", gap: 5 }}>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                    {urlError}
                  </div>
                )}
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <div>
                  <label className="ra-label">Programming Language</label>
                  <select className="ra-select" value={programmingLanguage} onChange={e => setProgrammingLanguage(e.target.value)}>
                    <option value="python">Python (MVP)</option>
                  </select>
                  <div style={{ marginTop: 6, fontSize: 11.5, color: "var(--text-muted)" }}>
                    Multi-language support is planned beyond MVP.
                  </div>
                </div>
                <div>
                  <label className="ra-label">Branch (Optional)</label>
                  <input
                    type="text"
                    className="ra-input"
                    placeholder="main"
                    value={branch}
                    onChange={e => setBranch(e.target.value)}
                  />
                </div>
              </div>

              <div>
                <label className="ra-label">Coverage Report (Optional)</label>
                <div className="coverage-upload">
                  <div style={{ minWidth: 0, display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{ width: 38, height: 38, borderRadius: 12, background: `${accent}18`, color: accent, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 15h8"/><path d="M8 18h5"/></svg>
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 13.5, fontWeight: 800, color: "var(--text-primary)" }}>Upload coverage.xml</div>
                      <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2, lineHeight: 1.45 }}>
                        Optional. If uploaded, SonarQube imports it. If not, SkillPulse will look for coverage.xml in the repository.
                      </div>
                      {coverageFile && (
                        <div className="coverage-file-pill" style={{ marginTop: 9 }}>
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{coverageFile.name}</span>
                          <button
                            type="button"
                            onClick={() => { setCoverageFile(null); setCoverageFileError(""); if (coverageInputRef.current) coverageInputRef.current.value = ""; }}
                            style={{ border: "none", background: "transparent", color: "inherit", cursor: "pointer", fontWeight: 900, padding: 0 }}
                            aria-label="Remove coverage file"
                          >
                            ×
                          </button>
                        </div>
                      )}
                    </div>
                  </div>

                  <input
                    ref={coverageInputRef}
                    type="file"
                    accept=".xml,text/xml,application/xml"
                    style={{ display: "none" }}
                    onChange={(e) => handleCoverageFileChange(e.target.files?.[0] || null)}
                  />
                  <button type="button" className="ra-btn-ghost" onClick={() => coverageInputRef.current?.click()}>
                    {coverageFile ? "Change file" : "Choose file"}
                  </button>
                </div>
                {coverageFileError && (
                  <div style={{ marginTop: 6, fontSize: 12.5, color: "#f87171" }}>{coverageFileError}</div>
                )}
              </div>

              {githubAuthUrl && role !== "recruiter" && (
                <div style={{ padding: "14px 16px", background: "rgba(251,191,36,0.07)", border: "1px solid rgba(251,191,36,0.2)", borderRadius: 12, display: "flex", alignItems: "center", gap: 14 }}>
                  <div style={{ width: 36, height: 36, borderRadius: 10, flexShrink: 0, background: "rgba(251,191,36,0.12)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="#fbbf24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13.5, fontWeight: 700, color: "#fbbf24", marginBottom: 3 }}>GitHub Connection Required</div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.5 }}>Connect GitHub so SkillPulse can verify access to private repositories.</div>
                  </div>
                  <button onClick={() => { window.location.href = githubAuthUrl; }} style={{ flexShrink: 0, padding: "9px 18px", background: "linear-gradient(135deg,#f59e0b,#fbbf24)", border: "none", borderRadius: 9, color: "#0a0a0f", fontSize: 13, fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap" as const }}>
                    Connect GitHub →
                  </button>
                </div>
              )}

              {(cachedMsg || failedMsg) && (
                <div style={{
                  padding: "12px 14px",
                  borderRadius: 10,
                  background: cachedMsg ? "rgba(52,211,153,0.08)" : "rgba(248,113,113,0.08)",
                  border: `1px solid ${cachedMsg ? "rgba(52,211,153,0.22)" : "rgba(248,113,113,0.22)"}`,
                  color: cachedMsg ? "#34d399" : "#f87171",
                  fontSize: 12.5,
                  fontWeight: 600,
                }}>
                  {cachedMsg ? `${cachedMsg.repoName} is already analyzed and ready.` : (failedMsg === "__rate_limit__" ? "GitHub rate limit reached. Try again later or connect GitHub." : failedMsg)}
                </div>
              )}

              {analysisMode === "analyze" && <div>
                <button className="ra-btn-primary" disabled={loading} onClick={() => startAnalysis(repoUrl, branch)}>
                  {loading
                    ? <><div className="pulse-dot" />Analyzing Code…</>
                    : <><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>Analyze Repository</>
                  }
                </button>
              </div>}

              {role === "manager" && analysisMode === "requirements" && (
                <div style={{ borderTop: "1px solid var(--border)", paddingTop: 20, display: "flex", flexDirection: "column", gap: 14 }}>
                  <div style={{
                    padding: "12px 14px",
                    borderRadius: 10,
                    background: requirementsAnalysisReady ? "rgba(52,211,153,0.08)" : "rgba(251,191,36,0.08)",
                    border: `1px solid ${requirementsAnalysisReady ? "rgba(52,211,153,0.22)" : "rgba(251,191,36,0.22)"}`,
                    color: requirementsAnalysisReady ? "#34d399" : "#fbbf24",
                    fontSize: 12.5,
                    fontWeight: 600,
                  }}>
                    {requirementsAnalysisMsg || "Upload a PRD to extract requirements. Repository analysis and coverage run after confirmation."}
                  </div>

                  <PrdUploadDropZone accent={accent} uploading={uploadingPrd} onFile={handlePrdUpload} disabledMessage={!repoUrl.trim() ? "Enter a GitHub repository URL first." : undefined} />
                  <button className="ra-btn-primary" disabled={!requirementsConfirmed || loading} onClick={analyzeAndDetectCoverage}>
                    {loading ? <><div className="pulse-dot" />Analyzing…</> : "Analyze Repository & Detect Coverage"}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* ── Manager PRD card ── */}
          {false && role === "manager" && card(
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 34, height: 34, borderRadius: 10, background: `${accent}18`, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                </div>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>2. Upload Business Requirements (PRD)</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Map user stories and tasks to a previously analyzed repository.</div>
                </div>
              </div>

              <div>
                <label className="ra-label">Select Target Repository</label>
                <select className="ra-select" value={selectedRepoForPrd} onChange={e => setSelectedRepoForPrd(e.target.value ? Number(e.target.value) : "")}>
                  <option value="">-- Choose an analyzed repository --</option>
                  {analyses.map(a => <option key={a.repo_id} value={a.repo_id}>{a.repo_name} ({a.branch})</option>)}
                </select>
              </div>

              <div className={`drop-zone${dragOver ? " active" : ""}`} onDrop={handleDrop} onDragOver={e => { e.preventDefault(); setDragOver(true); }} onDragLeave={() => setDragOver(false)} onClick={() => { if (selectedRepoForPrd === "") { alert("Please select a repository first."); } else { fileInputRef.current?.click(); } }}>
                {uploadingPrd ? (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
                    <div className="pulse-dot" style={{ background: accent }} />
                    <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>Extracting AI Requirements...</div>
                  </div>
                ) : file ? (
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10 }}>
                    <div style={{ width: 34, height: 34, borderRadius: 8, background: `${accent}18`, display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={accent} strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    </div>
                    <div style={{ textAlign: "left" as const }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{file!.name}</div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{(file!.size / 1024 / 1024).toFixed(2)} MB</div>
                    </div>
                  </div>
                ) : (
                  <>
                    <div style={{ width: 40, height: 40, borderRadius: "50%", background: "var(--bg-card-hover)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 12px" }}>
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                    </div>
                    <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 4 }}>
                      Drop your PRD here or <span style={{ color: accent }}>browse</span>
                    </div>
                  </>
                )}
              </div>
              <input ref={fileInputRef} type="file" accept=".pdf,.xlsx,.xls,.md,.txt" style={{ display: "none" }} onChange={e => { const f = e.target.files?.[0]; if (f) handlePrdUpload(f); }} />
            </div>
          )}

          {/* ── Recent Analyses ── */}
          {card(
            <>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{ width: 34, height: 34, borderRadius: 10, background: "var(--bg-card-hover)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                  </div>
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>Recent Analyses</div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                      {historyError ? "History could not be loaded" : `${analyses.length} ${analyses.length === 1 ? "repository" : "repositories"} analyzed`}
                    </div>
                  </div>
                </div>
                <button className="ra-btn-ghost" style={{ fontSize: 12, padding: "7px 13px" }} onClick={() => fetchHistory()}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                  Refresh
                </button>
              </div>

              {historyLoading && (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  {[1,2,3].map(i => (
                    <div key={i} style={{ display: "flex", gap: 14, alignItems: "center" }}>
                      <div className="skeleton" style={{ width: 48, height: 48, borderRadius: 12, flexShrink: 0 }} />
                      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8 }}>
                        <div className="skeleton" style={{ height: 14, width: "45%" }} />
                        <div className="skeleton" style={{ height: 11, width: "30%" }} />
                      </div>
                      <div className="skeleton" style={{ width: 50, height: 50, borderRadius: "50%" }} />
                    </div>
                  ))}
                </div>
              )}

              {!historyLoading && historyError && (
                <div style={{ textAlign: "center", padding: "48px 20px" }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "#f87171", marginBottom: 4 }}>Could not load analysis history</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{historyError}</div>
                </div>
              )}

              {!historyLoading && !historyError && analyses.length === 0 && (
                <div style={{ textAlign: "center", padding: "48px 20px" }}>
                  <div style={{ width: 56, height: 56, borderRadius: 16, background: "var(--bg-card-hover)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px" }}>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--text-faint)" strokeWidth="1.5" strokeLinecap="round"><path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/></svg>
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 4 }}>No analyses yet</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Enter a repository URL above to get started</div>
                </div>
              )}

              {!historyLoading && analyses.map(a => {
                const st = statusConfig[a.status] || statusConfig.pending;
                const sc = a.skill_score;
                const sColor = scoreColor(sc);
                return (
                  <div key={a.analysis_id} className="ra-row">
                    <div style={{ width: 44, height: 44, borderRadius: 12, flexShrink: 0, background: "var(--bg-card-hover)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.8" strokeLinecap="round"><path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/></svg>
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                        <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const }}>{a.repo_name}</span>
                        <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 20, background: "rgba(99,102,241,0.15)", color: "#818cf8", flexShrink: 0 }}>Python</span>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{a.branch} · {timeAgo(a.triggered_at)}</span>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 500, padding: "2px 8px", borderRadius: 20, background: st.bg, color: st.color, flexShrink: 0 }}>
                          <span style={{ width: 5, height: 5, borderRadius: "50%", background: st.dot, animation: a.status === "running" ? "pulse 1.4s ease-in-out infinite" : "none" }} />
                          {st.label}
                        </span>
                      </div>
                      {role === "manager" && (
                        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" as const, marginTop: 7 }}>
                          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Sonar {formatScore(a.sonar_health_score)}</span>
                          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Gate {a.quality_gate || "N/A"}</span>
                          <span style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "capitalize" as const }}>{formatState(a.sonar_state)}</span>
                        </div>
                      )}
                    </div>
                    <div style={{ textAlign: "right" as const, flexShrink: 0 }}>
                      {sc !== null ? (
                        <>
                          <div style={{ fontSize: 22, fontWeight: 800, color: sColor, lineHeight: 1 }}>{sc}</div>
                          <div style={{ fontSize: 10.5, color: "var(--text-muted)", marginTop: 2 }}>{a.skill_score_level || scoreLabel(sc)}</div>
                        </>
                      ) : <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Score unavailable</div>}
                    </div>
                  </div>
                );
              })}
            </>
          )}

        </div>
      </div>
    </DashboardLayout>
  );
}
