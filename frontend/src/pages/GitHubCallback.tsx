import React, { useEffect, useState } from "react";
import { API_BASE_URL } from "../api/auth";

function useAuthTheme() {
  const [theme, setTheme] = useState<"dark" | "light">(
    () => (localStorage.getItem("sp_theme") as "dark" | "light") || "dark"
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("sp_theme", next);
    document.documentElement.setAttribute("data-theme", next);
  };

  return { theme, toggle, isLight: theme === "light" };
}

const GitHubCallback: React.FC = () => {
  const { toggle, isLight } = useAuthTheme();

  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [message, setMessage] = useState('Completing GitHub sign in...');

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    const error = params.get('error');
    const errorMessage = params.get('message');

    if (error) {
      setStatus('error');
      setMessage(errorMessage || 'GitHub authorization could not be completed.');
      return;
    }

    if (!token) {
      setStatus('error');
      setMessage('GitHub login failed. No token received.');
      return;
    }

    localStorage.setItem('token', token);
    setStatus('success');
    setMessage('Signed in successfully! Redirecting...');

    setTimeout(async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/auth/whoami-full`, {
          headers: { Authorization: `Bearer ${token}` },
          credentials: "include",
        });
        const user = await res.json();
        localStorage.setItem("role", user.role);
        localStorage.setItem("full_name", user.full_name || user.username || "User");

        if (user.role === 'developer') window.location.href = '/dashboard/developer';
        else if (user.role === 'manager') window.location.href = '/dashboard/manager';
        else if (user.role === 'recruiter') window.location.href = '/dashboard/recruiter';
        else window.location.href = '/select-role';
      } catch {
        window.location.href = '/select-role';
      }
    }, 1000);
  }, []);

  const c = isLight ? {
    pageBg:        "#f5f3ff",
    cardBg:        "rgba(255,255,255,0.85)",
    cardBorder:    "rgba(124,58,237,0.15)",
    logoText:      "#3c3489",
    logoAccent:    "#7c3aed",
    titleColor:    "#26215c",
    msgColor:      "#534ab7",
    iconLoadingBg: "rgba(124,58,237,0.08)",
    iconLoadingBorder: "rgba(124,58,237,0.25)",
    iconSuccessBg: "rgba(52,211,153,0.12)",
    iconSuccessBorder: "rgba(52,211,153,0.3)",
    iconErrorBg:   "rgba(244,114,182,0.1)",
    iconErrorBorder: "rgba(244,114,182,0.3)",
    successColor:  "#0f9d72",
    errorColor:    "#be185d",
    spinnerTrack:  "rgba(124,58,237,0.15)",
    spinnerHead:   "#7c3aed",
    progressTrack: "rgba(124,58,237,0.1)",
    toggleBg:      "rgba(124,58,237,0.1)",
    toggleBorder:  "rgba(124,58,237,0.25)",
    toggleColor:   "#7c3aed",
    gridLine:      "rgba(124,58,237,0.04)",
    orb1:          "rgba(124,58,237,0.12)",
    orb2:          "rgba(244,114,182,0.08)",
  } : {
    pageBg:        "#0f0c1a",
    cardBg:        "rgba(255,255,255,0.03)",
    cardBorder:    "rgba(167,139,250,0.15)",
    logoText:      "white",
    logoAccent:    "#c4b5fd",
    titleColor:    "white",
    msgColor:      "rgba(196,181,253,0.5)",
    iconLoadingBg: "rgba(167,139,250,0.1)",
    iconLoadingBorder: "rgba(167,139,250,0.2)",
    iconSuccessBg: "rgba(52,211,153,0.1)",
    iconSuccessBorder: "rgba(52,211,153,0.2)",
    iconErrorBg:   "rgba(244,114,182,0.1)",
    iconErrorBorder: "rgba(244,114,182,0.2)",
    successColor:  "#34d399",
    errorColor:    "#f472b6",
    spinnerTrack:  "rgba(196,181,253,0.2)",
    spinnerHead:   "#c4b5fd",
    progressTrack: "rgba(167,139,250,0.1)",
    toggleBg:      "rgba(167,139,250,0.08)",
    toggleBorder:  "rgba(167,139,250,0.2)",
    toggleColor:   "rgba(167,139,250,0.7)",
    gridLine:      "rgba(167,139,250,0.04)",
    orb1:          "rgba(124,58,237,0.2)",
    orb2:          "rgba(244,114,182,0.12)",
  };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500;600;700&display=swap');
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        .cb-page {
          min-height: 100vh; display: flex; flex-direction: column;
          align-items: center; justify-content: center;
          font-family: 'DM Sans', sans-serif;
          position: relative; overflow: hidden;
          transition: background 0.3s ease;
        }

        .cb-orb1 { position: fixed; border-radius: 50%; pointer-events: none;
          width: 700px; height: 700px;
          top: -200px; left: -150px; animation: cbDrift1 9s ease-in-out infinite alternate; }
        .cb-orb2 { position: fixed; border-radius: 50%; pointer-events: none;
          width: 500px; height: 500px;
          bottom: -120px; right: -100px; animation: cbDrift2 12s ease-in-out infinite alternate; }
        @keyframes cbDrift1 { from{transform:translate(0,0)} to{transform:translate(40px,30px) scale(1.08)} }
        @keyframes cbDrift2 { from{transform:translate(0,0)} to{transform:translate(-30px,-20px) scale(1.1)} }

        .cb-grid { position: fixed; inset: 0; pointer-events: none; }

        .cb-card {
          position: relative; z-index: 2;
          border-radius: 24px; padding: 48px 44px;
          text-align: center; max-width: 400px; width: 100%;
          backdrop-filter: blur(28px);
          animation: cbPop 0.45s cubic-bezier(0.22,1,0.36,1);
          transition: background 0.3s ease, border-color 0.3s ease;
        }
        @keyframes cbPop { from { opacity:0; transform:scale(0.94) translateY(12px); } to { opacity:1; transform:scale(1) translateY(0); } }

        .cb-logo { display: flex; align-items: center; justify-content: center; gap: 9px; margin-bottom: 32px; }
        .cb-logo-bars { display: flex; gap: 3px; align-items: flex-end; }
        .cb-logo-bars span { display: block; width: 4px; border-radius: 2px; }
        .cb-brand { font-family: 'Syne', sans-serif; font-size: 18px; font-weight: 800; letter-spacing: -0.3px; }

        .cb-icon {
          width: 64px; height: 64px; border-radius: 50%;
          display: flex; align-items: center; justify-content: center;
          margin: 0 auto 20px;
          border: 1px solid;
          transition: background 0.3s ease, border-color 0.3s ease;
        }
        .cb-icon.loading { animation: cbPulse 1.4s ease infinite; }
        @keyframes cbPulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.5;transform:scale(0.95)} }

        .cb-spinner {
          width: 24px; height: 24px;
          border: 2.5px solid;
          border-radius: 50%;
          animation: cbSpin 0.8s linear infinite;
        }
        @keyframes cbSpin { to { transform: rotate(360deg); } }

        .cb-title {
          font-family: 'Syne', sans-serif;
          font-size: 20px; font-weight: 800;
          letter-spacing: -0.5px;
          margin-bottom: 8px;
        }

        .cb-msg { font-size: 13.5px; line-height: 1.6; }

        .cb-progress {
          margin-top: 24px; height: 3px;
          border-radius: 2px; overflow: hidden;
        }
        .cb-progress-fill {
          height: 100%; border-radius: 2px;
          background: linear-gradient(90deg, #c4b5fd, #f472b6, #67e8f9);
          background-size: 200%;
          animation: cbProgress 1.5s ease-in-out infinite, cbGrad 2s linear infinite;
          width: 60%;
        }
        @keyframes cbProgress {
          0%   { transform: translateX(-100%); }
          100% { transform: translateX(250%); }
        }
        @keyframes cbGrad {
          from { background-position: 0%; }
          to   { background-position: 200%; }
        }

        .cb-retry {
          margin-top: 24px; padding: 12px 28px;
          background: linear-gradient(135deg, #7c3aed, #a855f7);
          color: white; border: none; border-radius: 13px;
          font-family: 'DM Sans', sans-serif; font-size: 14px; font-weight: 600;
          cursor: pointer; transition: all 0.2s;
          box-shadow: 0 6px 20px rgba(124,58,237,0.3);
        }
        .cb-retry:hover { transform: translateY(-2px); box-shadow: 0 10px 28px rgba(124,58,237,0.4); }

        .cb-theme-btn { position: fixed; top: 20px; right: 20px; z-index: 50; display: flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 10px; border: 1px solid; font-family: 'DM Sans', sans-serif; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
      `}</style>

      <div className="cb-page" style={{ background: c.pageBg }}>

        {/* Theme toggle button */}
        <button
          className="cb-theme-btn"
          onClick={toggle}
          style={{ background: c.toggleBg, borderColor: c.toggleBorder, color: c.toggleColor }}
        >
          {isLight ? (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
          )}
          {isLight ? "Dark Mode" : "Light Mode"}
        </button>

        <div className="cb-orb1" style={{ background: `radial-gradient(circle, ${c.orb1} 0%, transparent 65%)` }} />
        <div className="cb-orb2" style={{ background: `radial-gradient(circle, ${c.orb2} 0%, transparent 65%)` }} />
        <div className="cb-grid" style={{ backgroundImage: `linear-gradient(${c.gridLine} 1px, transparent 1px), linear-gradient(90deg, ${c.gridLine} 1px, transparent 1px)`, backgroundSize: "48px 48px" }} />

        <div className="cb-card" style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}` }}>

          {/* Logo */}
          <div className="cb-logo">
            <div className="cb-logo-bars">
              <span style={{height:'10px',background:'#7c3aed'}} />
              <span style={{height:'16px',background:'#a855f7'}} />
              <span style={{height:'24px',background:'#c4b5fd'}} />
              <span style={{height:'18px',background:'#f472b6'}} />
              <span style={{height:'12px',background:'#e879f9',opacity:0.7}} />
              <span style={{height:'7px',background:'#c4b5fd',opacity:0.4}} />
            </div>
            <span className="cb-brand" style={{ color: c.logoText }}>
              <span style={{ color: c.logoAccent }}>Skill</span>Pulse
            </span>
          </div>

          {/* Icon */}
          <div
            className={`cb-icon ${status}`}
            style={{
              background: status === 'loading' ? c.iconLoadingBg : status === 'success' ? c.iconSuccessBg : c.iconErrorBg,
              borderColor: status === 'loading' ? c.iconLoadingBorder : status === 'success' ? c.iconSuccessBorder : c.iconErrorBorder,
            }}
          >
            {status === 'loading' && (
              <div className="cb-spinner" style={{ borderColor: c.spinnerTrack, borderTopColor: c.spinnerHead }} />
            )}
            {status === 'success' && (
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke={c.successColor} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>
              </svg>
            )}
            {status === 'error' && (
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke={c.errorColor} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/><path d="m15 9-6 6M9 9l6 6"/>
              </svg>
            )}
          </div>

          {/* Title */}
          <div className="cb-title" style={{ color: c.titleColor }}>
            {status === 'loading' && 'Signing you in...'}
            {status === 'success' && 'Welcome to SkillPulse!'}
            {status === 'error' && 'Something went wrong'}
          </div>

          {/* Message */}
          <div className="cb-msg" style={{ color: c.msgColor }}>{message}</div>

          {/* Loading progress bar */}
          {status === 'loading' && (
            <div className="cb-progress" style={{ background: c.progressTrack }}>
              <div className="cb-progress-fill" />
            </div>
          )}

          {/* Error retry */}
          {status === 'error' && (
            <button className="cb-retry" onClick={() => window.location.href = '/login'}>
              Back to Login
            </button>
          )}

        </div>
      </div>
    </>
  );
};

export default GitHubCallback;