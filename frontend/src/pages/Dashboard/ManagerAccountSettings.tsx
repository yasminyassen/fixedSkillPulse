import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Check, KeyRound, LockKeyhole, Save, Trash2, X } from "lucide-react";
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
  github_connected: boolean;
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

export default function ManagerAccountSettings() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<Profile | null>(null);
  // true = عنده password, false = GitHub only, null = لسه بيتحمل
  const [hasPassword, setHasPassword] = useState<boolean | null>(null);
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

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok });
    window.setTimeout(() => setToast(null), 2800);
  };

  const loadProfile = async () => {
    setLoading(true);
    try {
      const response = await api.get<Profile>("/manager/profile");
      const data = response.data;
      setProfile(data);
      // لو github_connected بس ومفيش password
      setHasPassword(!data.github_connected);
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
      const response = await api.patch<Profile>("/manager/profile", {
        full_name: form.full_name,
        email: form.email,
        avatar_url: form.avatar_url || null,
        organization: form.organization || null,
        department: form.department || null,
        job_title: form.job_title || null,
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

  // ── للـ GitHub users: طلب كود عشان يحددوا password لأول مرة ──
  const requestSetPasswordCode = async () => {
    setSaving(true);
    try {
      const response = await api.post<MessageResponse>("/manager/profile/set-password/request-code");
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

  // ── للـ GitHub users: تحديد password لأول مرة ──
  const setPassword = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      await api.post("/manager/profile/set-password", {
        new_password: passwordForm.new_password,
        verification_code: passwordForm.verification_code,
      });
      setPasswordForm({ current_password: "", new_password: "", verification_code: "" });
      setCodeSent(false);
      setHasPassword(true); // دلوقتي عنده password ويقدر يمسح الأكونت
      showToast("Password set successfully — you can now delete your account");
    } catch {
      showToast("Could not set password", false);
    } finally {
      setSaving(false);
    }
  };

  // ── للـ password users: طلب كود عشان يغيروا password ──
  const requestPasswordCode = async () => {
    if (!passwordForm.current_password) {
      showToast("Enter your current password first", false);
      return;
    }
    setSaving(true);
    try {
      const response = await api.post<MessageResponse>("/manager/profile/change-password/request-code", {
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

  // ── للـ password users: تغيير password ──
  const changePassword = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      await api.post("/manager/profile/change-password", passwordForm);
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
    if (!window.confirm("Delete this manager account permanently?")) return;
    setSaving(true);
    try {
      await api.post("/manager/profile/delete-account", deleteForm);
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

        .mas-page {
          min-height: 100vh;
          background: var(--bg-gradient);
          color: var(--text-primary);
          font-family: 'Inter', system-ui, sans-serif;
          padding: 36px 40px 80px;
        }
        .mas-shell {
          max-width: 860px;
          margin: 0 auto;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .mas-header {
          display: flex;
          align-items: center;
          gap: 14px;
          margin-bottom: 8px;
        }
        .mas-header h1 {
          margin: 0;
          font-family: 'Inter', sans-serif;
          font-size: 26px;
          letter-spacing: 0;
        }
        .mas-header p {
          margin: 3px 0 0;
          color: var(--text-muted);
          font-size: 13px;
        }
        .mas-back,
        .mas-btn {
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
        .mas-back {
          width: 40px;
          padding: 0;
          flex: 0 0 auto;
        }
        .mas-btn.primary {
          color: white;
          border-color: transparent;
          background: ${accent};
        }
        .mas-btn.danger {
          color: #fecaca;
          border-color: rgba(248,113,113,0.36);
          background: rgba(220,38,38,0.24);
        }
        .mas-btn:disabled {
          opacity: 0.55;
          cursor: not-allowed;
        }
        .mas-panel {
          border: 1px solid var(--border);
          border-radius: 8px;
          background: var(--bg-card);
          box-shadow: var(--shadow-card);
          padding: 20px;
        }
        .mas-person {
          display: flex;
          align-items: center;
          gap: 14px;
        }
        .mas-avatar {
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
        .mas-avatar img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .mas-person strong {
          display: block;
          color: var(--text-primary);
          font-size: 17px;
        }
        .mas-person span {
          color: var(--text-muted);
          font-size: 12px;
        }
        .mas-panel h2 {
          margin: 0 0 16px;
          padding-bottom: 12px;
          border-bottom: 1px solid var(--border);
          font-size: 16px;
          letter-spacing: 0;
        }
        .mas-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
        }
        .mas-field {
          display: flex;
          flex-direction: column;
          gap: 7px;
          color: var(--text-muted);
          font-size: 12px;
          font-weight: 800;
        }
        .mas-field input {
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
        .mas-field input:focus {
          border-color: rgba(139,92,246,0.62);
        }
        .mas-actions {
          display: flex;
          justify-content: flex-end;
          gap: 10px;
          margin-top: 16px;
          padding-top: 16px;
          border-top: 1px solid var(--border);
        }
        .mas-password {
          display: grid;
          gap: 12px;
          align-items: end;
        }
        .mas-password.cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
        .mas-password.cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .mas-password-note {
          margin: 10px 0 0;
          color: var(--text-muted);
          font-size: 12px;
          line-height: 1.45;
        }
        .mas-github-notice {
          margin: 0 0 14px;
          padding: 10px 14px;
          border-radius: 8px;
          border: 1px solid rgba(139,92,246,0.3);
          background: rgba(139,92,246,0.08);
          color: #c4b5fd;
          font-size: 12px;
          line-height: 1.6;
        }
        .mas-danger {
          border-color: rgba(248,113,113,0.26);
          background: rgba(248,113,113,0.07);
        }
        .mas-danger p {
          margin: 0 0 14px;
          color: var(--text-muted);
          font-size: 12px;
          line-height: 1.5;
        }
        .mas-danger-notice {
          margin: 0 0 14px;
          padding: 10px 14px;
          border-radius: 8px;
          border: 1px solid rgba(248,113,113,0.3);
          background: rgba(248,113,113,0.08);
          color: #fca5a5;
          font-size: 12px;
          line-height: 1.6;
        }
        .mas-toast {
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
        .mas-toast.bad {
          border-color: rgba(248,113,113,0.32);
          color: #f87171;
        }
        .mas-skeleton {
          height: 220px;
          border-radius: 8px;
          background: linear-gradient(90deg, var(--bg-card) 25%, var(--bg-card-hover) 50%, var(--bg-card) 75%);
          background-size: 400% 100%;
          animation: mas-shimmer 1.4s ease-in-out infinite;
        }
        @keyframes mas-shimmer {
          0% { background-position: 100% 50%; }
          100% { background-position: 0 50%; }
        }
        @media (max-width: 760px) {
          .mas-page { padding: 24px 16px 56px; }
          .mas-grid,
          .mas-password.cols-3,
          .mas-password.cols-2 { grid-template-columns: 1fr; }
          .mas-actions,
          .mas-btn { width: 100%; }
          .mas-actions { flex-direction: column; }
        }
      `}</style>

      {toast && (
        <div className={`mas-toast ${toast.ok ? "" : "bad"}`}>
          {toast.ok ? <Check size={15} /> : <X size={15} />}
          {toast.msg}
        </div>
      )}

      <main className="mas-page">
        <div className="mas-shell">
          <header className="mas-header">
            <button className="mas-back" type="button" onClick={() => navigate("/dashboard/manager/profile")} title="Back to profile">
              <ArrowLeft size={17} />
            </button>
            <div>
              <h1>Account Settings</h1>
              <p>Manage manager account details, password, and account deletion.</p>
            </div>
          </header>

          {loading ? (
            <div className="mas-panel mas-skeleton" />
          ) : profile ? (
            <>
              {/* ── Profile card ── */}
              <section className="mas-panel">
                <div className="mas-person">
                  <div className="mas-avatar">
                    {profile.avatar_url ? <img src={profile.avatar_url} alt="" /> : initials(profile.full_name)}
                  </div>
                  <div>
                    <strong>{profile.full_name}</strong>
                    <span>@{profile.username} · {profile.email}</span>
                  </div>
                </div>
              </section>

              {/* ── Profile Details ── */}
              <section className="mas-panel">
                <h2>Profile Details</h2>
                <form onSubmit={saveProfile}>
                  <div className="mas-grid">
                    <label className="mas-field">
                      Full name
                      <input value={form.full_name} onChange={e => setForm({ ...form, full_name: e.target.value })} />
                    </label>
                    <label className="mas-field">
                      Email
                      <input type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} />
                    </label>
                    <label className="mas-field">
                      Avatar URL
                      <input value={form.avatar_url} onChange={e => setForm({ ...form, avatar_url: e.target.value })} />
                    </label>
                    <label className="mas-field">
                      Job title
                      <input value={form.job_title ?? ""} onChange={e => setForm({ ...form, job_title: e.target.value })} />
                    </label>
                    <label className="mas-field">
                      Organization
                      <input value={form.organization ?? ""} onChange={e => setForm({ ...form, organization: e.target.value })} />
                    </label>
                    <label className="mas-field">
                      Department
                      <input value={form.department ?? ""} onChange={e => setForm({ ...form, department: e.target.value })} />
                    </label>
                  </div>
                  <div className="mas-actions">
                    <button className="mas-btn primary" disabled={saving} type="submit">
                      <Save size={15} />Save changes
                    </button>
                  </div>
                </form>
              </section>

              {/* ── Password section — يتغير حسب GitHub أو email ── */}
              <section className="mas-panel">
                <h2>{hasPassword ? "Change Password" : "Set Password"}</h2>

                {!hasPassword && (
                  <p className="mas-github-notice">
                    Your account is connected via GitHub and doesn't have a password yet.
                    Set one here — you'll need it to delete your account.
                  </p>
                )}

                {/* GitHub user: Set password for the first time */}
                {!hasPassword ? (
                  <form onSubmit={setPassword}>
                    <div className={`mas-password cols-2`}>
                      <label className="mas-field">
                        New password
                        <input
                          type="password"
                          value={passwordForm.new_password}
                          onChange={e => setPasswordForm({ ...passwordForm, new_password: e.target.value })}
                        />
                      </label>
                      <label className="mas-field">
                        Email code
                        <input
                          inputMode="numeric"
                          maxLength={6}
                          value={passwordForm.verification_code}
                          onChange={e => setPasswordForm({ ...passwordForm, verification_code: e.target.value })}
                        />
                      </label>
                    </div>
                    <p className="mas-password-note">
                      Click "Send code" to receive a 6-digit code on your email, then enter it here.
                    </p>
                    <div className="mas-actions">
                      <button
                        className="mas-btn"
                        disabled={saving}
                        type="button"
                        onClick={requestSetPasswordCode}
                      >
                        <KeyRound size={15} />{codeSent ? "Send code again" : "Send code"}
                      </button>
                      <button
                        className="mas-btn primary"
                        disabled={saving || !codeSent || passwordForm.verification_code.length !== 6 || passwordForm.new_password.length < 8}
                        type="submit"
                      >
                        <LockKeyhole size={15} />Set password
                      </button>
                    </div>
                  </form>
                ) : (
                  /* Email/password user: Change existing password */
                  <form onSubmit={changePassword}>
                    <div className="mas-password cols-3">
                      <label className="mas-field">
                        Current password
                        <input
                          type="password"
                          value={passwordForm.current_password}
                          onChange={e => setPasswordForm({ ...passwordForm, current_password: e.target.value })}
                        />
                      </label>
                      <label className="mas-field">
                        New password
                        <input
                          type="password"
                          value={passwordForm.new_password}
                          onChange={e => setPasswordForm({ ...passwordForm, new_password: e.target.value })}
                        />
                      </label>
                      <label className="mas-field">
                        Email code
                        <input
                          inputMode="numeric"
                          maxLength={6}
                          value={passwordForm.verification_code}
                          onChange={e => setPasswordForm({ ...passwordForm, verification_code: e.target.value })}
                        />
                      </label>
                    </div>
                    <p className="mas-password-note">
                      First send a code to your email, then enter the 6-digit code here to finish changing your password.
                    </p>
                    <div className="mas-actions">
                      <button
                        className="mas-btn"
                        disabled={saving || !passwordForm.current_password}
                        type="button"
                        onClick={requestPasswordCode}
                      >
                        <KeyRound size={15} />{codeSent ? "Send code again" : "Send code"}
                      </button>
                      <button
                        className="mas-btn primary"
                        disabled={saving || !codeSent || passwordForm.verification_code.length !== 6 || !passwordForm.new_password}
                        type="submit"
                      >
                        <LockKeyhole size={15} />Change password
                      </button>
                    </div>
                  </form>
                )}
              </section>

              {/* ── Delete Account ── */}
              <section className="mas-panel mas-danger">
                <h2>Delete Account</h2>
                <p>
                  This permanently removes your manager account, sessions, profile settings, team links,
                  activity logs, uploaded requirements, and manager-owned analysis data.
                </p>

                {!hasPassword && (
                  <p className="mas-danger-notice">
                    You need to set a password first (section above) before you can delete your account.
                  </p>
                )}

                <form onSubmit={deleteAccount}>
                  <div className="mas-grid">
                    <label className="mas-field">
                      Confirm email
                      <input
                        type="email"
                        placeholder={profile.email}
                        value={deleteForm.confirm_email}
                        onChange={e => setDeleteForm({ ...deleteForm, confirm_email: e.target.value })}
                        disabled={!hasPassword}
                      />
                    </label>
                    <label className="mas-field">
                      Password
                      <input
                        type="password"
                        value={deleteForm.password}
                        onChange={e => setDeleteForm({ ...deleteForm, password: e.target.value })}
                        disabled={!hasPassword}
                      />
                    </label>
                  </div>
                  <div className="mas-actions">
                    <button
                      className="mas-btn danger"
                      disabled={saving || !hasPassword || deleteForm.confirm_email !== profile.email || !deleteForm.password}
                      type="submit"
                    >
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
