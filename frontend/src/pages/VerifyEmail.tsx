import type { FormEvent } from "react";
import React, { useState } from "react";
import { verifyEmail } from "../api/auth";

const VerifyEmail: React.FC = () => {
  const params = new URLSearchParams(window.location.search);
  const emailFromQuery = params.get("email") ?? "";

  const [workEmail] = useState(emailFromQuery);
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [codeFocused, setCodeFocused] = useState(false);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      await verifyEmail({ work_email: workEmail, code });
      setSuccess(true);
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { detail?: string } } };
      setError(axiosError.response?.data?.detail ?? "Verification failed. Please try again.");
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
          .ve-page {
            min-height: 100vh; display: flex; align-items: center; justify-content: center;
            background: #0f0c1a; font-family: 'DM Sans', sans-serif; padding: 24px;
            position: relative; overflow: hidden;
          }
          .ve-orb {
            position: fixed; border-radius: 50%;
            background: radial-gradient(circle, rgba(124,58,237,0.22) 0%, transparent 65%);
            width: 700px; height: 700px; top: -200px; left: -150px; pointer-events: none;
          }
          .ve-card {
            background: rgba(255,255,255,0.04); border: 1px solid rgba(167,139,250,0.15);
            border-radius: 24px; padding: 56px 48px; text-align: center;
            max-width: 420px; width: 100%; position: relative; z-index: 2;
            backdrop-filter: blur(20px);
          }
          .ve-title { font-family: 'Syne', sans-serif; font-size: 24px; font-weight: 800; color: white; margin-bottom: 8px; }
          .ve-sub { font-size: 14px; color: rgba(196,181,253,0.5); margin-bottom: 28px; line-height: 1.7; }
          .ve-btn {
            display: inline-flex; align-items: center; gap: 8px;
            padding: 13px 28px;
            background: linear-gradient(135deg, #7c3aed, #a855f7);
            color: white; border: none; border-radius: 13px;
            font-family: 'DM Sans', sans-serif; font-size: 15px; font-weight: 600;
            cursor: pointer; transition: all 0.2s;
            box-shadow: 0 6px 20px rgba(124,58,237,0.3);
          }
          .ve-btn:hover { transform: translateY(-2px); box-shadow: 0 10px 28px rgba(124,58,237,0.4); }
        `}</style>
        <div className="ve-page">
          <div className="ve-orb" />
          <div className="ve-card">
            <div className="ve-title">Email verified!</div>
            <div className="ve-sub">Your account is ready. Sign in to start your skill analysis.</div>
            <button className="ve-btn" type="button" onClick={() => { window.location.href = "/login"; }}>
              Sign in now →
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
        .ve-page {
          min-height: 100vh; display: flex; align-items: center; justify-content: center;
          background: #0f0c1a; font-family: 'DM Sans', sans-serif; padding: 24px;
          position: relative; overflow: hidden;
        }
        .ve-orb {
          position: fixed; border-radius: 50%;
          background: radial-gradient(circle, rgba(124,58,237,0.22) 0%, transparent 65%);
          width: 700px; height: 700px; top: -200px; left: -150px; pointer-events: none;
        }
        .ve-grid {
          position: fixed; inset: 0;
          background-image: linear-gradient(rgba(167,139,250,0.04) 1px, transparent 1px),
                            linear-gradient(90deg, rgba(167,139,250,0.04) 1px, transparent 1px);
          background-size: 48px 48px; pointer-events: none;
        }
        .ve-card {
          background: rgba(255,255,255,0.04); border: 1px solid rgba(167,139,250,0.15);
          border-radius: 24px; padding: 48px 40px;
          max-width: 440px; width: 100%; position: relative; z-index: 2;
          backdrop-filter: blur(20px);
        }
        .ve-title { font-family: 'Syne', sans-serif; font-size: 26px; font-weight: 800; color: white; margin-bottom: 8px; letter-spacing: -0.5px; }
        .ve-sub { font-size: 14px; color: rgba(196,181,253,0.5); margin-bottom: 28px; line-height: 1.7; }
        .ve-email { color: #c4b5fd; font-weight: 600; }
        .ve-form { display: flex; flex-direction: column; gap: 16px; }
        .ve-label { font-size: 12px; font-weight: 600; color: rgba(196,181,253,0.6); text-transform: uppercase; letter-spacing: 0.08em; }
        .ve-input-wrap {
          display: flex; align-items: center;
          background: rgba(255,255,255,0.04); border: 1px solid rgba(167,139,250,0.15);
          border-radius: 12px; padding: 0 14px; transition: border-color 0.2s;
        }
        .ve-input-wrap.focused { border-color: rgba(167,139,250,0.5); }
        .ve-input {
          flex: 1; background: transparent; border: none; outline: none;
          color: white; font-family: 'DM Sans', sans-serif; font-size: 22px;
          letter-spacing: 0.3em; text-align: center; padding: 14px 0;
        }
        .ve-input::placeholder { color: rgba(196,181,253,0.25); letter-spacing: 0.1em; font-size: 15px; }
        .ve-error {
          font-size: 13px; color: #fca5a5; background: rgba(239,68,68,0.1);
          border: 1px solid rgba(239,68,68,0.2); border-radius: 10px; padding: 10px 14px;
        }
        .ve-submit {
          padding: 14px; background: linear-gradient(135deg, #7c3aed, #a855f7);
          color: white; border: none; border-radius: 13px;
          font-family: 'DM Sans', sans-serif; font-size: 15px; font-weight: 600;
          cursor: pointer; transition: all 0.2s;
          box-shadow: 0 6px 20px rgba(124,58,237,0.3);
        }
        .ve-submit:hover:not(:disabled) { transform: translateY(-2px); }
        .ve-submit:disabled { opacity: 0.6; cursor: not-allowed; }
        .ve-footer { margin-top: 20px; text-align: center; font-size: 13px; color: rgba(196,181,253,0.4); }
        .ve-footer a { color: #c4b5fd; text-decoration: none; font-weight: 600; }
        .ve-footer a:hover { text-decoration: underline; }
      `}</style>
      <div className="ve-page">
        <div className="ve-orb" />
        <div className="ve-grid" />
        <div className="ve-card">
          <div className="ve-title">Verify your email</div>
          <div className="ve-sub">
            We sent a 6-digit code to{" "}
            {workEmail ? <span className="ve-email">{workEmail}</span> : "your email"}.
            Enter it below to activate your account.
          </div>

          <form className="ve-form" onSubmit={handleSubmit}>
            <div>
              <label className="ve-label" htmlFor="verification-code">Verification code</label>
              <div className={`ve-input-wrap ${codeFocused ? "focused" : ""}`}>
                <input
                  id="verification-code"
                  className="ve-input"
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  placeholder="000000"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  onFocus={() => setCodeFocused(true)}
                  onBlur={() => setCodeFocused(false)}
                  required
                />
              </div>
            </div>

            {error && <div className="ve-error">{error}</div>}

            <button className="ve-submit" type="submit" disabled={loading || code.length !== 6 || !workEmail}>
              {loading ? "Verifying..." : "Verify email →"}
            </button>
          </form>

          <div className="ve-footer">
            Already verified?{" "}
            <a href="/login" onClick={(e) => { e.preventDefault(); window.location.href = "/login"; }}>
              Sign in
            </a>
          </div>
        </div>
      </div>
    </>
  );
};

export default VerifyEmail;
