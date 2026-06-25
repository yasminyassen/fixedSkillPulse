import type { FormEvent } from "react";
import React, { useMemo, useState } from "react";
import { resetPassword } from "../api/auth";

const ResetPassword: React.FC = () => {
  const token = useMemo(() => new URLSearchParams(window.location.search).get("token") ?? "", []);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [focused, setFocused] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(token ? null : "Reset token is missing. Please request a new link.");
  const [success, setSuccess] = useState(false);

  const validatePassword = (password: string) =>
    /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[ !@#$%^&*()_+\-=[\]{};':"\\|,.<>/?]).{8,}$/.test(password);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    if (!token) {
      setError("Reset token is missing. Please request a new link.");
      return;
    }

    if (!validatePassword(newPassword)) {
      setError("Password must be 8+ characters and include uppercase, lowercase, a number, and a special character.");
      return;
    }

    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      await resetPassword({ token, new_password: newPassword });
      setSuccess(true);
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { detail?: string } } };
      setError(axiosError.response?.data?.detail ?? "Unable to reset password. Please request a new link.");
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <>
        <style>{`
          @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500;600;700&display=swap');
          *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
          body { background: #0f0c1a; }
          .rp-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #0f0c1a; font-family: 'DM Sans', sans-serif; padding: 24px; position: relative; overflow: hidden; }
          .rp-card { background: rgba(255,255,255,0.04); border: 1px solid rgba(167,139,250,0.15); border-radius: 24px; padding: 56px 48px; text-align: center; max-width: 420px; width: 100%; position: relative; z-index: 2; backdrop-filter: blur(20px); }
          .rp-title { font-family: 'Syne', sans-serif; font-size: 24px; font-weight: 800; color: white; margin-bottom: 8px; }
          .rp-sub { font-size: 14px; color: rgba(196,181,253,0.5); margin-bottom: 28px; line-height: 1.7; }
          .rp-btn { display: inline-flex; align-items: center; justify-content: center; padding: 13px 28px; background: linear-gradient(135deg, #7c3aed, #a855f7); color: white; border: none; border-radius: 13px; font-family: 'DM Sans', sans-serif; font-size: 15px; font-weight: 600; cursor: pointer; transition: all 0.2s; box-shadow: 0 6px 20px rgba(124,58,237,0.3); }
          .rp-btn:hover { transform: translateY(-2px); box-shadow: 0 10px 28px rgba(124,58,237,0.4); }
        `}</style>
        <div className="rp-page">
          <div className="rp-card">
            <div className="rp-title">Password updated</div>
            <div className="rp-sub">Your SkillPulse password has been reset. You can now sign in with your new password.</div>
            <button className="rp-btn" type="button" onClick={() => { window.location.href = "/login"; }}>
              Sign in now
            </button>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500;600;700&display=swap');
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #0f0c1a; }
        .rp-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #0f0c1a; font-family: 'DM Sans', sans-serif; padding: 24px; position: relative; overflow: hidden; }
        .rp-orb { position: fixed; border-radius: 50%; background: radial-gradient(circle, rgba(244,114,182,0.16) 0%, transparent 65%); width: 680px; height: 680px; bottom: -220px; right: -120px; pointer-events: none; }
        .rp-grid { position: fixed; inset: 0; background-image: linear-gradient(rgba(167,139,250,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(167,139,250,0.04) 1px, transparent 1px); background-size: 48px 48px; pointer-events: none; }
        .rp-card { background: rgba(255,255,255,0.04); border: 1px solid rgba(167,139,250,0.15); border-radius: 24px; padding: 48px 40px; max-width: 440px; width: 100%; position: relative; z-index: 2; backdrop-filter: blur(20px); }
        .rp-title { font-family: 'Syne', sans-serif; font-size: 26px; font-weight: 800; color: white; margin-bottom: 8px; letter-spacing: -0.5px; text-align: center; }
        .rp-sub { font-size: 14px; color: rgba(196,181,253,0.5); margin-bottom: 28px; line-height: 1.7; text-align: center; }
        .rp-form { display: flex; flex-direction: column; gap: 16px; }
        .rp-label { font-size: 12px; font-weight: 600; color: rgba(196,181,253,0.6); text-transform: uppercase; letter-spacing: 0.08em; }
        .rp-input-wrap { display: flex; align-items: center; gap: 10px; background: rgba(255,255,255,0.04); border: 1px solid rgba(167,139,250,0.15); border-radius: 12px; padding: 0 14px; transition: border-color 0.2s, box-shadow 0.2s; height: 48px; }
        .rp-input-wrap.focused { border-color: rgba(167,139,250,0.5); box-shadow: 0 0 0 3px rgba(167,139,250,0.09); }
        .rp-icon { color: rgba(167,139,250,0.45); display: flex; align-items: center; }
        .rp-input { flex: 1; background: transparent; border: none; outline: none; color: white; font-family: 'DM Sans', sans-serif; font-size: 14px; }
        .rp-input::placeholder { color: rgba(196,181,253,0.25); }
        .rp-error { font-size: 13px; line-height: 1.5; color: #f472b6; background: rgba(244,114,182,0.08); border: 1px solid rgba(244,114,182,0.2); border-radius: 10px; padding: 10px 14px; }
        .rp-submit { padding: 14px; background: linear-gradient(135deg, #c4b5fd, #f472b6, #67e8f9); background-size: 300%; color: #1e1433; border: none; border-radius: 13px; font-family: 'Syne', sans-serif; font-size: 15px; font-weight: 800; cursor: pointer; transition: transform 0.2s; }
        .rp-submit:hover:not(:disabled) { transform: translateY(-2px); }
        .rp-submit:disabled { opacity: 0.6; cursor: not-allowed; }
        .rp-footer { margin-top: 20px; text-align: center; font-size: 13px; color: rgba(196,181,253,0.4); }
        .rp-footer a { color: #c4b5fd; text-decoration: none; font-weight: 600; }
        .rp-footer a:hover { color: #f472b6; }
      `}</style>
      <div className="rp-page">
        <div className="rp-orb" />
        <div className="rp-grid" />
        <div className="rp-card">
          <div className="rp-title">Create a new password</div>
          <div className="rp-sub">Choose a strong password to secure your SkillPulse account.</div>

          <form className="rp-form" onSubmit={handleSubmit}>
            <div>
              <label className="rp-label" htmlFor="new-password">New password</label>
              <div className={`rp-input-wrap ${focused === "new" ? "focused" : ""}`}>
                <span className="rp-icon">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                </span>
                <input id="new-password" className="rp-input" type="password" placeholder="Enter new password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} onFocus={() => setFocused("new")} onBlur={() => setFocused(null)} required />
              </div>
            </div>

            <div>
              <label className="rp-label" htmlFor="confirm-password">Confirm password</label>
              <div className={`rp-input-wrap ${focused === "confirm" ? "focused" : ""}`}>
                <span className="rp-icon">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                </span>
                <input id="confirm-password" className="rp-input" type="password" placeholder="Repeat new password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} onFocus={() => setFocused("confirm")} onBlur={() => setFocused(null)} required />
              </div>
            </div>

            {error && <div className="rp-error">{error}</div>}

            <button className="rp-submit" type="submit" disabled={loading || !token}>
              {loading ? "Updating..." : "Reset password"}
            </button>
          </form>

          <div className="rp-footer">
            Need a new link? <a href="/forgot-password">Request reset</a>
          </div>
        </div>
      </div>
    </>
  );
};

export default ResetPassword;
