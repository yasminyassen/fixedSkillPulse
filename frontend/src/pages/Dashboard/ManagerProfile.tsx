import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  BriefcaseBusiness,
  Check,
  ChevronRight,
  Mail,
  Pencil,
  RefreshCcw,
  ShieldCheck,
  Sparkles,
  UserCog,
  Users,
  X,
} from "lucide-react";
import api from "../../api/auth";
import DashboardLayout from "../DashboardLayout";

const accent = "#8b5cf6";

interface Profile {
  id: number;
  full_name: string;
  username: string;
  email: string;
  role: string | null;
  avatar_url: string | null;
  organization: string | null;
  department: string | null;
  job_title: string | null;
  member_since: string | null;
}

interface TeamOverview {
  team_members: number;
  repositories: number;
  ongoing_analyses: number;
  team_health: number;
}

interface ActivityItem {
  id: string;
  icon: string;
  title: string;
  description: string;
  time_ago: string;
}

const emptyProfile: Profile = {
  id: 0,
  full_name: "",
  username: "",
  email: "",
  role: "manager",
  avatar_url: null,
  organization: null,
  department: null,
  job_title: null,
  member_since: null,
};

const emptyOverview: TeamOverview = {
  team_members: 0,
  repositories: 0,
  ongoing_analyses: 0,
  team_health: 0,
};

