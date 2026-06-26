import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  BriefcaseBusiness,
  Check,
  ChevronRight,
  EyeOff,
  FileCheck2,
  Gauge,
  Mail,
  Pencil,
  RefreshCcw,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Target,
  UserCog,
  Users,
  X,
} from "lucide-react";
import api from "../../api/auth";
import DashboardLayout from "../DashboardLayout";

const accent = "#a855f7";

interface RecruiterProfileData {
  user: {
    id?: number;
    full_name: string;
    username: string;
    email: string;
    role?: string | null;
    avatar_url: string | null;
    organization: string | null;
    job_title: string | null;
    department: string | null;
    hiring_focus: string | null;
    member_since: string | null;
    has_password?: boolean;
    security_score_visible: boolean | null;
    high_priority_threshold: number | null;
    weight_code_quality: number | null;
    weight_architecture: number | null;
    weight_maintainability: number | null;
    weight_security: number | null;
    weight_git_activity: number | null;
  };
  talent_overview: {
    candidates_evaluated: number;
    high_priority: number;
    profiles_shortlisted: number;
  };
  recent_activity: Array<{
    title: string;
    description: string;
    sonar_health_score: number | null;
    sonar_state?: string;
    quality_gate?: string | null;
    completed_at: string | null;
  }>;
}

type SettingsView = "account" | "preferences" | "threshold" | "security";

const emptyProfile: RecruiterProfileData = {
  user: {
    full_name: "",
    username: "",
    email: "",
    role: "recruiter",
    avatar_url: null,
    organization: null,
    job_title: null,
    department: null,
    hiring_focus: null,
    member_since: null,
    has_password: false,
    security_score_visible: true,
    high_priority_threshold: 75,
    weight_code_quality: 20,
    weight_architecture: 20,
    weight_maintainability: 20,
    weight_security: 20,
    weight_git_activity: 20,
  },
  talent_overview: {
    candidates_evaluated: 0,
    high_priority: 0,
    profiles_shortlisted: 0,
  },
  recent_activity: [],
};

const settingRows: Array<{ key: SettingsView; label: string; description: string; icon: typeof UserCog }> = [
  {
    key: "account",
    label: "Account Settings",
    description: "Manage your account details, password, and deletion",
    icon: UserCog,
  },
  {
    key: "preferences",
    label: "Evaluation Preferences",
    description: "Adjust scoring weights for candidate analysis",
    icon: SlidersHorizontal,
  },
  {
    key: "threshold",
    label: "Priority Thresholds",
    description: "Choose the score that marks candidates as high priority",
    icon: Gauge,
  },
  {
    key: "security",
    label: "Security Visibility",
    description: "Show or hide security scores in recruiter reports",
    icon: ShieldCheck,
  },
];

const initials = (name: string) =>
  name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0])
    .join("")
    .toUpperCase() || "SP";

const fmtDate = (value: string | null) => {
  if (!value) return "Not set";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not set";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
};

