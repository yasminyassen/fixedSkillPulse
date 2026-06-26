import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/auth";

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

const roles = [
  {
    value: "developer",
    label: "Developer",
    desc: "Analyze your repositories and map your growth journey.",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
      </svg>
    ),
  },
  {
    value: "manager",
    label: "Engineering Manager",
    desc: "Evaluate team strengths and identify technical gaps.",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
        <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
      </svg>
    ),
  },
  {
    value: "recruiter",
    label: "Recruiter / Hiring",
    desc: "Screen candidates with objective data-driven insights.",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
        <circle cx="9" cy="7" r="4"/>
        <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
        <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
      </svg>
    ),
  },
];

const specializations = [
  { value: "backend", label: "Backend" },
  { value: "frontend", label: "Frontend" },
  { value: "qa", label: "QA" },
];

const RoleSelection: React.FC = () => {
  const { toggle, isLight } = useAuthTheme();

  const [selected, setSelected] = useState<string>("");
  const [selectedSpec, setSelectedSpec] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<{username: string; full_name: string; work_email: string; avatar_url?: string} | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/auth/whoami-full").then(res => {
      setUser(res.data);
    }).catch(() => {});
  }, []);

  const handleContinue = async () => {
    if (!selected) { setError("Please select a role to continue."); return; }
    if (selected === "developer" && !selectedSpec) { setError("Please select a specialization."); return; }

    setError(null);
    setLoading(true);
    try {
      await api.patch("/auth/complete-profile", {
        role: selected,
        specialization: selected === "developer" ? selectedSpec : null
      });
      localStorage.setItem("role", selected);

      if (selected === "manager")        navigate("/dashboard/manager");
      else if (selected === "recruiter") navigate("/dashboard/recruiter");
      else                               navigate("/dashboard/developer");
    } catch {
      setError("Failed to save your role. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const c = isLight ? {
    pageBg:           "#f5f3ff",
    cardBg:           "rgba(255,255,255,0.85)",
    cardBorder:       "rgba(124,58,237,0.15)",
    logoText:         "#3c3489",
    logoAccent:       "#7c3aed",
    titleColor:       "#26215c",
    subtitleColor:    "#534ab7",
    accountLabel:     "#7c3aed",
    fullNameColor:    "#26215c",
    verifiedBg:       "rgba(52,211,153,0.12)",
    verifiedBorder:   "rgba(52,211,153,0.3)",
    verifiedColor:    "#0f9d72",
    dividerColor:     "rgba(124,58,237,0.12)",
    infoLabel:        "rgba(124,58,237,0.55)",
    infoValue:        "#3c3489",
    roleTitle:        "#26215c",
    roleSubtitle:     "#534ab7",
    optionBg:         "rgba(124,58,237,0.04)",
    optionBorder:     "rgba(124,58,237,0.12)",
    optionSelBg:      "rgba(124,58,237,0.09)",
    optionSelBorder:  "rgba(124,58,237,0.4)",
    optionIconBg:     "rgba(124,58,237,0.08)",
    optionIconSelBg:  "rgba(124,58,237,0.16)",
    optionIconColor:  "rgba(124,58,237,0.55)",
    optionIconSelColor: "#7c3aed",
    optionLabel:      "#3c3489",
    optionDesc:       "rgba(83,74,183,0.6)",
    radioBorder:      "rgba(124,58,237,0.3)",
    radioSel:         "#7c3aed",
    radioDot:         "white",
    errorBg:          "rgba(244,114,182,0.1)",
    errorBorder:      "rgba(244,114,182,0.25)",
    errorColor:       "#be185d",
    toggleBg:         "rgba(124,58,237,0.1)",
    toggleBorder:     "rgba(124,58,237,0.25)",
    toggleColor:      "#7c3aed",
    gridLine:         "rgba(124,58,237,0.04)",
    orb1:             "rgba(124,58,237,0.12)",
    orb2:             "rgba(244,114,182,0.08)",
  } : {
    pageBg:           "#0f0c1a",
    cardBg:           "rgba(255,255,255,0.03)",
    cardBorder:       "rgba(167,139,250,0.14)",
    logoText:         "white",
    logoAccent:       "#c4b5fd",
    titleColor:       "white",
    subtitleColor:    "rgba(196,181,253,0.45)",
    accountLabel:     "rgba(167,139,250,0.4)",
    fullNameColor:    "white",
    verifiedBg:       "rgba(52,211,153,0.1)",
    verifiedBorder:   "rgba(52,211,153,0.2)",
    verifiedColor:    "#34d399",
    dividerColor:     "rgba(167,139,250,0.1)",
    infoLabel:        "rgba(167,139,250,0.35)",
    infoValue:        "rgba(226,232,240,0.75)",
    roleTitle:        "white",
    roleSubtitle:     "rgba(196,181,253,0.4)",
    optionBg:         "rgba(167,139,250,0.04)",
    optionBorder:     "rgba(167,139,250,0.1)",
    optionSelBg:      "rgba(167,139,250,0.12)",
    optionSelBorder:  "rgba(196,181,253,0.4)",
    optionIconBg:     "rgba(167,139,250,0.08)",
    optionIconSelBg:  "rgba(196,181,253,0.15)",
    optionIconColor:  "rgba(196,181,253,0.5)",
    optionIconSelColor: "#c4b5fd",
    optionLabel:      "rgba(233,213,255,0.85)",
    optionDesc:       "rgba(167,139,250,0.45)",
    radioBorder:      "rgba(167,139,250,0.25)",
    radioSel:         "#c4b5fd",
    radioDot:         "#1e1433",
    errorBg:          "rgba(244,114,182,0.08)",
    errorBorder:      "rgba(244,114,182,0.2)",
    errorColor:       "#f472b6",
    toggleBg:         "rgba(167,139,250,0.08)",
    toggleBorder:     "rgba(167,139,250,0.2)",
    toggleColor:      "rgba(167,139,250,0.7)",
    gridLine:         "rgba(167,139,250,0.04)",
    orb1:             "rgba(124,58,237,0.2)",
    orb2:             "rgba(244,114,182,0.12)",
  };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        .rs-page {
          font-family: 'Inter', sans-serif;
          min-height: 100vh; display: flex; flex-direction: column;
          align-items: center; justify-content: center;
          padding: 40px 16px;
          position: relative; overflow: hidden;
          transition: background 0.3s ease;
        }

        .rs-orb1 { position: fixed; border-radius: 50%; pointer-events: none; z-index: 0;
          width: 700px; height: 700px;
          top: -200px; left: -150px; animation: rsDrift1 9s ease-in-out infinite alternate; }
        .rs-orb2 { position: fixed; border-radius: 50%; pointer-events: none; z-index: 0;
          width: 500px; height: 500px;
          bottom: -120px; right: -100px; animation: rsDrift2 12s ease-in-out infinite alternate; }
        @keyframes rsDrift1 { from{transform:translate(0,0) scale(1)} to{transform:translate(40px,30px) scale(1.08)} }
        @keyframes rsDrift2 { from{transform:translate(0,0)} to{transform:translate(-30px,-20px) scale(1.1)} }

        .rs-grid { position: fixed; inset: 0; z-index: 1; pointer-events: none; }

        .rs-content { position: relative; z-index: 2; width: 100%; max-width: 720px; display: flex; flex-direction: column; align-items: center; }

        .rs-logo { display: flex; align-items: center; gap: 10px; margin-bottom: 28px; }
        .rs-logo-bars { display: flex; gap: 3px; align-items: flex-end; }
        .rs-logo-bars span { display: block; width: 4px; border-radius: 2px; }

        .rs-title { font-family: 'Inter', sans-serif; font-size: 26px; font-weight: 800; letter-spacing: -0.8px; margin-bottom: 6px; text-align: center; }
        .rs-title em { font-style: normal; background: linear-gradient(135deg, #c4b5fd, #f472b6, #67e8f9); background-size: 300%; -webkit-background-clip: text; -webkit-text-fill-color: transparent; animation: rsGrad 5s ease infinite; }
        @keyframes rsGrad { 0%{background-position:0% 50%} 50%{background-position:100% 50%} 100%{background-position:0% 50%} }
        .rs-subtitle { font-size: 13px; text-align: center; margin-bottom: 28px; line-height: 1.6; max-width: 400px; font-weight: 300; }

        .rs-layout { display: grid; grid-template-columns: 220px 1fr; gap: 16px; width: 100%; animation: rsUp 0.45s cubic-bezier(0.22,1,0.36,1) both; }
        @keyframes rsUp { from{opacity:0;transform:translateY(20px)} to{opacity:1;transform:translateY(0)} }

        .rs-card { border-radius: 20px; backdrop-filter: blur(20px); transition: background 0.3s ease, border-color 0.3s ease; }

        .rs-account-card { padding: 24px 20px; }
        .rs-account-label { font-size: 9.5px; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; margin-bottom: 16px; }

        .rs-avatar {
          width: 52px; height: 52px; border-radius: 50%;
          background: linear-gradient(135deg, #7c3aed, #c4b5fd);
          display: flex; align-items: center; justify-content: center;
          margin-bottom: 10px; overflow: hidden;
          font-family: 'Inter', sans-serif; font-size: 20px; font-weight: 800; color: white;
          border: 2px solid rgba(196,181,253,0.2);
        }
        .rs-avatar img { width: 100%; height: 100%; object-fit: cover; }

        .rs-full-name { font-family: 'Inter', sans-serif; font-size: 14px; font-weight: 800; margin-bottom: 8px; letter-spacing: -0.3px; }

        .rs-verified { display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px; border-radius: 20px; font-size: 10px; font-weight: 700; letter-spacing: 0.3px; }

        .rs-divider { height: 1px; margin: 16px 0; }

        .rs-info-block { margin-bottom: 12px; }
        .rs-info-block:last-child { margin-bottom: 0; }
        .rs-info-label { font-size: 9.5px; font-weight: 700; letter-spacing: 0.8px; text-transform: uppercase; margin-bottom: 3px; display: flex; align-items: center; gap: 5px; }
        .rs-info-value { font-size: 12.5px; font-weight: 600; }

        .rs-role-card { padding: 24px 22px; display: flex; flex-direction: column; }
        .rs-role-title { font-family: 'Inter', sans-serif; font-size: 15px; font-weight: 800; letter-spacing: -0.3px; margin-bottom: 3px; }
        .rs-role-subtitle { font-size: 11.5px; margin-bottom: 16px; line-height: 1.5; }

        .rs-options { display: flex; flex-direction: column; gap: 8px; flex: 1; }

        .rs-option { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: 12px; cursor: pointer; transition: all 0.2s; }

        .rs-option-icon { width: 34px; height: 34px; border-radius: 9px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: all 0.2s; }

        .rs-option-label { font-size: 13px; font-weight: 700; margin-bottom: 2px; }
        .rs-option-desc { font-size: 11px; line-height: 1.4; }

        .rs-radio { width: 15px; height: 15px; border-radius: 50%; border-width: 2px; border-style: solid; flex-shrink: 0; transition: all 0.2s; display: flex; align-items: center; justify-content: center; }

        .rs-error-wrap { height: 34px; margin-top: 10px; }
        .rs-error { display: flex; align-items: center; gap: 8px; padding: 7px 12px; border-radius: 9px; font-size: 11px; font-weight: 500; height: 100%; animation: rsFade 0.2s ease; }
        @keyframes rsFade { from{opacity:0;transform:translateY(-4px)} to{opacity:1;transform:translateY(0)} }

        .rs-btn { width: 100%; height: 46px; margin-top: 10px; display: flex; align-items: center; justify-content: center; gap: 8px; background: linear-gradient(135deg, #c4b5fd, #f472b6, #67e8f9); background-size: 300%; border: none; border-radius: 13px; font-family: 'Inter', sans-serif; font-size: 14px; font-weight: 700; cursor: pointer; transition: all 0.3s; box-shadow: 0 5px 18px rgba(196,181,253,0.2); animation: rsGrad 4s ease infinite; }
        .rs-btn:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(244,114,182,0.3); }
        .rs-btn:disabled { opacity: 0.5; cursor: not-allowed; animation: none; background: rgba(167,139,250,0.2); color: rgba(255,255,255,0.4); box-shadow: none; }

        .rs-spinner { width: 14px; height: 14px; border: 2px solid rgba(30,20,51,0.3); border-top-color: #1e1433; border-radius: 50%; animation: rsSpin 0.7s linear infinite; }
        @keyframes rsSpin { to{transform:rotate(360deg)} }

        .rs-theme-btn { position: fixed; top: 20px; right: 20px; z-index: 50; display: flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 10px; border: 1px solid; font-family: 'Inter', sans-serif; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.2s; }

        @media (max-width: 600px) {
          .rs-layout { grid-template-columns: 1fr; }
        }
      `}</style>

      <div className="rs-page" style={{ background: c.pageBg }}>

        {/* Theme toggle button */}
        <button
          className="rs-theme-btn"
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

        <div className="rs-orb1" style={{ background: `radial-gradient(circle, ${c.orb1} 0%, transparent 65%)` }} />
        <div className="rs-orb2" style={{ background: `radial-gradient(circle, ${c.orb2} 0%, transparent 65%)` }} />
        <div className="rs-grid" style={{ backgroundImage: `linear-gradient(${c.gridLine} 1px, transparent 1px), linear-gradient(90deg, ${c.gridLine} 1px, transparent 1px)`, backgroundSize: "48px 48px" }} />

        <div className="rs-content">

          <div className="rs-logo">
            <div className="rs-logo-bars">
              <span style={{height:'10px',background:'#7c3aed'}} />
              <span style={{height:'16px',background:'#a855f7'}} />
              <span style={{height:'24px',background:'#c4b5fd'}} />
              <span style={{height:'18px',background:'#f472b6'}} />
              <span style={{height:'12px',background:'#e879f9',opacity:0.7}} />
              <span style={{height:'7px',background:'#c4b5fd',opacity:0.4}} />
            </div>
            <span className="rs-logo-name" style={{ fontFamily: "'Inter', sans-serif", fontSize: "19px", fontWeight: 800, color: c.logoText, letterSpacing: "-0.3px" }}>
              <span style={{ color: c.logoAccent }}>Skill</span>Pulse
            </span>
          </div>

          <h1 className="rs-title" style={{ color: c.titleColor }}>Configure your <em>experience.</em></h1>
          <p className="rs-subtitle" style={{ color: c.subtitleColor }}>Help us tailor SkillPulse to your professional goals and workflow.</p>

          <div className="rs-layout">

            <div className="rs-card rs-account-card" style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}` }}>
              <div className="rs-account-label" style={{ color: c.accountLabel }}>Linked Account</div>

              <div className="rs-avatar">
                {user?.avatar_url
                  ? <img src={user.avatar_url} alt="avatar" />
                  : (user?.username?.[0] ?? "?").toUpperCase()
                }
              </div>

              <div className="rs-full-name" style={{ color: c.fullNameColor }}>{user?.full_name ?? "Loading..."}</div>

              <div className="rs-verified" style={{ background: c.verifiedBg, border: `1px solid ${c.verifiedBorder}`, color: c.verifiedColor }}>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>
                </svg>
                GitHub Verified
              </div>

              <div className="rs-divider" style={{ background: c.dividerColor }} />

              <div className="rs-info-block">
                <div className="rs-info-label" style={{ color: c.infoLabel }}>
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>
                  Username
                </div>
                <div className="rs-info-value" style={{ color: c.infoValue }}>{user?.username ?? "—"}</div>
              </div>

              <div className="rs-info-block">
                <div className="rs-info-label" style={{ color: c.infoLabel }}>
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
                  Email
                </div>
                <div className="rs-info-value" style={{ color: c.infoValue }}>{user?.work_email ?? "—"}</div>
              </div>
            </div>

            <div className="rs-card rs-role-card" style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}` }}>
              <div className="rs-role-title" style={{ color: c.roleTitle }}>Select your primary role</div>
              <div className="rs-role-subtitle" style={{ color: c.roleSubtitle }}>This defines your dashboard view and can be changed later.</div>

              <div className="rs-options">
                {roles.map(r => {
                  const isSel = selected === r.value;
                  return (
                    <div key={r.value} style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                      <div
                        className="rs-option"
                        style={{
                          background: isSel ? c.optionSelBg : c.optionBg,
                          border: `1.5px solid ${isSel ? c.optionSelBorder : c.optionBorder}`,
                        }}
                        onClick={() => setSelected(r.value)}
                      >
                        <div className="rs-option-icon" style={{ background: isSel ? c.optionIconSelBg : c.optionIconBg, color: isSel ? c.optionIconSelColor : c.optionIconColor }}>
                          {r.icon}
                        </div>
                        <div style={{ flex: 1 }}>
                          <div className="rs-option-label" style={{ color: c.optionLabel }}>{r.label}</div>
                          <div className="rs-option-desc" style={{ color: c.optionDesc }}>{r.desc}</div>
                        </div>
                        <div className="rs-radio" style={{ borderColor: isSel ? c.radioSel : c.radioBorder, background: isSel ? c.radioSel : "transparent" }}>
                          {isSel && <div style={{ width: "5px", height: "5px", borderRadius: "50%", background: c.radioDot }} />}
                        </div>
                      </div>

                      {selected === "developer" && r.value === "developer" && (
                        <div style={{ display: "flex", gap: "8px", marginLeft: "46px" }}>
                          {specializations.map(s => {
                            const specSel = selectedSpec === s.value;
                            return (
                              <div
                                key={s.value}
                                className="rs-option"
                                style={{
                                  flex: 1, padding: "8px 10px", justifyContent: "center",
                                  background: specSel ? c.optionSelBg : c.optionBg,
                                  border: `1.5px solid ${specSel ? c.optionSelBorder : c.optionBorder}`,
                                }}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setSelectedSpec(s.value);
                                }}
                              >
                                <div className="rs-option-label" style={{ fontSize: "11.5px", marginBottom: 0, color: c.optionLabel }}>
                                  {s.label}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              <div className="rs-error-wrap">
                {error && (
                  <div className="rs-error" style={{ background: c.errorBg, border: `1px solid ${c.errorBorder}`, color: c.errorColor }}>
                    <span>⚠</span> {error}
                  </div>
                )}
              </div>

              <button className="rs-btn" onClick={handleContinue} disabled={loading || !selected} style={{ color: isLight ? "#26215c" : "#1e1433" }}>
                {loading
                  ? <><div className="rs-spinner" /> Saving...</>
                  : <>Continue to Dashboard →</>
                }
              </button>
            </div>

          </div>
        </div>
      </div>
    </>
  );
};

export default RoleSelection;