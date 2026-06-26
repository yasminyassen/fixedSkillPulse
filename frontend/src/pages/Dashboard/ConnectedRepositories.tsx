import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../../api/auth";
import DashboardLayout from "../DashboardLayout";

interface AnalyzedRepo {
  analysis_id: number; repo_id: number; repo_name: string; branch: string;
  status: string; triggered_at: string; completed_at: string | null; sonar_health_score: number | null; sonar_state: string;
}

const scoreColor = (s: number | null) => { if (s === null) return "#6b7280"; if (s >= 80) return "#34d399"; if (s >= 60) return "#fbbf24"; return "#f87171"; };
const timeAgo = (iso: string) => { const diff = Date.now() - new Date(iso).getTime(); const m = Math.floor(diff / 60000); if (m < 1) return "just now"; if (m < 60) return `${m}m ago`; const h = Math.floor(m / 60); if (h < 24) return `${h}h ago`; return `${Math.floor(h / 24)}d ago`; };

function Skeleton({ w, h, radius = 8 }: { w: number | string; h: number; radius?: number }) {
  return <div style={{ width: w, height: h, borderRadius: radius, background: "linear-gradient(90deg, var(--bg-card) 25%, var(--bg-card-hover) 50%, var(--bg-card) 75%)", backgroundSize: "400% 100%", animation: "shimmer 1.5s ease-in-out infinite" }} />;
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{ fontFamily: "'Inter', sans-serif", fontSize: "16px", fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-0.2px", margin: "0 0 16px", paddingBottom: "12px", borderBottom: "1px solid var(--border)" }}>
      {children}
    </h2>
  );
}

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "16px", padding: "24px 28px", transition: "background 0.3s ease, border-color 0.3s ease", ...style }}>
      {children}
    </div>
  );
}

function Toast({ msg, type }: { msg: string; type: "success" | "error" }) {
  return (
    <div style={{ position: "fixed", bottom: "28px", right: "28px", zIndex: 9999, padding: "12px 20px", borderRadius: "12px", background: type === "success" ? "rgba(52,211,153,0.12)" : "rgba(248,113,113,0.12)", border: `1px solid ${type === "success" ? "rgba(52,211,153,0.3)" : "rgba(248,113,113,0.3)"}`, color: type === "success" ? "#34d399" : "#f87171", fontSize: "13px", fontWeight: 600, display: "flex", alignItems: "center", gap: "8px", boxShadow: "0 8px 32px rgba(0,0,0,0.2)", fontFamily: "'Inter', sans-serif" }}>
      {type === "success" ? "✓" : "✕"} {msg}
    </div>
  );
}

