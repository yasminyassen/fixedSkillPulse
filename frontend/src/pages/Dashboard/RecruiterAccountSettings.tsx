import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Check, KeyRound, LockKeyhole, Save, Trash2, X } from "lucide-react";
import api from "../../api/auth";
import DashboardLayout from "../DashboardLayout";

const accent = "#a855f7";

interface Profile {
  id: number;
  full_name: string;
  username: string;
  email: string;
  role: string | null;
  avatar_url: string | null;
  github_connected: boolean;
  has_password: boolean;
  organization: string | null;
  department: string | null;
  job_title: string | null;
  hiring_focus: string | null;
  member_since: string | null;
}

interface MessageResponse {
  message: string;
  data?: {
    verification_code?: string;
    email_delivery?: string;
  } | null;
}

const initials = (name: string) =>
  name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0])
    .join("")
    .toUpperCase() || "SP";

export default function RecruiterAccountSettings() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    avatar_url: "",
    organization: "",
    department: "",
    job_title: "",
    hiring_focus: "",
  });
  const [passwordForm, setPasswordForm] = useState({
    current_password: "",
    new_password: "",
    verification_code: "",
  });
  const [deleteForm, setDeleteForm] = useState({ confirm_email: "", password: "" });
  const [codeSent, setCodeSent] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

  const hasPassword = Boolean(profile?.has_password);

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok });
    window.setTimeout(() => setToast(null), 2800);
  };

  const loadProfile = async () => {
    setLoading(true);
    try {
      const response = await api.get<Profile>("/recruiter/profile");
      const data = response.data;
      setProfile(data);
      setForm({
        full_name: data.full_name || "",
        email: data.email || "",
        avatar_url: data.avatar_url || "",
        organization: data.organization || "",
        department: data.department || "",
        job_title: data.job_title || "",
        hiring_focus: data.hiring_focus || "",
      });
    } catch {
      showToast("Unable to load account settings", false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProfile();
  }, []);

  const saveProfile = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      const response = await api.patch<Profile>("/recruiter/profile", {
        full_name: form.full_name,
        email: form.email,
        avatar_url: form.avatar_url || null,
        organization: form.organization || null,
        department: form.department || null,
        job_title: form.job_title || null,
        hiring_focus: form.hiring_focus || null,
      });
      setProfile(response.data);
      localStorage.setItem("full_name", response.data.full_name);
      showToast("Account settings saved");
    } catch {
      showToast("Could not save account settings", false);
    } finally {
      setSaving(false);
    }
  };

  const requestSetPasswordCode = async () => {
    setSaving(true);
    try {
      const response = await api.post<MessageResponse>("/recruiter/profile/set-password/request-code");
      const returnedCode = response.data.data?.verification_code;
      if (returnedCode) {
        setPasswordForm(prev => ({ ...prev, verification_code: returnedCode }));
      }
      setCodeSent(true);
      showToast(returnedCode ? "Email failed, local test code filled in" : "Verification code sent to your email");
    } catch {
      showToast("Could not send verification code", false);
    } finally {
      setSaving(false);
    }
  };

  const setPassword = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      await api.post("/recruiter/profile/set-password", {
        new_password: passwordForm.new_password,
        verification_code: passwordForm.verification_code,
      });
      setPasswordForm({ current_password: "", new_password: "", verification_code: "" });
      setCodeSent(false);
      setProfile(prev => prev ? { ...prev, has_password: true } : prev);
      showToast("Password set successfully");
    } catch {
      showToast("Could not set password", false);
    } finally {
      setSaving(false);
    }
  };

  const requestPasswordCode = async () => {
    if (!passwordForm.current_password) {
      showToast("Enter your current password first", false);
      return;
    }
    setSaving(true);
    try {
      const response = await api.post<MessageResponse>("/recruiter/profile/change-password/request-code", {
        current_password: passwordForm.current_password,
      });
      const returnedCode = response.data.data?.verification_code;
      if (returnedCode) {
        setPasswordForm(prev => ({ ...prev, verification_code: returnedCode }));
      }
      setCodeSent(true);
      showToast(returnedCode ? "Email failed, local test code filled in" : "Verification code sent to your email");
    } catch {
      showToast("Could not send verification code", false);
    } finally {
      setSaving(false);
    }
  };

  const changePassword = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      await api.post("/recruiter/profile/change-password", passwordForm);
      setPasswordForm({ current_password: "", new_password: "", verification_code: "" });
      setCodeSent(false);
      showToast("Password changed");
    } catch {
      showToast("Password change failed", false);
    } finally {
      setSaving(false);
    }
  };

  const deleteAccount = async (event: FormEvent) => {
    event.preventDefault();
    if (!window.confirm("Delete this recruiter account permanently?")) return;
    setSaving(true);
    try {
      await api.post("/recruiter/profile/delete-account", deleteForm);
      localStorage.clear();
      window.location.href = "/login?account=deleted";
    } catch {
      showToast("Account deletion failed", false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <DashboardLayout>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        .ras-page {
          min-height: 100vh;
          background: var(--bg-gradient);
          color: var(--text-primary);
          font-family: 'Inter', system-ui, sans-serif;
          padding: 36px 40px 80px;
        }
        .ras-shell {
          max-width: 860px;
          margin: 0 auto;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .ras-header {
          display: flex;
          align-items: center;
          gap: 14px;
          margin-bottom: 8px;
        }
        .ras-header h1 {
          margin: 0;
          font-family: 'Inter', sans-serif;
          font-size: 26px;
          letter-spacing: 0;
        }
        .ras-header p {
          margin: 3px 0 0;
          color: var(--text-muted);
          font-size: 13px;
        }
        .ras-back,
        .ras-btn {
          min-height: 40px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          border: 1px solid var(--border);
          border-radius: 8px;
          background: var(--bg-card);
          color: var(--text-secondary);
          padding: 0 14px;
          font-family: 'Inter', system-ui, sans-serif;
          font-size: 13px;
          font-weight: 800;
          cursor: pointer;
        }
        .ras-back {
          width: 40px;
          padding: 0;
          flex: 0 0 auto;
        }
        .ras-btn.primary {
          color: white;
          border-color: transparent;
          background: ${accent};
        }
        .ras-btn.danger {
          color: #fecaca;
          border-color: rgba(248,113,113,0.36);
          background: rgba(220,38,38,0.24);
        }
        .ras-btn:disabled {
          opacity: 0.55;
          cursor: not-allowed;
        }
        .ras-panel {
          border: 1px solid var(--border);
          border-radius: 8px;
          background: var(--bg-card);
          box-shadow: var(--shadow-card);
          padding: 20px;
        }
        .ras-person {
          display: flex;
          align-items: center;
          gap: 14px;
        }
        .ras-avatar {
          width: 62px;
          height: 62px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: hidden;
          background: linear-gradient(135deg, ${accent}, #ec4899);
          color: white;
          font-weight: 800;
          font-size: 20px;
          flex: 0 0 auto;
        }
        .ras-avatar img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .ras-person strong {
          display: block;
          color: var(--text-primary);
          font-size: 17px;
        }
        .ras-person span {
          color: var(--text-muted);
          font-size: 12px;
        }
        .ras-panel h2 {
          margin: 0 0 16px;
          padding-bottom: 12px;
          border-bottom: 1px solid var(--border);
          font-size: 16px;
          letter-spacing: 0;
        }
        .ras-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
        }
        .ras-field {
          display: flex;
          flex-direction: column;
          gap: 7px;
          color: var(--text-muted);
          font-size: 12px;
          font-weight: 800;
        }
        .ras-field input {
          width: 100%;
          min-height: 42px;
          border: 1px solid var(--border);
          border-radius: 8px;
          background: var(--bg-input);
          color: var(--text-primary);
          outline: 0;
          padding: 0 12px;
          font-family: 'Inter', system-ui, sans-serif;
          font-size: 13px;
          box-sizing: border-box;
        }
        .ras-field input:focus {
          border-color: rgba(168,85,247,0.62);
        }
        .ras-actions {
          display: flex;
          justify-content: flex-end;
          gap: 10px;
          margin-top: 16px;
          padding-top: 16px;
          border-top: 1px solid var(--border);
        }
        .ras-password {
          display: grid;
          gap: 12px;
          align-items: end;
        }
        .ras-password.cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
        .ras-password.cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .ras-password-note,
        .ras-danger p,
        .ras-github-notice,
        .ras-danger-notice {
          color: var(--text-muted);
          font-size: 12px;
          line-height: 1.5;
        }
        .ras-password-note {
          margin: 10px 0 0;
        }
        .ras-github-notice {
          margin: 0 0 14px;
          padding: 10px 14px;
          border-radius: 8px;
          border: 1px solid rgba(168,85,247,0.3);
          background: rgba(168,85,247,0.08);
          color: #d8b4fe;
        }
        .ras-danger {
          border-color: rgba(248,113,113,0.26);
          background: rgba(248,113,113,0.07);
        }
        .ras-danger p {
          margin: 0 0 14px;
        }
        .ras-danger-notice {
          margin: 0 0 14px;
          padding: 10px 14px;
          border-radius: 8px;
          border: 1px solid rgba(248,113,113,0.3);
          background: rgba(248,113,113,0.08);
          color: #fca5a5;
        }
        .ras-toast {
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
        .ras-toast.bad {
          border-color: rgba(248,113,113,0.32);
          color: #f87171;
        }
        .ras-skeleton {
          height: 220px;
          border-radius: 8px;
          background: linear-gradient(90deg, var(--bg-card) 25%, var(--bg-card-hover) 50%, var(--bg-card) 75%);
          background-size: 400% 100%;
          animation: ras-shimmer 1.4s ease-in-out infinite;
        }
        @keyframes ras-shimmer {
          0% { background-position: 100% 50%; }
          100% { background-position: 0 50%; }
        }
        @media (max-width: 760px) {
          .ras-page { padding: 24px 16px 56px; }
          .ras-grid,
          .ras-password.cols-3,
          .ras-password.cols-2 { grid-template-columns: 1fr; }
          .ras-actions,
          .ras-btn { width: 100%; }
          .ras-actions { flex-direction: column; }
        }
      `}</style>

      {toast && (
        <div className={`ras-toast ${toast.ok ? "" : "bad"}`}>
          {toast.ok ? <Check size={15} /> : <X size={15} />}
          {toast.msg}
        </div>
      )}

      <main className="ras-page">
        <div className="ras-shell">
          <header className="ras-header">
            <button className="ras-back" type="button" onClick={() => navigate("/dashboard/recruiter/profile")} title="Back to profile">
              <ArrowLeft size={17} />
            </button>
            <div>
              <h1>Account Settings</h1>
              <p>Manage recruiter account details, password, and account deletion.</p>
            </div>
          </header>

          {loading ? (
            <div className="ras-panel ras-skeleton" />
          ) : profile ? (
            <>
              <section className="ras-panel">
                <div className="ras-person">
                  <div className="ras-avatar">
                    {profile.avatar_url ? <img src={profile.avatar_url} alt="" /> : initials(profile.full_name)}
                  </div>
                  <div>
                    <strong>{profile.full_name}</strong>
                    <span>@{profile.username} - {profile.email}</span>
                  </div>
                </div>
              </section>

              <section className="ras-panel">
                <h2>Profile Details</h2>
                <form onSubmit={saveProfile}>
                  <div className="ras-grid">
                    <label className="ras-field">
                      Full name
                      <input value={form.full_name} onChange={event => setForm({ ...form, full_name: event.target.value })} />
                    </label>
                    <label className="ras-field">
                      Email
                      <input type="email" value={form.email} onChange={event => setForm({ ...form, email: event.target.value })} />
                    </label>
                    <label className="ras-field">
                      Avatar URL
                      <input value={form.avatar_url} onChange={event => setForm({ ...form, avatar_url: event.target.value })} />
                    </label>
                    <label className="ras-field">
                      Job title
                      <input value={form.job_title} onChange={event => setForm({ ...form, job_title: event.target.value })} />
                    </label>
                    <label className="ras-field">
                      Organization
                      <input value={form.organization} onChange={event => setForm({ ...form, organization: event.target.value })} />
                    </label>
                    <label className="ras-field">
                      Department
                      <input value={form.department} onChange={event => setForm({ ...form, department: event.target.value })} />
                    </label>
                    <label className="ras-field">
                      Hiring focus
                      <input value={form.hiring_focus} onChange={event => setForm({ ...form, hiring_focus: event.target.value })} />
                    </label>
                  </div>
                  <div className="ras-actions">
                    <button className="ras-btn primary" disabled={saving} type="submit">
                      <Save size={15} />Save changes
                    </button>
                  </div>
                </form>
              </section>

              <section className="ras-panel">
                <h2>{hasPassword ? "Change Password" : "Set Password"}</h2>
                {!hasPassword && (
                  <p className="ras-github-notice">
                    Your account does not have a password yet. Set one here before using password-protected actions.
                  </p>
                )}

                {!hasPassword ? (
                  <form onSubmit={setPassword}>
                    <div className="ras-password cols-2">
                      <label className="ras-field">
                        New password
                        <input
                          type="password"
                          value={passwordForm.new_password}
                          onChange={event => setPasswordForm({ ...passwordForm, new_password: event.target.value })}
                        />
                      </label>
                      <label className="ras-field">
                        Email code
                        <input
                          inputMode="numeric"
                          maxLength={6}
                          value={passwordForm.verification_code}
                          onChange={event => setPasswordForm({ ...passwordForm, verification_code: event.target.value })}
                        />
                      </label>
                    </div>
                    <p className="ras-password-note">
                      Click Send code to receive a 6-digit code on your email, then enter it here.
                    </p>
                    <div className="ras-actions">
                      <button className="ras-btn" disabled={saving} type="button" onClick={requestSetPasswordCode}>
                        <KeyRound size={15} />{codeSent ? "Send code again" : "Send code"}
                      </button>
                      <button className="ras-btn primary" disabled={saving || !codeSent || passwordForm.verification_code.length !== 6 || passwordForm.new_password.length < 8} type="submit">
                        <LockKeyhole size={15} />Set password
                      </button>
                    </div>
                  </form>
                ) : (
                  <form onSubmit={changePassword}>
                    <div className="ras-password cols-3">
                      <label className="ras-field">
                        Current password
                        <input
                          type="password"
                          value={passwordForm.current_password}
                          onChange={event => setPasswordForm({ ...passwordForm, current_password: event.target.value })}
                        />
                      </label>
                      <label className="ras-field">
                        New password
                        <input
                          type="password"
                          value={passwordForm.new_password}
                          onChange={event => setPasswordForm({ ...passwordForm, new_password: event.target.value })}
                        />
                      </label>
                      <label className="ras-field">
                        Email code
                        <input
                          inputMode="numeric"
                          maxLength={6}
                          value={passwordForm.verification_code}
                          onChange={event => setPasswordForm({ ...passwordForm, verification_code: event.target.value })}
                        />
                      </label>
                    </div>
                    <p className="ras-password-note">
                      First send a code to your email, then enter the 6-digit code here to finish changing your password.
                    </p>
                    <div className="ras-actions">
                      <button className="ras-btn" disabled={saving || !passwordForm.current_password} type="button" onClick={requestPasswordCode}>
                        <KeyRound size={15} />{codeSent ? "Send code again" : "Send code"}
                      </button>
                      <button className="ras-btn primary" disabled={saving || !codeSent || passwordForm.verification_code.length !== 6 || !passwordForm.new_password} type="submit">
                        <LockKeyhole size={15} />Change password
                      </button>
                    </div>
                  </form>
                )}
              </section>

              <section className="ras-panel ras-danger">
                <h2>Delete Account</h2>
                <p>
                  This permanently removes your recruiter account, sessions, connected repository links, candidate
                  evaluations, scores, and profile data.
                </p>
                {!hasPassword && (
                  <p className="ras-danger-notice">
                    You need to set a password first before you can delete your account.
                  </p>
                )}
                <form onSubmit={deleteAccount}>
                  <div className="ras-grid">
                    <label className="ras-field">
                      Confirm email
                      <input
                        type="email"
                        placeholder={profile.email}
                        value={deleteForm.confirm_email}
                        onChange={event => setDeleteForm({ ...deleteForm, confirm_email: event.target.value })}
                        disabled={!hasPassword}
                      />
                    </label>
                    <label className="ras-field">
                      Password
                      <input
                        type="password"
                        value={deleteForm.password}
                        onChange={event => setDeleteForm({ ...deleteForm, password: event.target.value })}
                        disabled={!hasPassword}
                      />
                    </label>
                  </div>
                  <div className="ras-actions">
                    <button className="ras-btn danger" disabled={saving || !hasPassword || deleteForm.confirm_email !== profile.email || !deleteForm.password} type="submit">
                      <Trash2 size={15} />Delete account
                    </button>
                  </div>
                </form>
              </section>
            </>
          ) : null}
        </div>
      </main>
    </DashboardLayout>
  );
}
