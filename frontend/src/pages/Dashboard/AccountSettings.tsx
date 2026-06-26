import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Check, KeyRound, LockKeyhole, Save, Trash2, X } from "lucide-react";
import api from "../../api/auth";
import DashboardLayout from "../DashboardLayout";

const accent = "#6366f1";

interface ProfileData {
  id: number;
  full_name: string;
  username: string;
  email: string;
  role: string | null;
  avatar_url: string | null;
  github_login: string | null;
  github_connected: boolean;
  has_password: boolean;
  organization: string | null;
  department: string | null;
  job_title: string | null;
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

export default function AccountSettings() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    avatar_url: "",
    organization: "",
    department: "",
    job_title: "",
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
      const response = await api.get<ProfileData>("/profile");
      const data = response.data;
      setProfile(data);
      setForm({
        full_name: data.full_name || "",
        email: data.email || "",
        avatar_url: data.avatar_url || "",
        organization: data.organization || "",
        department: data.department || "",
        job_title: data.job_title || "",
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
      const response = await api.patch<ProfileData>("/profile", {
        full_name: form.full_name,
        email: form.email,
        avatar_url: form.avatar_url || null,
        organization: form.organization || null,
        department: form.department || null,
        job_title: form.job_title || null,
      });
      setProfile(prev => prev ? { ...prev, ...response.data, has_password: prev.has_password } : response.data);
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
      const response = await api.post<MessageResponse>("/profile/set-password/request-code");
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
      await api.post("/profile/set-password", {
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
      const response = await api.post<MessageResponse>("/profile/change-password/request-code", {
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
      await api.post("/profile/change-password", passwordForm);
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
    if (!window.confirm("Delete this developer account permanently?")) return;
    setSaving(true);
    try {
      await api.post("/profile/delete-account", deleteForm);
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

        .das-page {
          min-height: 100vh;
          background: var(--bg-gradient);
          color: var(--text-primary);
          font-family: 'Inter', system-ui, sans-serif;
          padding: 36px 40px 80px;
        }
        .das-shell {
          max-width: 860px;
          margin: 0 auto;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .das-header {
          display: flex;
          align-items: center;
          gap: 14px;
          margin-bottom: 8px;
        }
        .das-header h1 {
          margin: 0;
          font-family: 'Inter', sans-serif;
          font-size: 26px;
          letter-spacing: 0;
        }
        .das-header p {
          margin: 3px 0 0;
          color: var(--text-muted);
          font-size: 13px;
        }
        .das-back,
        .das-btn {
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
        .das-back {
          width: 40px;
          padding: 0;
          flex: 0 0 auto;
        }
        .das-btn.primary {
          color: white;
          border-color: transparent;
          background: ${accent};
        }
        .das-btn.danger {
          color: #fecaca;
          border-color: rgba(248,113,113,0.36);
          background: rgba(220,38,38,0.24);
        }
        .das-btn:disabled {
          opacity: 0.55;
          cursor: not-allowed;
        }
        .das-panel {
          border: 1px solid var(--border);
          border-radius: 8px;
          background: var(--bg-card);
          box-shadow: var(--shadow-card);
          padding: 20px;
        }
        .das-person {
          display: flex;
          align-items: center;
          gap: 14px;
        }
        .das-avatar {
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
        .das-avatar img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .das-person strong {
          display: block;
          color: var(--text-primary);
          font-size: 17px;
        }
        .das-person span {
          color: var(--text-muted);
          font-size: 12px;
        }
        .das-panel h2 {
          margin: 0 0 16px;
          padding-bottom: 12px;
          border-bottom: 1px solid var(--border);
          font-size: 16px;
          letter-spacing: 0;
        }
        .das-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
        }
        .das-field {
          display: flex;
          flex-direction: column;
          gap: 7px;
          color: var(--text-muted);
          font-size: 12px;
          font-weight: 800;
        }
        .das-field input {
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
        .das-field input:focus {
          border-color: rgba(99,102,241,0.62);
        }
        .das-actions {
          display: flex;
          justify-content: flex-end;
          gap: 10px;
          margin-top: 16px;
          padding-top: 16px;
          border-top: 1px solid var(--border);
        }
        .das-password {
          display: grid;
          gap: 12px;
          align-items: end;
        }
        .das-password.cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
        .das-password.cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .das-password-note,
        .das-danger p,
        .das-github-notice,
        .das-danger-notice {
          color: var(--text-muted);
          font-size: 12px;
          line-height: 1.5;
        }
        .das-password-note {
          margin: 10px 0 0;
        }
        .das-github-notice {
          margin: 0 0 14px;
          padding: 10px 14px;
          border-radius: 8px;
          border: 1px solid rgba(99,102,241,0.3);
          background: rgba(99,102,241,0.08);
          color: #c7d2fe;
        }
        .das-danger {
          border-color: rgba(248,113,113,0.26);
          background: rgba(248,113,113,0.07);
        }
        .das-danger p {
          margin: 0 0 14px;
        }
        .das-danger-notice {
          margin: 0 0 14px;
          padding: 10px 14px;
          border-radius: 8px;
          border: 1px solid rgba(248,113,113,0.3);
          background: rgba(248,113,113,0.08);
          color: #fca5a5;
        }
        .das-toast {
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
        .das-toast.bad {
          border-color: rgba(248,113,113,0.32);
          color: #f87171;
        }
        .das-skeleton {
          height: 220px;
          border-radius: 8px;
          background: linear-gradient(90deg, var(--bg-card) 25%, var(--bg-card-hover) 50%, var(--bg-card) 75%);
          background-size: 400% 100%;
          animation: das-shimmer 1.4s ease-in-out infinite;
        }
        @keyframes das-shimmer {
          0% { background-position: 100% 50%; }
          100% { background-position: 0 50%; }
        }
        @media (max-width: 760px) {
          .das-page { padding: 24px 16px 56px; }
          .das-grid,
          .das-password.cols-3,
          .das-password.cols-2 { grid-template-columns: 1fr; }
          .das-actions,
          .das-btn { width: 100%; }
          .das-actions { flex-direction: column; }
        }
      `}</style>

      {toast && (
        <div className={`das-toast ${toast.ok ? "" : "bad"}`}>
          {toast.ok ? <Check size={15} /> : <X size={15} />}
          {toast.msg}
        </div>
      )}

      <main className="das-page">
        <div className="das-shell">
          <header className="das-header">
            <button className="das-back" type="button" onClick={() => navigate("/dashboard/developer/profile")} title="Back to profile">
              <ArrowLeft size={17} />
            </button>
            <div>
              <h1>Account Settings</h1>
              <p>Manage developer account details, password, and account deletion.</p>
            </div>
          </header>

          {loading ? (
            <div className="das-panel das-skeleton" />
          ) : profile ? (
            <>
              <section className="das-panel">
                <div className="das-person">
                  <div className="das-avatar">
                    {profile.avatar_url ? <img src={profile.avatar_url} alt="" /> : initials(profile.full_name)}
                  </div>
                  <div>
                    <strong>{profile.full_name}</strong>
                    <span>@{profile.username} · {profile.email}</span>
                  </div>
                </div>
              </section>

              <section className="das-panel">
                <h2>Profile Details</h2>
                <form onSubmit={saveProfile}>
                  <div className="das-grid">
                    <label className="das-field">
                      Full name
                      <input value={form.full_name} onChange={event => setForm({ ...form, full_name: event.target.value })} />
                    </label>
                    <label className="das-field">
                      Email
                      <input type="email" value={form.email} onChange={event => setForm({ ...form, email: event.target.value })} />
                    </label>
                    <label className="das-field">
                      Avatar URL
                      <input value={form.avatar_url} onChange={event => setForm({ ...form, avatar_url: event.target.value })} />
                    </label>
                    <label className="das-field">
                      Job title
                      <input value={form.job_title} onChange={event => setForm({ ...form, job_title: event.target.value })} />
                    </label>
                    <label className="das-field">
                      Organization
                      <input value={form.organization} onChange={event => setForm({ ...form, organization: event.target.value })} />
                    </label>
                    <label className="das-field">
                      Department
                      <input value={form.department} onChange={event => setForm({ ...form, department: event.target.value })} />
                    </label>
                  </div>
                  <div className="das-actions">
                    <button className="das-btn primary" disabled={saving} type="submit">
                      <Save size={15} />Save changes
                    </button>
                  </div>
                </form>
              </section>

              <section className="das-panel">
                <h2>{hasPassword ? "Change Password" : "Set Password"}</h2>
                {!hasPassword && (
                  <p className="das-github-notice">
                    Your account does not have a password yet. Set one here before using password-protected actions.
                  </p>
                )}

                {!hasPassword ? (
                  <form onSubmit={setPassword}>
                    <div className="das-password cols-2">
                      <label className="das-field">
                        New password
                        <input
                          type="password"
                          value={passwordForm.new_password}
                          onChange={event => setPasswordForm({ ...passwordForm, new_password: event.target.value })}
                        />
                      </label>
                      <label className="das-field">
                        Email code
                        <input
                          inputMode="numeric"
                          maxLength={6}
                          value={passwordForm.verification_code}
                          onChange={event => setPasswordForm({ ...passwordForm, verification_code: event.target.value })}
                        />
                      </label>
                    </div>
                    <p className="das-password-note">
                      Click Send code to receive a 6-digit code on your email, then enter it here.
                    </p>
                    <div className="das-actions">
                      <button className="das-btn" disabled={saving} type="button" onClick={requestSetPasswordCode}>
                        <KeyRound size={15} />{codeSent ? "Send code again" : "Send code"}
                      </button>
                      <button className="das-btn primary" disabled={saving || !codeSent || passwordForm.verification_code.length !== 6 || passwordForm.new_password.length < 8} type="submit">
                        <LockKeyhole size={15} />Set password
                      </button>
                    </div>
                  </form>
                ) : (
                  <form onSubmit={changePassword}>
                    <div className="das-password cols-3">
                      <label className="das-field">
                        Current password
                        <input
                          type="password"
                          value={passwordForm.current_password}
                          onChange={event => setPasswordForm({ ...passwordForm, current_password: event.target.value })}
                        />
                      </label>
                      <label className="das-field">
                        New password
                        <input
                          type="password"
                          value={passwordForm.new_password}
                          onChange={event => setPasswordForm({ ...passwordForm, new_password: event.target.value })}
                        />
                      </label>
                      <label className="das-field">
                        Email code
                        <input
                          inputMode="numeric"
                          maxLength={6}
                          value={passwordForm.verification_code}
                          onChange={event => setPasswordForm({ ...passwordForm, verification_code: event.target.value })}
                        />
                      </label>
                    </div>
                    <p className="das-password-note">
                      First send a code to your email, then enter the 6-digit code here to finish changing your password.
                    </p>
                    <div className="das-actions">
                      <button className="das-btn" disabled={saving || !passwordForm.current_password} type="button" onClick={requestPasswordCode}>
                        <KeyRound size={15} />{codeSent ? "Send code again" : "Send code"}
                      </button>
                      <button className="das-btn primary" disabled={saving || !codeSent || passwordForm.verification_code.length !== 6 || !passwordForm.new_password} type="submit">
                        <LockKeyhole size={15} />Change password
                      </button>
                    </div>
                  </form>
                )}
              </section>

              <section className="das-panel das-danger">
                <h2>Delete Account</h2>
                <p>
                  This permanently removes your developer account, sessions, connected repository links, analyses,
                  uploaded requirements, scores, and profile data.
                </p>
                {!hasPassword && (
                  <p className="das-danger-notice">
                    You need to set a password first before you can delete your account.
                  </p>
                )}
                <form onSubmit={deleteAccount}>
                  <div className="das-grid">
                    <label className="das-field">
                      Confirm email
                      <input
                        type="email"
                        placeholder={profile.email}
                        value={deleteForm.confirm_email}
                        onChange={event => setDeleteForm({ ...deleteForm, confirm_email: event.target.value })}
                        disabled={!hasPassword}
                      />
                    </label>
                    <label className="das-field">
                      Password
                      <input
                        type="password"
                        value={deleteForm.password}
                        onChange={event => setDeleteForm({ ...deleteForm, password: event.target.value })}
                        disabled={!hasPassword}
                      />
                    </label>
                  </div>
                  <div className="das-actions">
                    <button className="das-btn danger" disabled={saving || !hasPassword || deleteForm.confirm_email !== profile.email || !deleteForm.password} type="submit">
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
