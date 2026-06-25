import React, { useState, useEffect } from "react";
import type { FormEvent } from "react";
import { API_BASE_URL, register } from "../api/auth";



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

const Register: React.FC = () => {
  const { toggle, isLight } = useAuthTheme();

  const [form, setForm] = useState({ username: '', full_name: '', work_email: '', role: '', specialization: '', password: '', confirm_password: '' });
  const [focused, setFocused] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [githubLoading, setGithubLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  React.useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('error') === 'already_registered') {
      setError('This GitHub account is already registered. Please sign in instead.');
    }
  }, []);

  const update = (field: string, value: string) => setForm(prev => ({ ...prev, [field]: value }));
  const handleGitHubLogin = () => { setError(null); setGithubLoading(true); window.location.href = `${API_BASE_URL}/auth/github?action=register`; };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault(); setError(null);
    if (form.username.length < 3) { setError("Username must be at least 3 characters."); return; }
    if (form.full_name.trim().length < 3) { setError("Please enter a valid full name."); return; }
    const passwordRegex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/;
    if (!passwordRegex.test(form.password)) { setError("Password must be 8+ characters, include uppercase, lowercase, a number and a special character."); return; }
    if (form.password !== form.confirm_password) { setError("Passwords do not match."); return; }
    if (!form.role) { setError("Please select your primary role."); return; }
    if (form.role === 'developer' && !form.specialization) { setError("Please select your specialization."); return; }
    setLoading(true);
    try {
      await register({ username: form.username, full_name: form.full_name, work_email: form.work_email, role: form.role, specialization: form.role === 'developer' ? form.specialization : undefined, password: form.password });
      window.location.href = `/verify-email?email=${encodeURIComponent(form.work_email)}`;
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { detail?: string | Array<{ msg: string }> } } };
      const detail = axiosError.response?.data?.detail;
      if (Array.isArray(detail)) setError(detail[0].msg);
      else if (typeof detail === 'string') setError(detail);
      else setError('Registration failed. Please check your connection.');
    } finally { setLoading(false); }
  };

 
  const c = isLight ? {
    pageBg:       "#f5f3ff",
    leftBg:       "linear-gradient(135deg,#f0eeff 0%,#fce7f3 100%)",
    rightBg:      "rgba(255,255,255,0.92)",
    rightBorder:  "rgba(124,58,237,0.12)",
    logoText:     "#3c3489",
    logoAccent:   "#7c3aed",
    eyebrowBg:    "rgba(124,58,237,0.1)",
    eyebrowBorder:"rgba(124,58,237,0.25)",
    eyebrowColor: "#7c3aed",
    heroTitle:    "#26215c",
    heroSub:      "#534ab7",
    featBg:       "rgba(255,255,255,0.6)",
    featBorder:   "rgba(124,58,237,0.15)",
    quoteBg:      "rgba(255,255,255,0.7)",
    quoteBorder:  "rgba(124,58,237,0.2)",
    quoteTitle:   "#26215c",
    quoteSub:     "#534ab7",
    cardTitle:    "#26215c",
    cardSub:      "#534ab7",
    divLine:      "rgba(124,58,237,0.12)",
    divText:      "#534ab7",
    fieldLabel:   "#7c3aed",
    inputBg:      "rgba(124,58,237,0.05)",
    inputBorder:  "rgba(124,58,237,0.15)",
    inputFocBorder:"rgba(124,58,237,0.45)",
    inputFocBg:   "rgba(124,58,237,0.08)",
    inputFocShadow:"rgba(124,58,237,0.09)",
    inputIcon:    "#a855f7",
    inputText:    "#26215c",
    placeholder:  "rgba(83,74,183,0.4)",
    roleOptionBg: "rgba(124,58,237,0.03)",
    roleOptionBorder:"rgba(124,58,237,0.1)",
    roleOptSelBg: "rgba(124,58,237,0.08)",
    roleOptSelBorder:"rgba(124,58,237,0.4)",
    roleLabel:    "#26215c",
    roleDesc:     "#534ab7",
    radioSel:     "#c4b5fd",
    errorBg:      "rgba(244,114,182,0.1)",
    errorBorder:  "rgba(244,114,182,0.25)",
    signinText:   "rgba(83,74,183,0.6)",
    signinLink:   "#7c3aed",
    toggleBg:     "rgba(124,58,237,0.1)",
    toggleBorder: "rgba(124,58,237,0.25)",
    toggleColor:  "#7c3aed",
    gridLine:     "rgba(124,58,237,0.04)",
    orb1:         "rgba(124,58,237,0.12)",
    orb2:         "rgba(244,114,182,0.08)",
    orb3:         "rgba(103,232,249,0.06)",
  } : {
    pageBg:       "#0f0c1a",
    leftBg:       "transparent",
    rightBg:      "rgba(255,255,255,0.022)",
    rightBorder:  "rgba(167,139,250,0.1)",
    logoText:     "white",
    logoAccent:   "#c4b5fd",
    eyebrowBg:    "rgba(167,139,250,0.1)",
    eyebrowBorder:"rgba(167,139,250,0.22)",
    eyebrowColor: "#c4b5fd",
    heroTitle:    "white",
    heroSub:      "rgba(196,181,253,0.5)",
    featBg:       "rgba(167,139,250,0.05)",
    featBorder:   "rgba(167,139,250,0.1)",
    quoteBg:      "rgba(167,139,250,0.07)",
    quoteBorder:  "rgba(167,139,250,0.15)",
    quoteTitle:   "white",
    quoteSub:     "rgba(196,181,253,0.45)",
    cardTitle:    "white",
    cardSub:      "rgba(196,181,253,0.45)",
    divLine:      "rgba(167,139,250,0.1)",
    divText:      "rgba(167,139,250,0.35)",
    fieldLabel:   "rgba(196,181,253,0.45)",
    inputBg:      "rgba(167,139,250,0.07)",
    inputBorder:  "rgba(167,139,250,0.14)",
    inputFocBorder:"rgba(196,181,253,0.45)",
    inputFocBg:   "rgba(167,139,250,0.11)",
    inputFocShadow:"rgba(167,139,250,0.09)",
    inputIcon:    "rgba(167,139,250,0.4)",
    inputText:    "white",
    placeholder:  "rgba(167,139,250,0.28)",
    roleOptionBg: "rgba(167,139,250,0.04)",
    roleOptionBorder:"rgba(167,139,250,0.1)",
    roleOptSelBg: "rgba(167,139,250,0.12)",
    roleOptSelBorder:"rgba(196,181,253,0.4)",
    roleLabel:    "rgba(233,213,255,0.8)",
    roleDesc:     "rgba(167,139,250,0.45)",
    radioSel:     "#c4b5fd",
    errorBg:      "rgba(244,114,182,0.08)",
    errorBorder:  "rgba(244,114,182,0.2)",
    signinText:   "rgba(167,139,250,0.45)",
    signinLink:   "#c4b5fd",
    toggleBg:     "rgba(167,139,250,0.08)",
    toggleBorder: "rgba(167,139,250,0.2)",
    toggleColor:  "rgba(167,139,250,0.7)",
    gridLine:     "rgba(167,139,250,0.04)",
    orb1:         "rgba(124,58,237,0.22)",
    orb2:         "rgba(244,114,182,0.14)",
    orb3:         "rgba(103,232,249,0.1)",
  };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500;600;700&display=swap');
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        .sp-reg { font-family: 'DM Sans', sans-serif; min-height: 100vh; display: flex; overflow: hidden; position: relative; transition: background 0.3s ease; }
        .sp-orb1 { position: fixed; border-radius: 50%; z-index: 0; width: 700px; height: 700px; top: -200px; left: -150px; animation: spDrift1 9s ease-in-out infinite alternate; pointer-events: none; }
        .sp-orb2 { position: fixed; border-radius: 50%; z-index: 0; width: 500px; height: 500px; bottom: -120px; right: 380px; animation: spDrift2 12s ease-in-out infinite alternate; pointer-events: none; }
        .sp-orb3 { position: fixed; border-radius: 50%; z-index: 0; width: 320px; height: 320px; top: 35%; right: -60px; animation: spDrift1 7s ease-in-out infinite alternate-reverse; pointer-events: none; }
        @keyframes spDrift1 { from{transform:translate(0,0) scale(1)} to{transform:translate(40px,30px) scale(1.08)} }
        @keyframes spDrift2 { from{transform:translate(0,0)} to{transform:translate(-30px,-20px) scale(1.1)} }
        .sp-grid { position: fixed; inset: 0; z-index: 1; pointer-events: none; }
        .sp-layout { position: relative; z-index: 2; display: grid; grid-template-columns: 1fr 560px; width: 100%; height: 100vh; overflow: hidden; }
        .sp-left { display: flex; flex-direction: column; justify-content: space-between; padding: 36px 52px; overflow: hidden; }
        .sp-logo { display: flex; align-items: center; gap: 10px; }
        .sp-logo-bars { display: flex; gap: 3px; align-items: flex-end; }
        .sp-logo-bars span { display: block; width: 4px; border-radius: 2px; }
        .sp-hero { flex: 1; display: flex; flex-direction: column; justify-content: center; padding: 20px 0; }
        .sp-eyebrow { display: inline-flex; align-items: center; gap: 8px; padding: 5px 14px; border-radius: 100px; font-size: 10px; font-weight: 700; letter-spacing: 0.8px; text-transform: uppercase; margin-bottom: 16px; width: fit-content; }
        .sp-pulse-dot { width: 6px; height: 6px; border-radius: 50%; background: #f472b6; animation: spBlink 2s ease infinite; }
        @keyframes spBlink { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.35;transform:scale(0.65)} }
        .sp-hero-title { font-family: 'Syne', sans-serif; font-size: 42px; font-weight: 800; line-height: 1.08; letter-spacing: -2px; margin-bottom: 12px; }
        .sp-grad { background: linear-gradient(135deg, #c4b5fd, #f472b6, #67e8f9, #a78bfa, #c4b5fd); background-size: 300%; -webkit-background-clip: text; -webkit-text-fill-color: transparent; animation: spGrad 5s ease infinite; }
        @keyframes spGrad { 0%{background-position:0% 50%} 50%{background-position:100% 50%} 100%{background-position:0% 50%} }
        .sp-features { display: flex; flex-direction: column; gap: 8px; margin: 18px 0 0 0; }
        .sp-feat { display: flex; align-items: center; gap: 12px; padding: 10px 14px; border-radius: 12px; transition: all 0.2s; }
        .sp-feat-icon { width: 32px; height: 32px; border-radius: 9px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
        .sp-feat-label { font-size: 12.5px; font-weight: 700; margin-bottom: 1px; letter-spacing: -0.2px; }
        .sp-feat-desc { font-size: 11px; font-weight: 300; line-height: 1.4; }
        .sp-quote-wrap { position: relative; margin-top: 20px; }
        .sp-quote-mark { font-family: 'Syne', sans-serif; font-size: 90px; font-weight: 800; line-height: 0.7; background: linear-gradient(135deg, #c4b5fd, #f472b6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; opacity: 0.35; position: absolute; top: -12px; left: -6px; pointer-events: none; animation: spGrad 5s ease infinite; background-size: 300%; }
        .sp-quote-inner { padding: 20px 22px 18px 22px; border-radius: 18px; position: relative; overflow: hidden; transition: background 0.3s ease, border-color 0.3s ease; }
        .sp-quote-inner::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: linear-gradient(180deg, #c4b5fd, #f472b6, #67e8f9); border-radius: 3px; }
        .sp-quote-text { font-family: 'Syne', sans-serif; font-size: 22px; font-weight: 800; line-height: 1.25; letter-spacing: -0.8px; margin-bottom: 8px; position: relative; z-index: 1; }
        .sp-quote-sub { font-size: 12px; font-weight: 300; line-height: 1.6; position: relative; z-index: 1; }

        .sp-right { display: flex; align-items: center; justify-content: center; padding: 24px 36px; height: 100vh; overflow: hidden; transition: background 0.3s ease, border-color 0.3s ease; }
        .sp-card { width: 100%; }
        .sp-card-head { margin-bottom: 16px; }
        .sp-card-title { font-family: 'Syne', sans-serif; font-size: 22px; font-weight: 800; letter-spacing: -0.8px; margin-bottom: 4px; line-height: 1.2; }
        .sp-gh-btn { width: 100%; height: 50px; display: flex; align-items: center; justify-content: center; gap: 10px; background: linear-gradient(135deg, #7c3aed, #a855f7, #ec4899); background-size: 200%; border: none; border-radius: 14px; font-family: 'DM Sans', sans-serif; font-size: 15px; font-weight: 600; color: white; cursor: pointer; transition: all 0.3s; box-shadow: 0 6px 22px rgba(124,58,237,0.3); margin-bottom: 8px; }
        .sp-gh-btn:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 10px 30px rgba(168,85,247,0.4); }
        .sp-gh-btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .sp-secure { display: flex; align-items: center; justify-content: center; gap: 5px; margin-bottom: 12px; font-size: 10px; font-weight: 600; letter-spacing: 0.5px; }
        .sp-divider { display: flex; align-items: center; gap: 14px; margin-bottom: 12px; }
        .sp-div-line { flex: 1; height: 1px; }
        .sp-div-txt { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.6px; }
        .sp-form { display: flex; flex-direction: column; gap: 8px; }
        .sp-row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        .sp-field { display: flex; flex-direction: column; gap: 4px; }
        .sp-field-label { font-size: 10px; font-weight: 700; letter-spacing: 0.6px; text-transform: uppercase; }
        .sp-input-wrap { display: flex; align-items: center; gap: 8px; padding: 0 12px; height: 40px; border-radius: 11px; transition: all 0.25s; }
        .sp-input-field { flex: 1; border: none; background: transparent !important; outline: none; font-family: 'DM Sans', sans-serif; font-size: 13px; }
        .sp-input-field:-webkit-autofill { -webkit-box-shadow: 0 0 0px 1000px rgba(30,20,51,0.95) inset !important; -webkit-text-fill-color: white !important; }
        .sp-input-icon { flex-shrink: 0; display: flex; align-items: center; transition: color 0.2s; }
        .sp-role-group { display: flex; flex-direction: column; gap: 5px; }
        .sp-role-option { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 10px; cursor: pointer; transition: all 0.2s; }
        .sp-role-radio { width: 14px; height: 14px; border-radius: 50%; border-width: 2px; border-style: solid; flex-shrink: 0; transition: all 0.2s; display: flex; align-items: center; justify-content: center; }
        .sp-role-label { font-size: 12px; font-weight: 600; }
        .sp-role-desc { font-size: 10px; margin-top: 1px; }
        .sp-error-wrap { height: 36px; margin-top: 2px; }
        .sp-error { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 9px; font-size: 11px; color: #f472b6; font-weight: 500; animation: spFade 0.2s ease; height: 100%; }
        @keyframes spFade { from{opacity:0;transform:translateY(-4px)} to{opacity:1;transform:translateY(0)} }
        .sp-submit { width: 100%; height: 46px; margin-top: 2px; display: flex; align-items: center; justify-content: center; gap: 8px; background: linear-gradient(135deg, #c4b5fd, #f472b6, #67e8f9); background-size: 300%; border: none; border-radius: 13px; font-family: 'Syne', sans-serif; font-size: 14px; font-weight: 700; cursor: pointer; transition: all 0.3s; box-shadow: 0 5px 18px rgba(196,181,253,0.2); animation: spGrad 4s ease infinite; }
        .sp-submit:hover:not(:disabled) { transform: translateY(-2px); }
        .sp-submit:disabled { opacity: 0.6; cursor: not-allowed; }
        .sp-spinner { width: 15px; height: 15px; border: 2px solid rgba(30,20,51,0.3); border-top-color: #1e1433; border-radius: 50%; animation: spSpin 0.7s linear infinite; }
        @keyframes spSpin { to{transform:rotate(360deg)} }
        .sp-signin { text-align: center; margin-top: 10px; font-size: 12px; }
        .sp-theme-btn { position: fixed; top: 20px; right: 20px; z-index: 50; display: flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 10px; border: 1px solid; font-family: 'DM Sans', sans-serif; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
        .sp-pwd-toggle { background: none; border: none; padding: 0; cursor: pointer; display: flex; align-items: center; transition: color 0.2s; outline: none; }
      `}</style>

      <div className="sp-reg" style={{ background: c.pageBg }}>

        {/* Theme toggle button */}
        <button
          className="sp-theme-btn"
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

        {/* Orbs */}
        <div className="sp-orb1" style={{ background: `radial-gradient(circle, ${c.orb1} 0%, transparent 65%)` }} />
        <div className="sp-orb2" style={{ background: `radial-gradient(circle, ${c.orb2} 0%, transparent 65%)` }} />
        <div className="sp-orb3" style={{ background: `radial-gradient(circle, ${c.orb3} 0%, transparent 65%)` }} />
        <div className="sp-grid" style={{ backgroundImage: `linear-gradient(${c.gridLine} 1px, transparent 1px), linear-gradient(90deg, ${c.gridLine} 1px, transparent 1px)`, backgroundSize: "48px 48px" }} />

        <div className="sp-layout">

          {/* ── LEFT ── */}
          <div className="sp-left" style={{ background: c.leftBg }}>
            <div className="sp-logo">
              <div className="sp-logo-bars">
                <span style={{ height: "10px", background: "#7c3aed" }} />
                <span style={{ height: "16px", background: "#a855f7" }} />
                <span style={{ height: "24px", background: "#c4b5fd" }} />
                <span style={{ height: "18px", background: "#f472b6" }} />
                <span style={{ height: "12px", background: "#e879f9", opacity: 0.7 }} />
                <span style={{ height: "7px", background: "#c4b5fd", opacity: 0.4 }} />
              </div>
              <span style={{ fontFamily: "'Syne', sans-serif", fontSize: "19px", fontWeight: 800, color: c.logoText, letterSpacing: "-0.3px" }}>
                <span style={{ color: c.logoAccent }}>Skill</span>Pulse
              </span>
            </div>

            <div className="sp-hero">
              <div className="sp-eyebrow" style={{ background: c.eyebrowBg, border: `1px solid ${c.eyebrowBorder}`, color: c.eyebrowColor }}>
                <div className="sp-pulse-dot" />
                Developer Intelligence Platform
              </div>
              <h1 className="sp-hero-title" style={{ color: c.heroTitle }}>
                Measure your<br/>
                <span className="sp-grad">coding mastery.</span>
              </h1>
              <p style={{ fontSize: "13.5px", color: c.heroSub, lineHeight: 1.65, maxWidth: "380px", fontWeight: 300 }}>
                Connect your GitHub and get AI-powered insights into your code quality, security awareness, and skill trajectory.
              </p>

              <div className="sp-features">
                {[
                  { icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={isLight ? "#7c3aed" : "#c4b5fd"} strokeWidth="1.8" strokeLinecap="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>, iconBg: isLight ? "rgba(124,58,237,0.12)" : "rgba(196,181,253,0.12)", label: "Deep Code Understanding", desc: "Go beyond syntax — uncover the story your code tells" },
                  { icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#f472b6" strokeWidth="1.8" strokeLinecap="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>, iconBg: "rgba(244,114,182,0.12)", label: "Instant Actionable Insights", desc: "Know exactly where to grow — no guesswork needed" },
                  { icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={isLight ? "#0e7490" : "#67e8f9"} strokeWidth="1.8" strokeLinecap="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>, iconBg: isLight ? "rgba(14,116,144,0.1)" : "rgba(103,232,249,0.12)", label: "Built for Every Role", desc: "Developers, managers, and recruiters — one platform" },
                ].map((feat) => (
                  <div key={feat.label} className="sp-feat" style={{ background: c.featBg, border: `1px solid ${c.featBorder}` }}>
                    <div className="sp-feat-icon" style={{ background: feat.iconBg }}>{feat.icon}</div>
                    <div>
                      <div className="sp-feat-label" style={{ color: c.heroTitle }}>{feat.label}</div>
                      <div className="sp-feat-desc" style={{ color: c.heroSub }}>{feat.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="sp-quote-wrap">
              <div className="sp-quote-mark">"</div>
              <div className="sp-quote-inner" style={{ background: c.quoteBg, border: `1px solid ${c.quoteBorder}` }}>
                <div className="sp-quote-text" style={{ color: c.quoteTitle }}>
                  Your code tells<br/>a <span style={{ color: "#a855f7" }}>story.</span>
                </div>
                <div className="sp-quote-sub" style={{ color: c.quoteSub }}>
                  SkillPulse reads between the lines —<br/>turning commits into career intelligence.
                </div>
              </div>
            </div>
          </div>

          {/* ── RIGHT ── */}
          <div className="sp-right" style={{ background: c.rightBg, borderLeft: `1px solid ${c.rightBorder}` }}>
            <div className="sp-card">

              <div className="sp-card-head">
                <div className="sp-card-title" style={{ color: c.cardTitle }}>
                  Start your<br/><span style={{ color: "#7c3aed" }}>dev journey.</span>
                </div>
                <div style={{ fontSize: "12px", color: c.cardSub, fontWeight: 300 }}>Join thousands of developers leveling up their craft.</div>
              </div>

              <button className="sp-gh-btn" type="button" disabled={githubLoading} onClick={handleGitHubLogin}>
                {githubLoading ? (
                  <><div className="sp-spinner" /> Redirecting to GitHub...</>
                ) : (
                  <><svg width="18" height="18" viewBox="0 0 24 24" fill="white"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>Continue with GitHub</>
                )}
              </button>

              <div className="sp-secure" style={{ color: isLight ? "#7c3aed" : "rgba(167,139,250,0.5)" }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>
                Secure OAuth 2.0
              </div>

              <div className="sp-divider">
                <div className="sp-div-line" style={{ background: c.divLine }} />
                <span className="sp-div-txt" style={{ color: c.divText }}>or register with email</span>
                <div className="sp-div-line" style={{ background: c.divLine }} />
              </div>

              <form className="sp-form" onSubmit={handleSubmit}>

                <div className="sp-row2">
                  {[{ key: "full_name", label: "Full Name", placeholder: "Your full name", icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>, type: "text" }, { key: "username", label: "Username", placeholder: "Choose a username", icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>, type: "text" }].map(field => (
                    <div key={field.key} className="sp-field">
                      <label className="sp-field-label" style={{ color: c.fieldLabel }}>{field.label}</label>
                      <div className="sp-input-wrap" style={{ background: focused === field.key ? c.inputFocBg : c.inputBg, border: `1.5px solid ${focused === field.key ? c.inputFocBorder : c.inputBorder}`, boxShadow: focused === field.key ? `0 0 0 3px ${c.inputFocShadow}` : "none" }}>
                        <span className="sp-input-icon" style={{ color: c.inputIcon }}>{field.icon}</span>
                        <input className="sp-input-field" type={field.type} placeholder={field.placeholder} value={(form as any)[field.key]} onChange={e => update(field.key, e.target.value)} onFocus={() => setFocused(field.key)} onBlur={() => setFocused(null)} style={{ color: c.inputText }} required />
                      </div>
                    </div>
                  ))}
                </div>

                <div className="sp-field">
                  <label className="sp-field-label" style={{ color: c.fieldLabel }}>Work Email</label>
                  <div className="sp-input-wrap" style={{ background: focused === "work_email" ? c.inputFocBg : c.inputBg, border: `1.5px solid ${focused === "work_email" ? c.inputFocBorder : c.inputBorder}`, boxShadow: focused === "work_email" ? `0 0 0 3px ${c.inputFocShadow}` : "none" }}>
                    <span className="sp-input-icon" style={{ color: c.inputIcon }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg></span>
                    <input className="sp-input-field" type="email" placeholder="you@company.com" value={form.work_email} onChange={e => update("work_email", e.target.value)} onFocus={() => setFocused("work_email")} onBlur={() => setFocused(null)} style={{ color: c.inputText }} required />
                  </div>
                </div>

                <div className="sp-row2">
                  {[{ key: "password", label: "Password", placeholder: "••••••••", show: showPassword, toggle: () => setShowPassword(!showPassword) }, { key: "confirm_password", label: "Confirm Password", placeholder: "Repeat password", show: showConfirm, toggle: () => setShowConfirm(!showConfirm) }].map(field => (
                    <div key={field.key} className="sp-field">
                      <label className="sp-field-label" style={{ color: c.fieldLabel }}>{field.label}</label>
                      <div className="sp-input-wrap" style={{ background: focused === field.key ? c.inputFocBg : c.inputBg, border: `1.5px solid ${focused === field.key ? c.inputFocBorder : c.inputBorder}`, boxShadow: focused === field.key ? `0 0 0 3px ${c.inputFocShadow}` : "none" }}>
                        <span className="sp-input-icon" style={{ color: c.inputIcon }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg></span>
                        <input className="sp-input-field" type={field.show ? "text" : "password"} placeholder={field.placeholder} value={(form as any)[field.key]} onChange={e => update(field.key, e.target.value)} onFocus={() => setFocused(field.key)} onBlur={() => setFocused(null)} style={{ color: c.inputText }} required />
                        <button type="button" className="sp-pwd-toggle" style={{ color: c.inputIcon }} onClick={field.toggle}>
                          {field.show ? <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg> : <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="sp-field">
                  <label className="sp-field-label" style={{ color: c.fieldLabel }}>Account Type</label>
                  <div className="sp-role-group">
                    {[{ value: "developer", label: "Developer", desc: "Personal growth & analysis" }, { value: "manager", label: "Engineering Manager", desc: "Team intelligence & evaluation" }, { value: "recruiter", label: "Technical Recruiter", desc: "Candidate screening & insights" }].map(r => (
                      <div key={r.value} className="sp-role-option" style={{ background: form.role === r.value ? c.roleOptSelBg : c.roleOptionBg, border: `1.5px solid ${form.role === r.value ? c.roleOptSelBorder : c.roleOptionBorder}` }} onClick={() => update("role", r.value)}>
                        <div className="sp-role-radio" style={{ borderColor: form.role === r.value ? c.radioSel : (isLight ? "rgba(124,58,237,0.3)" : "rgba(167,139,250,0.3)"), background: form.role === r.value ? c.radioSel : "transparent" }}>
                          {form.role === r.value && <div style={{ width: "5px", height: "5px", borderRadius: "50%", background: isLight ? "white" : "#1e1433" }} />}
                        </div>
                        <div>
                          <div className="sp-role-label" style={{ color: c.roleLabel }}>{r.label}</div>
                          <div className="sp-role-desc" style={{ color: c.roleDesc }}>{r.desc}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {form.role === "developer" && (
                  <div className="sp-field">
                    <label className="sp-field-label" style={{ color: c.fieldLabel }}>Specialization</label>
                    <div className="sp-role-group" style={{ flexDirection: "row", gap: "8px" }}>
                      {[{ value: "backend", label: "Backend" }, { value: "frontend", label: "Frontend" }, { value: "qa", label: "QA" }].map(s => (
                        <div key={s.value} className="sp-role-option" style={{ flex: 1, justifyContent: "center", padding: "8px", background: form.specialization === s.value ? c.roleOptSelBg : c.roleOptionBg, border: `1.5px solid ${form.specialization === s.value ? c.roleOptSelBorder : c.roleOptionBorder}` }} onClick={() => update("specialization", s.value)}>
                          <div className="sp-role-label" style={{ fontSize: "11.5px", color: c.roleLabel }}>{s.label}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="sp-error-wrap">
                  {error && <div className="sp-error" style={{ background: c.errorBg, border: `1px solid ${c.errorBorder}` }}><span>⚠</span> {error}</div>}
                </div>

                <button className="sp-submit" type="submit" disabled={loading} style={{ color: isLight ? "#26215c" : "#1e1433" }}>
                  {loading ? <><div className="sp-spinner" /> Creating account...</> : <>Create Account ✦</>}
                </button>
              </form>

              <div className="sp-signin" style={{ color: c.signinText }}>
                Already have an account? <a href="/login" style={{ color: c.signinLink, fontWeight: 600, textDecoration: "none" }}>Sign in</a>
              </div>

            </div>
          </div>
        </div>
      </div>
    </>
  );
};

export default Register;