const fmtAgo = (value: string | null) => {
  if (!value) return "just now";
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months} mo ago`;
  return `${Math.floor(months / 12)} yr ago`;
};

const fmtNumber = (value: number) => Number(value || 0).toLocaleString();

function Toggle({
  checked,
  onChange,
  title,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  title: string;
}) {
  return (
    <button
      type="button"
      className={`rp-toggle ${checked ? "is-on" : ""}`}
      onClick={() => onChange(!checked)}
      title={title}
      aria-pressed={checked}
    >
      <span />
    </button>
  );
}

function Skeleton() {
  return (
    <div className="rp-stack">
      <div className="rp-panel rp-skeleton" style={{ height: 260 }} />
      <div className="rp-kpi-grid">
        {[1, 2, 3].map(item => <div key={item} className="rp-card rp-skeleton" style={{ height: 118 }} />)}
      </div>
      <div className="rp-panel rp-skeleton" style={{ height: 240 }} />
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="rp-section-title">{children}</h2>;
}

export default function RecruiterProfilePage() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<RecruiterProfileData>(emptyProfile);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({ organization: "", job_title: "", department: "", hiring_focus: "" });
  const [editSaving, setEditSaving] = useState(false);
  const [activeView, setActiveView] = useState<SettingsView>("preferences");
  const [showAllActivities, setShowAllActivities] = useState(false);
  const [savingEval, setSavingEval] = useState(false);
  const [securityOn, setSecurityOn] = useState(true);
  const [threshold, setThreshold] = useState(75);

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok });
    window.setTimeout(() => setToast(null), 2600);
  };

  const applyProfileState = (data: RecruiterProfileData) => {
    setProfile(data);
    setEditForm({
      organization: data.user.organization || "",
      job_title: data.user.job_title || "",
      department: data.user.department || "",
      hiring_focus: data.user.hiring_focus || "",
    });
    setSecurityOn(data.user.security_score_visible ?? true);
    setThreshold(data.user.high_priority_threshold ?? 75);
  };

  const loadProfile = async () => {
    setError(null);
    setLoading(true);
    try {
      const response = await api.get<RecruiterProfileData>("/recruiter/profile-dashboard");
      applyProfileState(response.data);
    } catch {
      setError("Unable to load recruiter profile.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProfile();
  }, []);

  const handleEditClick = () => {
    setEditForm({
      organization: profile.user.organization || "",
      job_title: profile.user.job_title || "",
      department: profile.user.department || "",
      hiring_focus: profile.user.hiring_focus || "",
    });
    setEditing(true);
  };

  const handleEditSave = async () => {
    setEditSaving(true);
    try {
      const response = await api.patch("/recruiter/profile", {
        organization: editForm.organization || null,
        job_title: editForm.job_title || null,
        department: editForm.department || null,
        hiring_focus: editForm.hiring_focus || null,
      });
      setProfile(prev => ({ ...prev, user: { ...prev.user, ...response.data } }));
      setEditing(false);
      showToast("Profile updated");
    } catch {
      showToast("Could not save profile", false);
    } finally {
      setEditSaving(false);
    }
  };

  const saveEvalSettings = useCallback(async (patch: Record<string, unknown>) => {
    setSavingEval(true);
    try {
      const response = await api.patch("/recruiter/eval-settings", patch);
      setProfile(prev => ({ ...prev, user: { ...prev.user, ...response.data } }));
      showToast("Settings saved");
    } catch {
      showToast("Failed to save settings", false);
    } finally {
      setSavingEval(false);
    }
  }, []);

  const saveThreshold = async () => {
    await saveEvalSettings({ high_priority_threshold: threshold });
  };

  const toggleSecurity = async (next: boolean) => {
    setSecurityOn(next);
    await saveEvalSettings({ security_score_visible: next });
  };

  const infoGrid = useMemo(
    () => [
      { label: "Organization", value: profile.user.organization || "Not set", icon: BriefcaseBusiness },
      { label: "Department", value: profile.user.department || "Not set", icon: Users },
      { label: "Hiring Focus", value: profile.user.hiring_focus || "Not set", icon: Target },
      { label: "Member Since", value: fmtDate(profile.user.member_since), icon: Sparkles },
    ],
    [profile],
  );

  const visibleActivities = showAllActivities ? profile.recent_activity : profile.recent_activity.slice(0, 5);

  const renderSettings = () => {
    if (activeView === "account") {
      return (
        <section className="rp-panel">
          <div className="rp-panel-head">
            <div>
              <h2>Account Settings</h2>
              <span>Edit account details, change password, or delete the account.</span>
            </div>
          </div>
          <button className="rp-btn primary" type="button" onClick={() => navigate("/dashboard/recruiter/account-settings")}>
            Open Account Settings <ChevronRight size={16} />
          </button>
        </section>
      );
    }

    if (activeView === "threshold") {
      return (
        <section className="rp-panel">
          <div className="rp-panel-head">
            <div>
              <h2>Priority Thresholds</h2>
              <span>Candidates at or above this score are marked high priority.</span>
            </div>
          </div>
          <div className="rp-slider-block">
            <div className="rp-slider-label"><strong>High priority score</strong><span>{threshold}%</span></div>
            <input type="range" min={0} max={100} value={threshold} onChange={event => setThreshold(Number(event.target.value))} />
          </div>
          <div className="rp-actions">
            <button className="rp-btn primary" type="button" disabled={savingEval} onClick={saveThreshold}>
              Save Threshold
            </button>
          </div>
        </section>
      );
    }

    if (activeView === "security") {
      return (
        <section className="rp-panel">
          <div className="rp-panel-head">
            <div>
              <h2>Security Visibility</h2>
              <span>Control whether security scores appear in candidate reports.</span>
            </div>
            <Toggle checked={securityOn} onChange={toggleSecurity} title="Security score visibility" />
          </div>
          <div className={`rp-notice ${securityOn ? "" : "danger"}`}>
            {securityOn ? <ShieldCheck size={16} /> : <EyeOff size={16} />}
            <span>{securityOn ? "Security scores are visible in recruiter reports." : "Security scores are currently hidden in recruiter reports."}</span>
          </div>
        </section>
      );
    }

    return (
      <section className="rp-panel">
        <div className="rp-panel-head">
          <div>
            <h2>Evaluation Preferences</h2>
            <span>Candidate ranking now uses the Skill Score Engine.</span>
          </div>
        </div>
        <div className="rp-notice">
          <AlertTriangle size={16} />
          <span>Legacy weighting sliders are disabled and no longer affect candidate ranking or comparison.</span>
        </div>
      </section>
    );
  };

  return (
    <DashboardLayout>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        .rp-page {
          min-height: 100vh;
          background: var(--bg-gradient);
          color: var(--text-primary);
          font-family: 'Inter', system-ui, sans-serif;
          padding: 36px 40px 80px;
        }
        .rp-shell {
          max-width: 960px;
          margin: 0 auto;
          display: flex;
          flex-direction: column;
          gap: 24px;
        }
        .rp-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 18px;
          flex-wrap: wrap;
        }
        .rp-title h1 {
          margin: 0 0 4px;
          font-family: 'Inter', sans-serif;
          font-size: 26px;
          font-weight: 800;
          line-height: 1.15;
          letter-spacing: 0;
        }
        .rp-title p {
          margin: 0;
          color: var(--text-muted);
          font-size: 13.5px;
          line-height: 1.6;
        }
        .rp-badge {
          display: inline-flex;
          align-items: center;
          width: fit-content;
          margin-bottom: 10px;
          padding: 5px 14px;
          border-radius: 999px;
          border: 1px solid ${accent}40;
          background: ${accent}12;
          color: ${accent};
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.8px;
          text-transform: uppercase;
        }
        .rp-panel,
        .rp-card,
        .rp-activity-row {
          border: 1px solid var(--border);
          border-radius: 16px;
          background: var(--bg-card);
        }
        .rp-panel { padding: 24px 28px; }
        .rp-identity {
          display: flex;
          gap: 18px;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 24px;
        }
        .rp-identity-left {
          display: flex;
          gap: 18px;
          align-items: center;
          min-width: 0;
        }
        .rp-avatar {
          width: 76px;
          height: 76px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: hidden;
          flex-shrink: 0;
          background: linear-gradient(135deg, ${accent}, #ec4899);
          color: white;
          font-size: 26px;
          font-weight: 800;
          border: 2px solid ${accent}40;
        }
        .rp-avatar img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .rp-name h2 {
          margin: 0 0 3px;
          font-size: 22px;
          font-weight: 800;
          color: var(--text-primary);
        }
        .rp-name p {
          margin: 0 0 10px;
          color: var(--text-muted);
          font-size: 13px;
        }
        .rp-chip-row {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        .rp-chip {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 4px 12px;
          border-radius: 20px;
          color: var(--text-secondary);
          background: var(--bg-card-hover);
          border: 1px solid var(--border);
          font-size: 12px;
          max-width: 100%;
        }
        .rp-chip span {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .rp-edit-form {
          margin-bottom: 20px;
          padding: 20px;
          border-radius: 12px;
          background: var(--bg-card-hover);
          border: 1px solid var(--border);
        }
        .rp-edit-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 14px;
          margin-bottom: 16px;
        }
        .rp-field {
          display: flex;
          flex-direction: column;
          gap: 6px;
          color: ${accent};
          font-size: 11px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.6px;
        }
        .rp-field input {
          width: 100%;
          min-height: 40px;
          border: 1px solid var(--border);
          border-radius: 8px;
          background: var(--bg-input, var(--bg-card));
          color: var(--text-primary);
          outline: 0;
          padding: 0 12px;
          font-family: 'Inter', system-ui, sans-serif;
          font-size: 13px;
          box-sizing: border-box;
          text-transform: none;
          letter-spacing: 0;
        }
        .rp-field input:focus { border-color: rgba(168,85,247,0.62); }
        .rp-info-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 16px;
          padding-top: 20px;
          border-top: 1px solid var(--border);
        }
        .rp-info-item {
          display: grid;
          grid-template-columns: 36px minmax(0, 1fr);
          gap: 12px;
          align-items: flex-start;
          min-width: 0;
        }
        .rp-info-item span {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 36px;
          height: 36px;
          border-radius: 10px;
          color: var(--text-muted);
          background: var(--bg-card-hover);
          border: 1px solid var(--border);
        }
        .rp-info-item small {
          display: block;
          color: var(--text-faint);
          font-size: 11px;
          font-weight: 600;
          margin-bottom: 3px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .rp-info-item strong {
          display: block;
          color: var(--text-primary);
          font-size: 14px;
          font-weight: 700;
          overflow-wrap: anywhere;
        }
        .rp-section-title,
        .rp-panel-head h2 {
          font-family: 'Inter', sans-serif;
          font-size: 18px;
          font-weight: 800;
          color: var(--text-primary);
          letter-spacing: 0;
          margin: 0 0 16px;
        }
        .rp-kpi-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
          gap: 12px;
        }
        .rp-card {
          min-height: 130px;
          padding: 20px 22px;
        }
        .rp-card-top {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          color: var(--text-secondary);
          font-size: 12px;
          font-weight: 600;
          margin-bottom: 14px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .rp-card-top svg { color: ${accent}; }
        .rp-card strong {
          display: block;
          font-size: 32px;
          font-weight: 900;
          line-height: 1;
          color: var(--text-primary);
          overflow-wrap: anywhere;
          margin-bottom: 6px;
        }
        .rp-card small {
          display: block;
          color: var(--text-muted);
          font-size: 12px;
        }
        .rp-panel-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 14px;
          margin-bottom: 16px;
        }
        .rp-panel-head h2 { margin: 0; }
        .rp-panel-head span {
          color: var(--text-muted);
          font-size: 12px;
        }
        .rp-activity-list,
        .rp-settings-grid,
        .rp-stack,
        .rp-two-col {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .rp-activity-row {
          display: grid;
          grid-template-columns: 38px minmax(0, 1fr) auto;
          gap: 14px;
          align-items: center;
          padding: 14px 16px;
          border-radius: 12px;
          background: var(--bg-card-hover);
        }
        .rp-activity-icon {
          width: 38px;
          height: 38px;
          border-radius: 10px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          color: ${accent};
          background: rgba(168,85,247,0.14);
        }
        .rp-activity-row strong {
          display: block;
          font-size: 13px;
          color: var(--text-primary);
        }
        .rp-activity-row p {
          margin: 3px 0 0;
          color: var(--text-muted);
          font-size: 12px;
          overflow-wrap: anywhere;
        }
        .rp-activity-time {
          color: var(--text-muted);
          font-size: 12px;
          white-space: nowrap;
          text-align: right;
        }
        .rp-activity-score {
          display: block;
          color: ${accent};
          font-weight: 800;
          margin-top: 2px;
        }
        .rp-link-button {
          border: 0;
          background: transparent;
          color: ${accent};
          padding: 0;
          font: inherit;
          font-size: 13px;
          font-weight: 800;
          cursor: pointer;
        }
        .rp-setting-row {
          display: flex;
          align-items: center;
          gap: 14px;
          padding: 15px 18px;
          border-radius: 12px;
          background: var(--bg-card);
          border: 1px solid var(--border);
          color: var(--text-secondary);
          cursor: pointer;
          transition: all 0.15s;
          text-align: left;
          text-decoration: none;
          font-size: 14px;
          font-weight: 500;
        }
        .rp-setting-row:hover,
        .rp-setting-row.is-active {
          background: var(--bg-card-hover);
          border-color: var(--border-hover);
          color: var(--text-primary);
        }
        .rp-setting-icon {
          width: 36px;
          height: 36px;
          border-radius: 10px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          background: var(--bg-card-hover);
          color: var(--text-secondary);
        }
        .rp-setting-copy {
          flex: 1;
          min-width: 0;
        }
        .rp-setting-copy strong {
          display: block;
          font-weight: 600;
          margin-bottom: 1px;
          color: inherit;
        }
        .rp-setting-copy small {
          display: block;
          color: var(--text-muted);
          font-size: 12px;
          font-weight: 400;
          line-height: 1.4;
        }
        .rp-btn {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 7px;
          min-height: 38px;
          border: 1px solid var(--border);
          border-radius: 9px;
          background: var(--bg-card);
          color: var(--text-secondary);
          padding: 0 16px;
          font-family: 'Inter', system-ui, sans-serif;
          font-size: 13px;
          font-weight: 700;
          cursor: pointer;
          transition: all 0.2s;
          white-space: nowrap;
        }
        .rp-btn:hover {
          background: var(--bg-card-hover);
          color: var(--text-primary);
          border-color: var(--border-hover);
        }
        .rp-btn.primary {
          border-color: transparent;
          color: white;
          background: ${accent};
        }
        .rp-btn:disabled {
          opacity: 0.58;
          cursor: not-allowed;
        }
        .rp-actions {
          display: flex;
          justify-content: flex-end;
          gap: 10px;
          margin-top: 16px;
          padding-top: 16px;
          border-top: 1px solid var(--border);
        }
        .rp-weight-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 14px;
        }
        .rp-slider-block {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .rp-slider-label {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          color: var(--text-secondary);
          font-size: 12px;
        }
        .rp-slider-label span {
          color: ${accent};
          font-weight: 800;
        }
        .rp-slider-block input[type="range"] {
          accent-color: ${accent};
          width: 100%;
        }
        .rp-notice {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-top: 14px;
          padding: 10px 12px;
          border: 1px solid rgba(168,85,247,0.28);
          border-radius: 10px;
          background: rgba(168,85,247,0.08);
          color: #d8b4fe;
          font-size: 12px;
          line-height: 1.5;
        }
        .rp-notice.danger {
          border-color: rgba(248,113,113,0.3);
          background: rgba(248,113,113,0.08);
          color: #fca5a5;
        }
        .rp-toggle {
          width: 46px;
          height: 26px;
          border-radius: 999px;
          border: 1px solid var(--border);
          background: var(--bg-card-hover);
          padding: 2px;
          cursor: pointer;
          transition: background 0.18s, border-color 0.18s;
        }
        .rp-toggle span {
          display: block;
          width: 20px;
          height: 20px;
          border-radius: 50%;
          background: var(--text-muted);
          transition: transform 0.18s, background 0.18s;
        }
        .rp-toggle.is-on {
          border-color: rgba(168,85,247,0.52);
          background: rgba(168,85,247,0.28);
        }
        .rp-toggle.is-on span {
          transform: translateX(20px);
          background: ${accent};
        }
        .rp-empty,
        .rp-error {
          border: 1px dashed var(--border-hover);
          border-radius: 8px;
          padding: 24px 16px;
          text-align: center;
          color: var(--text-muted);
          background: var(--bg-card);
          font-size: 13px;
        }
        .rp-error {
          border-style: solid;
          color: #f87171;
          background: rgba(248,113,113,0.09);
        }
        .rp-toast {
          position: fixed;
          right: 28px;
          bottom: 28px;
          z-index: 500;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 12px 16px;
          border-radius: 8px;
          border: 1px solid rgba(74,222,128,0.32);
          background: var(--bg-card);
          color: #4ade80;
          box-shadow: var(--shadow-card);
          font-size: 13px;
          font-weight: 800;
        }
        .rp-toast.bad {
          border-color: rgba(248,113,113,0.32);
          color: #f87171;
        }
        .rp-skeleton {
          background: linear-gradient(90deg, var(--bg-card) 25%, var(--bg-card-hover) 50%, var(--bg-card) 75%);
          background-size: 400% 100%;
          animation: rp-shimmer 1.4s ease-in-out infinite;
        }
        @keyframes rp-shimmer {
          0% { background-position: 100% 50%; }
          100% { background-position: 0 50%; }
        }
        @media (max-width: 1060px) {
          .rp-weight-grid { grid-template-columns: 1fr; }
        }
        @media (max-width: 760px) {
          .rp-page { padding: 24px 16px 56px; }
          .rp-edit-grid,
          .rp-info-grid { grid-template-columns: 1fr; }
          .rp-identity { flex-wrap: wrap; }
          .rp-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          .rp-activity-row { grid-template-columns: 38px minmax(0, 1fr); }
          .rp-activity-time { grid-column: 2; text-align: left; }
          .rp-actions,
          .rp-btn { width: 100%; }
          .rp-actions { flex-direction: column; }
        }
      `}</style>

      {toast && (
        <div className={`rp-toast ${toast.ok ? "" : "bad"}`}>
          {toast.ok ? <Check size={15} /> : <X size={15} />}
          {toast.msg}
        </div>
      )}

      <main className="rp-page">
        <div className="rp-shell">
          <header className="rp-header">
            <div className="rp-title">
              <div className="rp-badge">Recruiter Profile</div>
              <h1>Your profile & overview</h1>
              <p>Track candidate decisions, evaluation preferences, and recruiter account access.</p>
            </div>
            <button className="rp-btn" type="button" onClick={loadProfile}><RefreshCcw size={15} />Refresh</button>
          </header>

          {error && <div className="rp-error">{error}</div>}

          {loading ? (
            <Skeleton />
          ) : (
            <>
              <section className="rp-panel">
                <div className="rp-identity">
                  <div className="rp-identity-left">
                    <div className="rp-avatar">
                      {profile.user.avatar_url ? <img src={profile.user.avatar_url} alt="" /> : initials(profile.user.full_name)}
                    </div>
                    <div className="rp-name">
                      <h2>{profile.user.full_name}</h2>
                      <p>{profile.user.job_title || "Technical Recruiter"}</p>
                      <div className="rp-chip-row">
                        <span className="rp-chip"><UserCog size={13} /><span>@{profile.user.username}</span></span>
                        <span className="rp-chip"><Mail size={13} /><span>{profile.user.email}</span></span>
                      </div>
                    </div>
                  </div>
                  {!editing && (
                    <button className="rp-btn" type="button" onClick={handleEditClick}>
                      <Pencil size={15} />Edit Profile
                    </button>
                  )}
                </div>

                {editing && (
                  <div className="rp-edit-form">
                    <div className="rp-edit-grid">
                      <label className="rp-field">
                        Organization
                        <input value={editForm.organization} onChange={event => setEditForm(prev => ({ ...prev, organization: event.target.value }))} />
                      </label>
                      <label className="rp-field">
                        Job Title
                        <input value={editForm.job_title} onChange={event => setEditForm(prev => ({ ...prev, job_title: event.target.value }))} />
                      </label>
                      <label className="rp-field">
                        Department
                        <input value={editForm.department} onChange={event => setEditForm(prev => ({ ...prev, department: event.target.value }))} />
                      </label>
                      <label className="rp-field">
                        Hiring Focus
                        <input value={editForm.hiring_focus} onChange={event => setEditForm(prev => ({ ...prev, hiring_focus: event.target.value }))} />
                      </label>
                    </div>
                    <div className="rp-actions">
                      <button className="rp-btn" type="button" onClick={() => setEditing(false)} disabled={editSaving}>Cancel</button>
                      <button className="rp-btn primary" type="button" onClick={handleEditSave} disabled={editSaving}>
                        {editSaving ? "Saving..." : "Save Changes"}
                      </button>
                    </div>
                  </div>
                )}

                <div className="rp-info-grid">
                  {infoGrid.map(item => {
                    const Icon = item.icon;
                    return (
                      <div className="rp-info-item" key={item.label}>
                        <span><Icon size={16} /></span>
                        <div>
                          <small>{item.label}</small>
                          <strong>{item.value}</strong>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>

              <section>
                <SectionTitle>Talent Overview</SectionTitle>
                <div className="rp-kpi-grid">
                  <section className="rp-card">
                    <div className="rp-card-top"><span>Candidates Evaluated</span><Users size={18} /></div>
                    <strong>{fmtNumber(profile.talent_overview.candidates_evaluated)}</strong>
                    <small>Total completed evaluations</small>
                  </section>
                  <section className="rp-card">
                    <div className="rp-card-top"><span>High Priority</span><AlertTriangle size={18} /></div>
                    <strong>{fmtNumber(profile.talent_overview.high_priority)}</strong>
                    <small>Above current threshold</small>
                  </section>
                  <section className="rp-card">
                    <div className="rp-card-top"><span>Shortlisted</span><Sparkles size={18} /></div>
                    <strong>{fmtNumber(profile.talent_overview.profiles_shortlisted)}</strong>
                    <small>Marked for consideration</small>
                  </section>
                </div>
              </section>

              <section className="rp-panel">
                <div className="rp-panel-head">
                  <div>
                    <h2>Recent Activity</h2>
                  </div>
                  {profile.recent_activity.length > 5 && (
                    <button className="rp-link-button" type="button" onClick={() => setShowAllActivities(prev => !prev)}>
                      {showAllActivities ? "Show Less" : "View All Activities"}
                    </button>
                  )}
                </div>
                <div className="rp-activity-list">
                  {visibleActivities.map((item, index) => (
                    <article className="rp-activity-row" key={`${item.title}-${item.completed_at}-${index}`}>
                      <span className="rp-activity-icon"><FileCheck2 size={16} /></span>
                      <div>
                        <strong>{item.title}</strong>
                        <p>{item.description}</p>
                      </div>
                      <span className="rp-activity-time">
                        {fmtAgo(item.completed_at)}
                        {item.sonar_health_score !== null && <span className="rp-activity-score">{item.sonar_health_score}</span>}
                        {item.sonar_health_score === null && <span className="rp-activity-score">sonar_unavailable</span>}
                      </span>
                    </article>
                  ))}
                  {!visibleActivities.length && <div className="rp-empty">No recent activity yet.</div>}
                </div>
              </section>

              <div className="rp-two-col">
                <SectionTitle>Profile Settings</SectionTitle>
                <aside className="rp-settings-grid" aria-label="Recruiter profile settings">
                  {settingRows.map(row => {
                    const Icon = row.icon;
                    return (
                      <button
                        key={row.key}
                        type="button"
                        className={`rp-setting-row ${activeView === row.key ? "is-active" : ""}`}
                        onClick={() => {
                          if (row.key === "account") {
                            navigate("/dashboard/recruiter/account-settings");
                            return;
                          }
                          setActiveView(row.key);
                        }}
                      >
                        <span className="rp-setting-icon"><Icon size={17} /></span>
                        <span className="rp-setting-copy">
                          <strong>{row.label}</strong>
                          <small>{row.description}</small>
                        </span>
                        <ChevronRight size={16} />
                      </button>
                    );
                  })}
                </aside>
                {renderSettings()}
              </div>
            </>
          )}
        </div>
      </main>
    </DashboardLayout>
  );
}
