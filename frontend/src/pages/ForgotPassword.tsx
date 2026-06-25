import type { FormEvent } from "react";
import React, { useState } from "react";
import { forgotPassword } from "../api/auth";

const ForgotPassword: React.FC = () => {
  const [email, setEmail] = useState("");
  const [focused, setFocused] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setMessage(null);
    setError(null);

    try {
      const response = await forgotPassword({ email });
      setMessage(response.message);
    } catch (err: unknown) {
      const axiosError = err as { response?: { status?: number; data?: { detail?: string } } };
      if (axiosError.response?.status === 404) {
        setError(axiosError.response.data?.detail ?? "No account found with this email address.");
      } else {
        setError("We couldn't process that request. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500;600;700&display=swap');
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #0f0c1a; }
        .fp-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #0f0c1a; font-family: 'DM Sans', sans-serif; padding: 24px; position: relative; overflow: hidden; }
        .fp-orb { position: fixed; border-radius: 50%; background: radial-gradient(circle, rgba(124,58,237,0.22) 0%, transparent 65%); width: 700px; height: 700px; top: -200px; left: -150px; pointer-events: none; }
        .fp-grid { position: fixed; inset: 0; background-image: linear-gradient(rgba(167,139,250,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(167,139,250,0.04) 1px, transparent 1px); background-size: 48px 48px; pointer-events: none; }
        .fp-card { background: rgba(255,255,255,0.04); border: 1px solid rgba(167,139,250,0.15); border-radius: 24px; padding: 48px 40px; max-width: 440px; width: 100%; position: relative; z-index: 2; backdrop-filter: blur(20px); }
        .fp-logo { display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 30px; }
        .fp-logo-bars { display: flex; gap: 3px; align-items: flex-end; }
        .fp-logo-bars span { display: block; width: 4px; border-radius: 2px; }
        .fp-logo-name { font-family: 'Syne', sans-serif; font-size: 19px; font-weight: 800; color: white; letter-spacing: -0.3px; }
        .fp-logo-name em { font-style: normal; color: #c4b5fd; }
        .fp-title { font-family: 'Syne', sans-serif; font-size: 26px; font-weight: 800; color: white; margin-bottom: 8px; letter-spacing: -0.5px; text-align: center; }
        .fp-sub { font-size: 14px; color: rgba(196,181,253,0.5); margin-bottom: 28px; line-height: 1.7; text-align: center; }
        .fp-form { display: flex; flex-direction: column; gap: 16px; }
        .fp-label { font-size: 12px; font-weight: 600; color: rgba(196,181,253,0.6); text-transform: uppercase; letter-spacing: 0.08em; }
        .fp-input-wrap { display: flex; align-items: center; gap: 10px; background: rgba(255,255,255,0.04); border: 1px solid rgba(167,139,250,0.15); border-radius: 12px; padding: 0 14px; transition: border-color 0.2s, box-shadow 0.2s; height: 48px; }
        .fp-input-wrap.focused { border-color: rgba(167,139,250,0.5); box-shadow: 0 0 0 3px rgba(167,139,250,0.09); }
        .fp-icon { color: rgba(167,139,250,0.45); display: flex; align-items: center; }
        .fp-input { flex: 1; background: transparent; border: none; outline: none; color: white; font-family: 'DM Sans', sans-serif; font-size: 14px; }
        .fp-input::placeholder { color: rgba(196,181,253,0.25); }
        .fp-message { font-size: 13px; line-height: 1.5; color: #34d399; background: rgba(52,211,153,0.08); border: 1px solid rgba(52,211,153,0.2); border-radius: 10px; padding: 10px 14px; }
        .fp-error { font-size: 13px; line-height: 1.5; color: #f472b6; background: rgba(244,114,182,0.08); border: 1px solid rgba(244,114,182,0.2); border-radius: 10px; padding: 10px 14px; }
        .fp-submit { padding: 14px; background: linear-gradient(135deg, #c4b5fd, #f472b6, #67e8f9); background-size: 300%; color: #1e1433; border: none; border-radius: 13px; font-family: 'Syne', sans-serif; font-size: 15px; font-weight: 800; cursor: pointer; transition: transform 0.2s; }
        .fp-submit:hover:not(:disabled) { transform: translateY(-2px); }
        .fp-submit:disabled { opacity: 0.6; cursor: not-allowed; }
        .fp-footer { margin-top: 20px; text-align: center; font-size: 13px; color: rgba(196,181,253,0.4); }
        .fp-footer a { color: #c4b5fd; text-decoration: none; font-weight: 600; }
        .fp-footer a:hover { color: #f472b6; }
      `}</style>
      <div className="fp-page">
        <div className="fp-orb" />
        <div className="fp-grid" />
        <div className="fp-card">
          <div className="fp-logo">
            <div className="fp-logo-bars">
              <span style={{ height: "10px", background: "#7c3aed" }} />
              <span style={{ height: "16px", background: "#a855f7" }} />
              <span style={{ height: "24px", background: "#c4b5fd" }} />
              <span style={{ height: "18px", background: "#f472b6" }} />
              <span style={{ height: "12px", background: "#e879f9", opacity: 0.7 }} />
              <span style={{ height: "7px", background: "#c4b5fd", opacity: 0.4 }} />
            </div>
            <span className="fp-logo-name"><em>Skill</em>Pulse</span>
          </div>

          <div className="fp-title">Reset your password</div>
          <div className="fp-sub">Enter your work email and we will send a secure reset link if an account exists.</div>

          <form className="fp-form" onSubmit={handleSubmit}>
            <div>
              <label className="fp-label" htmlFor="forgot-email">Work email</label>
              <div className={`fp-input-wrap ${focused ? "focused" : ""}`}>
                <span className="fp-icon">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
                </span>
                <input id="forgot-email" className="fp-input" type="email" placeholder="you@company.com" value={email} onChange={(e) => setEmail(e.target.value)} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} required />
              </div>
            </div>

            {message && <div className="fp-message">{message}</div>}
            {error && <div className="fp-error">{error}</div>}

            <button className="fp-submit" type="submit" disabled={loading}>
              {loading ? "Sending..." : "Send reset link"}
            </button>
          </form>

          <div className="fp-footer">
            Remembered it? <a href="/login">Sign in</a>
          </div>
        </div>
      </div>
    </>
  );
};

export default ForgotPassword;