const settingRows: Array<{ key: "account"; label: string; icon: typeof UserCog }> = [
  { key: "account", label: "Account Settings", icon: UserCog },
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

const fmtNumber = (value: number) => Number(value || 0).toLocaleString();

function Skeleton() {
  return (
    <div className="mp-stack">
      <div className="mp-panel mp-skeleton" style={{ height: 260 }} />
      <div className="mp-kpi-grid">
        {[1, 2, 3, 4].map(item => <div key={item} className="mp-card mp-skeleton" style={{ height: 118 }} />)}
      </div>
      <div className="mp-panel mp-skeleton" style={{ height: 240 }} />
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="mp-section-title">{children}</h2>;
}

export default function ManagerProfile() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<Profile>(emptyProfile);
  const [overview, setOverview] = useState<TeamOverview>(emptyOverview);
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [showAllActivities, setShowAllActivities] = useState(false);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ── Inline edit state ──
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({ organization: "", job_title: "" });
  const [editSaving, setEditSaving] = useState(false);

  const badgeName = profile.role ? profile.role.charAt(0).toUpperCase() + profile.role.slice(1) : "Manager";

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok });
    window.setTimeout(() => setToast(null), 2600);
  };

  const loadProfile = async () => {
    setError(null);
    setLoading(true);
    try {
      const [profileRes, overviewRes, activityRes] = await Promise.all([
        api.get<Profile>("/manager/profile"),
        api.get<TeamOverview>("/manager/profile/team-overview"),
        api.get<ActivityItem[]>("/manager/profile/activities", { params: { limit: 5 } }),
      ]);
      setProfile(profileRes.data);
      setOverview(overviewRes.data);
      setActivities(activityRes.data);
    } catch {
      setError("Unable to load manager profile.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProfile();
  }, []);

  const loadActivities = async (limit: number) => {
    const response = await api.get<ActivityItem[]>("/manager/profile/activities", { params: { limit } });
    setActivities(response.data);
  };

  const handleEditClick = () => {
    setEditForm({
      organization: profile.organization || "",
      job_title: profile.job_title || "",
    });
    setEditing(true);
  };

  const handleEditCancel = () => {
    setEditing(false);
  };

  const handleEditSave = async () => {
    setEditSaving(true);
    try {
      const response = await api.patch<Profile>("/manager/profile", {
        organization: editForm.organization || null,
        job_title: editForm.job_title || null,
      });
      setProfile(response.data);
      setEditing(false);
      showToast("Profile updated");
    } catch {
      showToast("Could not save profile", false);
    } finally {
      setEditSaving(false);
    }
  };

  const toggleActivities = async () => {
    const nextShowAll = !showAllActivities;
    setShowAllActivities(nextShowAll);
    try {
      await loadActivities(nextShowAll ? 20 : 5);
    } catch {
      showToast("Activities failed to load", false);
    }
  };

  const infoGrid = useMemo(
    () => [
      { label: "Organization", value: profile.organization || "Not set", icon: BriefcaseBusiness },
      { label: "Department", value: profile.department || "Not set", icon: Users },
      { label: "Role", value: badgeName, icon: ShieldCheck },
      { label: "Member Since", value: fmtDate(profile.member_since), icon: Sparkles },
    ],
    [profile, badgeName],
  );

  return (
    <DashboardLayout>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        .mp-page {
          min-height: 100vh;
          background: var(--bg-gradient);
          color: var(--text-primary);
          font-family: 'Inter', system-ui, sans-serif;
          padding: 36px 40px 80px;
        }
        .mp-shell {
          max-width: 960px;
          margin: 0 auto;
          display: flex;
          flex-direction: column;
          gap: 24px;
        }
        .mp-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 18px;
          flex-wrap: wrap;
        }
        .mp-title {
          min-width: 0;
        }
        .mp-title h1 {
          margin: 0 0 4px;
          font-family: 'Inter', sans-serif;
          font-size: 26px;
          font-weight: 800;
          line-height: 1.15;
          letter-spacing: -0.5px;
        }
        .mp-title p {
          margin: 0;
          color: var(--text-muted);
          font-size: 13.5px;
          line-height: 1.6;
        }
        .mp-badge {
          display: inline-flex;
          align-items: center;
          gap: 8px;
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
        .mp-hero-avatar img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .mp-header-actions {
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .mp-panel,
        .mp-card,
        .mp-activity-row {
          border: 1px solid var(--border);
          border-radius: 16px;
          background: var(--bg-card);
        }
        .mp-panel { padding: 24px 28px; }
        .mp-profile-panel {
          position: relative;
        }

        /* ── Identity row (avatar + name + edit button) ── */
        .mp-identity {
          display: flex;
          gap: 18px;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 24px;
        }
        .mp-identity-left {
          display: flex;
          gap: 18px;
          align-items: center;
          min-width: 0;
        }
        .mp-hero-avatar {
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
        .mp-name h2 {
          margin: 0 0 3px;
          font-size: 22px;
          font-weight: 800;
          color: var(--text-primary);
        }
        .mp-name p {
          margin: 0 0 10px;
          color: var(--text-muted);
          font-size: 13px;
        }

        /* ── Inline edit form ── */
        .mp-edit-form {
          margin-bottom: 20px;
          padding: 20px;
          border-radius: 12px;
          background: var(--bg-card-hover);
          border: 1px solid var(--border);
        }
        .mp-edit-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 14px;
          margin-bottom: 16px;
        }
        .mp-edit-field {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .mp-edit-field label {
          font-size: 11px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.6px;
          color: ${accent};
        }
        .mp-edit-field input {
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
          transition: border-color 0.15s;
        }
        .mp-edit-field input:focus {
          border-color: rgba(139,92,246,0.62);
        }
        .mp-edit-field input::placeholder {
          color: var(--text-muted);
        }
        .mp-edit-actions {
          display: flex;
          justify-content: flex-end;
          gap: 10px;
        }
        .mp-btn-cancel {
          display: inline-flex;
          align-items: center;
          gap: 7px;
          border: 1px solid var(--border);
          border-radius: 9px;
          background: var(--bg-card);
          color: var(--text-secondary);
          padding: 9px 16px;
          font-family: 'Inter', system-ui, sans-serif;
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s;
        }
        .mp-btn-cancel:hover {
          background: var(--bg-card-hover);
          color: var(--text-primary);
        }
        .mp-btn-save {
          display: inline-flex;
          align-items: center;
          gap: 7px;
          border: none;
          border-radius: 9px;
          background: linear-gradient(135deg, ${accent}, #ec4899);
          color: white;
          padding: 9px 20px;
          font-family: 'Inter', system-ui, sans-serif;
          font-size: 13px;
          font-weight: 700;
          cursor: pointer;
          transition: opacity 0.15s;
        }
        .mp-btn-save:hover { opacity: 0.88; }
        .mp-btn-save:disabled { opacity: 0.5; cursor: not-allowed; }

        .mp-chip-row {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        .mp-chip {
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
        .mp-chip span {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .mp-info-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 16px;
          padding-top: 20px;
          border-top: 1px solid var(--border);
        }
        .mp-info-item {
          display: grid;
          grid-template-columns: 36px minmax(0, 1fr);
          gap: 12px;
          align-items: flex-start;
          min-width: 0;
        }
        .mp-info-item span {
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
        .mp-info-item small {
          display: block;
          color: var(--text-faint);
          font-size: 11px;
          font-weight: 600;
          margin-bottom: 3px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .mp-info-item strong {
          display: block;
          color: var(--text-primary);
          font-size: 14px;
          font-weight: 700;
          overflow-wrap: anywhere;
        }
        .mp-section-title {
          font-family: 'Inter', sans-serif;
          font-size: 18px;
          font-weight: 800;
          color: var(--text-primary);
          letter-spacing: -0.3px;
          margin: 0 0 16px;
        }
        .mp-kpi-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
          gap: 12px;
        }
        .mp-card {
          min-height: 130px;
          padding: 20px 22px;
        }
        .mp-card-top {
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
        .mp-card-top svg {
          color: ${accent};
        }
        .mp-card strong {
          display: block;
          font-size: 32px;
          font-weight: 900;
          line-height: 1;
          color: var(--text-primary);
          overflow-wrap: anywhere;
          margin-bottom: 6px;
        }
        .mp-card small {
          display: block;
          color: var(--text-muted);
          font-size: 12px;
        }
        .mp-panel-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 14px;
          margin-bottom: 16px;
        }
        .mp-panel-head h2 {
          margin: 0;
          font-family: 'Inter', sans-serif;
          font-size: 18px;
          font-weight: 800;
          color: var(--text-primary);
          letter-spacing: -0.3px;
        }
        .mp-panel-head span {
          color: var(--text-muted);
          font-size: 12px;
        }
        .mp-activity-list,
        .mp-settings-grid,
        .mp-stack {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .mp-activity-row {
          display: grid;
          grid-template-columns: 38px minmax(0, 1fr) auto;
          gap: 14px;
          align-items: center;
          padding: 14px 16px;
          border-radius: 12px;
          background: var(--bg-card-hover);
        }
        .mp-activity-icon {
          width: 38px;
          height: 38px;
          border-radius: 10px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          color: ${accent};
          background: rgba(139,92,246,0.14);
        }
        .mp-activity-row strong {
          display: block;
          font-size: 13px;
          color: var(--text-primary);
        }
        .mp-activity-row p {
          margin: 3px 0 0;
          color: var(--text-muted);
          font-size: 12px;
          overflow-wrap: anywhere;
        }
        .mp-activity-time {
          color: var(--text-muted);
          font-size: 12px;
          white-space: nowrap;
        }
        .mp-link-button {
          border: 0;
          background: transparent;
          color: ${accent};
          padding: 0;
          font: inherit;
          font-size: 13px;
          font-weight: 800;
          cursor: pointer;
        }
        .mp-settings-section {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .mp-setting-row {
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
        .mp-setting-row:hover,
        .mp-setting-row.is-active {
          background: var(--bg-card-hover);
          border-color: var(--border-hover);
          color: var(--text-primary);
        }
        .mp-setting-icon {
          width: 36px;
          height: 36px;
          border-radius: 10px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          background: var(--bg-card-hover);
          color: var(--text-secondary);
        }
        .mp-setting-copy {
          flex: 1;
          min-width: 0;
        }
        .mp-setting-copy strong {
          display: block;
          font-weight: 600;
          margin-bottom: 1px;
          color: inherit;
        }
        .mp-setting-copy small {
          display: block;
          color: var(--text-muted);
          font-size: 12px;
          font-weight: 400;
          line-height: 1.4;
        }
        .mp-btn {
          display: inline-flex;
          align-items: center;
          gap: 7px;
          border: 1px solid var(--border);
          border-radius: 9px;
          background: var(--bg-card);
          color: var(--text-secondary);
          padding: 9px 16px;
          font-family: 'Inter', system-ui, sans-serif;
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s;
          white-space: nowrap;
        }
        .mp-btn:hover {
          background: var(--bg-card-hover);
          color: var(--text-primary);
          border-color: var(--border-hover);
        }
        .mp-btn:disabled {
          opacity: 0.58;
          cursor: not-allowed;
        }
        .mp-empty,
        .mp-error {
          border: 1px dashed var(--border-hover);
          border-radius: 8px;
          padding: 24px 16px;
          text-align: center;
          color: var(--text-muted);
          background: var(--bg-card);
          font-size: 13px;
        }
        .mp-error {
          border-style: solid;
          color: #f87171;
          background: rgba(248,113,113,0.09);
        }
        .mp-toast {
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
        .mp-toast.bad {
          border-color: rgba(248,113,113,0.32);
          color: #f87171;
        }
        .mp-skeleton {
          background: linear-gradient(90deg, var(--bg-card) 25%, var(--bg-card-hover) 50%, var(--bg-card) 75%);
          background-size: 400% 100%;
          animation: mp-shimmer 1.4s ease-in-out infinite;
        }
        @keyframes mp-shimmer {
          0% { background-position: 100% 50%; }
          100% { background-position: 0 50%; }
        }
        @media (max-width: 760px) {
          .mp-page { padding: 24px 16px 56px; }
          .mp-edit-grid { grid-template-columns: 1fr; }
          .mp-identity { flex-wrap: wrap; }
          .mp-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          .mp-info-grid { grid-template-columns: 1fr; }
          .mp-activity-row { grid-template-columns: 38px minmax(0, 1fr); }
          .mp-activity-time { grid-column: 2; }
        }
      `}</style>

      {toast && (
        <div className={`mp-toast ${toast.ok ? "" : "bad"}`}>
          {toast.ok ? <Check size={15} /> : <X size={15} />}
          {toast.msg}
        </div>
      )}

      <main className="mp-page">
        <div className="mp-shell">
          <header className="mp-header">
            <div className="mp-title">
              <div className="mp-badge">Manager Profile</div>
              <h1>Your profile & overview</h1>
              <p>Track your team overview, recent activity, and profile access.</p>
            </div>
            <div className="mp-header-actions">
              <button className="mp-btn" type="button" onClick={loadProfile}><RefreshCcw size={15} />Refresh</button>
            </div>
          </header>

          {error && <div className="mp-error">{error}</div>}

          {loading ? (
            <Skeleton />
          ) : (
            <>
              {/* ── Profile card ── */}
              <section className="mp-panel mp-profile-panel">

                {/* Identity row: avatar + name + Edit Profile button */}
                <div className="mp-identity">
                  <div className="mp-identity-left">
                    <div className="mp-hero-avatar">
                      {profile.avatar_url ? <img src={profile.avatar_url} alt="" /> : initials(profile.full_name)}
                    </div>
                    <div className="mp-name">
                      <h2>{profile.full_name}</h2>
                      <p>{profile.job_title || "Engineering Manager"}</p>
                      <div className="mp-chip-row">
                        <span className="mp-chip"><UserCog size={13} /><span>@{profile.username}</span></span>
                        <span className="mp-chip"><Mail size={13} /><span>{profile.email}</span></span>
                      </div>
                    </div>
                  </div>

                  {/* Edit Profile button — top-right of identity row, like developer */}
                  {!editing && (
                    <button className="mp-btn" type="button" onClick={handleEditClick} style={{ flexShrink: 0 }}>
                      <Pencil size={15} />Edit Profile
                    </button>
                  )}
                </div>

                {/* Inline edit form — appears below identity, above info grid */}
                {editing && (
                  <div className="mp-edit-form">
                    <div className="mp-edit-grid">
                      <div className="mp-edit-field">
                        <label htmlFor="edit-org">Organization</label>
                        <input
                          id="edit-org"
                          placeholder="Enter organization..."
                          value={editForm.organization}
                          onChange={e => setEditForm(prev => ({ ...prev, organization: e.target.value }))}
                        />
                      </div>
                      <div className="mp-edit-field">
                        <label htmlFor="edit-job">Job Title</label>
                        <input
                          id="edit-job"
                          placeholder="Enter job title..."
                          value={editForm.job_title}
                          onChange={e => setEditForm(prev => ({ ...prev, job_title: e.target.value }))}
                        />
                      </div>
                    </div>
                    <div className="mp-edit-actions">
                      <button className="mp-btn-cancel" type="button" onClick={handleEditCancel} disabled={editSaving}>
                        Cancel
                      </button>
                      <button className="mp-btn-save" type="button" onClick={handleEditSave} disabled={editSaving}>
                        {editSaving ? "Saving…" : "Save Changes"}
                      </button>
                    </div>
                  </div>
                )}

                {/* Info grid */}
                <div className="mp-info-grid">
                  {infoGrid.map(item => {
                    const Icon = item.icon;
                    return (
                      <div className="mp-info-item" key={item.label}>
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

              {/* ── Team Overview ── */}
              <section>
                <SectionTitle>Team Overview</SectionTitle>
                <div className="mp-kpi-grid">
                  <section className="mp-card">
                    <div className="mp-card-top"><span>Team Members</span><Users size={18} /></div>
                    <strong>{fmtNumber(overview.team_members)}</strong>
                    <small>Active developers</small>
                  </section>
                  <section className="mp-card">
                    <div className="mp-card-top"><span>Repositories</span><BriefcaseBusiness size={18} /></div>
                    <strong>{fmtNumber(overview.repositories)}</strong>
                    <small>Analyzed by manager</small>
                  </section>
                  <section className="mp-card">
                    <div className="mp-card-top"><span>Ongoing Analyses</span><Activity size={18} /></div>
                    <strong>{fmtNumber(overview.ongoing_analyses)}</strong>
                    <small>Currently processing</small>
                  </section>
                  <section className="mp-card">
                    <div className="mp-card-top"><span>Team Health</span><Sparkles size={18} /></div>
                    <strong>{Math.round(overview.team_health || 0)}%</strong>
                    <small>Average Sonar health</small>
                  </section>
                </div>
              </section>

              {/* ── Recent Activity ── */}
              <section className="mp-panel">
                <div className="mp-panel-head">
                  <div>
                    <h2>Recent Activity</h2>
                  </div>
                  <button className="mp-link-button" type="button" onClick={toggleActivities}>
                    {showAllActivities ? "Show Less" : "View All Activities"}
                  </button>
                </div>
                <div className="mp-activity-list">
                  {activities.map(item => (
                    <article className="mp-activity-row" key={item.id}>
                      <span className="mp-activity-icon"><Activity size={16} /></span>
                      <div>
                        <strong>{item.title}</strong>
                        <p>{item.description}</p>
                      </div>
                      <span className="mp-activity-time">{item.time_ago}</span>
                    </article>
                  ))}
                  {!activities.length && <div className="mp-empty">No recent activity yet.</div>}
                </div>
              </section>

              {/* ── Profile Settings ── */}
              <div className="mp-settings-section">
                <SectionTitle>Profile Settings</SectionTitle>
                <aside className="mp-settings-grid" aria-label="Profile settings">
                  {settingRows.map(row => {
                    const Icon = row.icon;
                    return (
                      <button
                        key={row.key}
                        type="button"
                        className="mp-setting-row"
                        onClick={() => navigate("/dashboard/manager/account-settings")}
                      >
                        <span className="mp-setting-icon"><Icon size={17} /></span>
                        <span className="mp-setting-copy">
                          <strong>{row.label}</strong>
                          <small>Manage your account details and password</small>
                        </span>
                        <ChevronRight size={16} />
                      </button>
                    );
                  })}
                </aside>
              </div>
            </>
          )}
        </div>
      </main>
    </DashboardLayout>
  );
}