export default function ConnectedRepositories() {
  const navigate = useNavigate();
  const role = localStorage.getItem("role") || "developer";
  const analysisDashPath = `/dashboard/${role}/analysis`;
  const [repos, setRepos] = useState<AnalyzedRepo[]>([]);
  const [loading, setLoading] = useState(true);
  const [disconnecting, setDisconnecting] = useState<number | null>(null);
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);

  const showToast = (msg: string, type: "success" | "error") => { setToast({ msg, type }); setTimeout(() => setToast(null), 3000); };

  const fetchRepos = async () => {
    setLoading(true);
    try { const res = await api.get("/analysis/history?limit=50"); setRepos(res.data.history ?? []); }
    catch (err: any) {
      if (err.response?.status === 401) { localStorage.clear(); window.location.href = "/login"; return; }
      showToast("Failed to load repositories", "error");
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchRepos(); }, []);

  const handleDisconnect = async (analysisId: number, repoName: string) => {
    setDisconnecting(analysisId);
    try { await api.delete(`/repos/disconnect-analysis/${analysisId}`); setRepos(prev => prev.filter(r => r.analysis_id !== analysisId)); showToast(`"${repoName}" disconnected`, "success"); }
    catch { showToast("Failed to disconnect. Please try again.", "error"); }
    finally { setDisconnecting(null); }
  };

  const completedRepos = repos.filter(r => r.status === "completed");

  return (
    <DashboardLayout>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        @keyframes shimmer { 0%{background-position:100% 50%} 100%{background-position:0% 50%} }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .repo-row { transition: background 0.15s; border-radius: 12px; }
        .repo-row:hover { background: var(--bg-card-hover); }
        .view-btn:hover { background: rgba(99,102,241,0.15) !important; border-color: rgba(99,102,241,0.4) !important; color: #a5b4fc !important; }
        .disc-btn:hover { background: rgba(248,113,113,0.12) !important; border-color: rgba(248,113,113,0.3) !important; color: #f87171 !important; }
      `}</style>

      {toast && <Toast msg={toast.msg} type={toast.type} />}

      <div style={{ padding: "32px 36px", maxWidth: "720px", fontFamily: "'Inter', sans-serif" }}>

        <div style={{ display: "flex", alignItems: "center", gap: "14px", marginBottom: "28px" }}>
          <button onClick={() => navigate("/dashboard/developer/profile")} style={{ width: 36, height: 36, borderRadius: "10px", border: "1px solid var(--border)", background: "var(--bg-card)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", cursor: "pointer" }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6" /></svg>
          </button>
          <div>
            <h1 style={{ fontFamily: "'Inter', sans-serif", fontSize: "24px", fontWeight: 800, color: "var(--text-primary)", margin: 0, letterSpacing: "-0.4px" }}>Connected Repositories</h1>
            <p style={{ fontSize: "13px", color: "var(--text-muted)", margin: "2px 0 0" }}>{loading ? "Loading…" : `${completedRepos.length} analyzed ${completedRepos.length === 1 ? "repository" : "repositories"}`}</p>
          </div>
        </div>

        <Card style={{ marginBottom: "16px" }}>
          <SectionTitle>Analyzed Repositories</SectionTitle>

          {loading && (
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              {[1, 2, 3].map(i => (
                <div key={i} style={{ display: "flex", gap: "14px", alignItems: "center", padding: "12px 0" }}>
                  <Skeleton w={44} h={44} radius={12} />
                  <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "8px" }}>
                    <Skeleton w="40%" h={14} /><Skeleton w="25%" h={11} />
                  </div>
                  <Skeleton w={56} h={32} radius={8} /><Skeleton w={80} h={32} radius={8} />
                </div>
              ))}
            </div>
          )}

          {!loading && completedRepos.length === 0 && (
            <div style={{ textAlign: "center", padding: "40px 20px" }}>
              <div style={{ width: "52px", height: "52px", borderRadius: "14px", background: "var(--bg-input)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 14px" }}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--text-faint)" strokeWidth="1.5">
                  <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/>
                </svg>
              </div>
              <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "4px" }}>No analyzed repositories yet</div>
              <div style={{ fontSize: "12px", color: "var(--text-muted)", marginBottom: "20px" }}>Analyze a repository to see it here</div>
              <button onClick={() => navigate(analysisDashPath)} style={{ padding: "9px 20px", borderRadius: "10px", border: "none", background: "#6366f1", color: "white", fontSize: "13px", fontWeight: 700, cursor: "pointer", fontFamily: "'Inter', sans-serif" }}>
                Analyze a Repository
              </button>
            </div>
          )}

          {!loading && completedRepos.map((repo) => {
            const sc = repo.sonar_health_score; const sColor = scoreColor(sc); const isDisconnecting = disconnecting === repo.analysis_id;
            return (
              <div key={repo.analysis_id} className="repo-row" style={{ display: "flex", alignItems: "center", gap: "14px", padding: "14px 8px", borderBottom: "1px solid var(--border)" }}>
                <div style={{ width: 44, height: 44, borderRadius: "12px", flexShrink: 0, background: "var(--bg-input)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.8">
                    <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/>
                  </svg>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginBottom: "3px" }}>{repo.repo_name}</div>
                  <div style={{ fontSize: "11.5px", color: "var(--text-muted)" }}>{repo.branch} · {repo.triggered_at ? timeAgo(repo.triggered_at) : "—"}</div>
                </div>
                {sc !== null && (
                  <div style={{ textAlign: "center", flexShrink: 0, padding: "4px 10px", borderRadius: "8px", background: `${sColor}15`, border: `1px solid ${sColor}30` }}>
                    <span style={{ fontSize: "16px", fontWeight: 800, color: sColor }}>{Math.round(sc)}</span>
                  </div>
                )}
                <button className="view-btn" onClick={() => navigate(`/analysis/${repo.analysis_id}`)} style={{ padding: "7px 14px", borderRadius: "8px", flexShrink: 0, border: "1px solid rgba(99,102,241,0.25)", background: "rgba(99,102,241,0.08)", color: "#818cf8", fontSize: "12px", fontWeight: 600, cursor: "pointer", fontFamily: "'Inter', sans-serif", transition: "all 0.15s", display: "flex", alignItems: "center", gap: "5px" }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                  View
                </button>
                <button className="disc-btn" onClick={() => handleDisconnect(repo.analysis_id, repo.repo_name)} disabled={isDisconnecting} title="Disconnect this analysis" style={{ padding: "7px 10px", borderRadius: "8px", flexShrink: 0, border: "1px solid var(--border)", background: "var(--bg-card)", color: "var(--text-muted)", fontSize: "12px", fontWeight: 600, cursor: isDisconnecting ? "not-allowed" : "pointer", fontFamily: "'Inter', sans-serif", transition: "all 0.15s", opacity: isDisconnecting ? 0.5 : 1, display: "flex", alignItems: "center", gap: "5px" }}>
                  {isDisconnecting ? (<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ animation: "spin 1s linear infinite" }}><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>) : (<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>)}
                </button>
              </div>
            );
          })}
        </Card>

        <div style={{ marginTop: "16px", textAlign: "center" }}>
          <button onClick={() => navigate(analysisDashPath)} style={{ display: "inline-flex", alignItems: "center", gap: "8px", padding: "10px 22px", borderRadius: "10px", border: "1px solid rgba(99,102,241,0.3)", background: "rgba(99,102,241,0.08)", color: "#818cf8", fontSize: "13px", fontWeight: 700, cursor: "pointer", fontFamily: "'Inter', sans-serif", transition: "all 0.15s" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Analyze a New Repository
          </button>
        </div>

      </div>
    </DashboardLayout>
  );
}
