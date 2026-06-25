import React, { useEffect, useState } from "react";

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

const NotFound: React.FC = () => {
  const { toggle, isLight } = useAuthTheme();

   const c = isLight ? {
    pageBg:        "#f5f3ff",
    logoText:      "#3c3489",
    logoAccent:    "#7c3aed",
    titleColor:    "#26215c",
    subColor:      "#534ab7",
    ghostBorder:   "rgba(124,58,237,0.25)",
    ghostColor:    "rgba(83,74,183,0.7)",
    ghostHoverBorder: "rgba(124,58,237,0.45)",
    ghostHoverColor:  "#7c3aed",
    ghostHoverBg:     "rgba(124,58,237,0.07)",
    toggleBg:      "rgba(124,58,237,0.1)",
    toggleBorder:  "rgba(124,58,237,0.25)",
    toggleColor:   "#7c3aed",
    gridLine:      "rgba(124,58,237,0.04)",
    orb1:          "rgba(124,58,237,0.12)",
    orb2:          "rgba(244,114,182,0.08)",
    numberShadow:  "rgba(124,58,237,0.18)",
  } : {
    pageBg:        "#0f0c1a",
    logoText:      "white",
    logoAccent:    "#c4b5fd",
    titleColor:    "white",
    subColor:      "rgba(196,181,253,0.45)",
    ghostBorder:   "rgba(167,139,250,0.2)",
    ghostColor:    "rgba(196,181,253,0.6)",
    ghostHoverBorder: "rgba(196,181,253,0.4)",
    ghostHoverColor:  "#c4b5fd",
    ghostHoverBg:     "rgba(167,139,250,0.07)",
    toggleBg:      "rgba(167,139,250,0.08)",
    toggleBorder:  "rgba(167,139,250,0.2)",
    toggleColor:   "rgba(167,139,250,0.7)",
    gridLine:      "rgba(167,139,250,0.04)",
    orb1:          "rgba(124,58,237,0.2)",
    orb2:          "rgba(244,114,182,0.12)",
    numberShadow:  "rgba(196,181,253,0.25)",
  };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500;600&display=swap');
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        .nf-page {
          font-family: 'DM Sans', sans-serif;
          min-height: 100vh; display: flex; flex-direction: column;
          align-items: center; justify-content: center;
          position: relative; overflow: hidden;
          padding: 24px;
          transition: background 0.3s ease;
        }

        .nf-orb1 { position: fixed; border-radius: 50%; pointer-events: none; z-index: 0;
          width: 700px; height: 700px;
          top: -200px; left: -150px; animation: nfDrift1 9s ease-in-out infinite alternate; }
        .nf-orb2 { position: fixed; border-radius: 50%; pointer-events: none; z-index: 0;
          width: 500px; height: 500px;
          bottom: -120px; right: -100px; animation: nfDrift2 12s ease-in-out infinite alternate; }
        @keyframes nfDrift1 { from{transform:translate(0,0)} to{transform:translate(40px,30px) scale(1.08)} }
        @keyframes nfDrift2 { from{transform:translate(0,0)} to{transform:translate(-30px,-20px) scale(1.1)} }

        .nf-grid { position: fixed; inset: 0; z-index: 1; pointer-events: none; }

        .nf-content { position: relative; z-index: 2; text-align: center; max-width: 480px; }

        .nf-logo { display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 48px; }
        .nf-logo-bars { display: flex; gap: 3px; align-items: flex-end; }
        .nf-logo-bars span { display: block; width: 4px; border-radius: 2px; }
        .nf-logo-name { font-family: 'Syne', sans-serif; font-size: 19px; font-weight: 800; letter-spacing: -0.3px; }

        .nf-number {
          font-family: 'Syne', sans-serif; font-size: 120px; font-weight: 800;
          line-height: 1; letter-spacing: -6px; margin-bottom: 8px;
          background: linear-gradient(135deg, #c4b5fd, #f472b6, #67e8f9, #a78bfa, #c4b5fd);
          background-size: 300%; -webkit-background-clip: text; -webkit-text-fill-color: transparent;
          animation: nfGrad 5s ease infinite, nfFloat 4s ease-in-out infinite;
        }
        @keyframes nfGrad { 0%{background-position:0% 50%} 50%{background-position:100% 50%} 100%{background-position:0% 50%} }
        @keyframes nfFloat { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-8px)} }

        .nf-line { width: 60px; height: 2px; background: linear-gradient(90deg, #c4b5fd, #f472b6); border-radius: 2px; margin: 0 auto 24px; }

        .nf-title { font-family: 'Syne', sans-serif; font-size: 22px; font-weight: 800; letter-spacing: -0.5px; margin-bottom: 10px; }
        .nf-sub { font-size: 13.5px; font-weight: 300; line-height: 1.7; margin-bottom: 36px; }

        .nf-actions { display: flex; align-items: center; justify-content: center; gap: 12px; flex-wrap: wrap; }

        .nf-btn-primary {
          height: 46px; padding: 0 28px; display: flex; align-items: center; gap: 8px;
          background: linear-gradient(135deg, #7c3aed, #a855f7, #ec4899);
          background-size: 200%; border: none; border-radius: 13px;
          font-family: 'DM Sans', sans-serif; font-size: 14px; font-weight: 600; color: white;
          cursor: pointer; transition: all 0.3s; box-shadow: 0 6px 22px rgba(124,58,237,0.3);
          text-decoration: none;
        }
        .nf-btn-primary:hover { transform: translateY(-2px); box-shadow: 0 10px 30px rgba(168,85,247,0.4); }

        .nf-btn-ghost {
          height: 46px; padding: 0 28px; display: flex; align-items: center; gap: 8px;
          background: transparent; border: 1.5px solid;
          border-radius: 13px; font-family: 'DM Sans', sans-serif; font-size: 14px;
          font-weight: 600;
          cursor: pointer; transition: all 0.25s; text-decoration: none;
        }

        .nf-theme-btn { position: fixed; top: 20px; right: 20px; z-index: 50; display: flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 10px; border: 1px solid; font-family: 'DM Sans', sans-serif; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
      `}</style>

      <div className="nf-page" style={{ background: c.pageBg }}>

        {/* Theme toggle button */}
        <button
          className="nf-theme-btn"
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

        <div className="nf-orb1" style={{ background: `radial-gradient(circle, ${c.orb1} 0%, transparent 65%)` }} />
        <div className="nf-orb2" style={{ background: `radial-gradient(circle, ${c.orb2} 0%, transparent 65%)` }} />
        <div className="nf-grid" style={{ backgroundImage: `linear-gradient(${c.gridLine} 1px, transparent 1px), linear-gradient(90deg, ${c.gridLine} 1px, transparent 1px)`, backgroundSize: "48px 48px" }} />

        <div className="nf-content">

          {/* Logo */}
          <div className="nf-logo">
            <div className="nf-logo-bars">
              <span style={{height:'10px',background:'#7c3aed'}} />
              <span style={{height:'16px',background:'#a855f7'}} />
              <span style={{height:'24px',background:'#c4b5fd'}} />
              <span style={{height:'18px',background:'#f472b6'}} />
              <span style={{height:'12px',background:'#e879f9',opacity:0.7}} />
              <span style={{height:'7px',background:'#c4b5fd',opacity:0.4}} />
            </div>
            <span className="nf-logo-name" style={{ color: c.logoText }}>
              <span style={{ color: c.logoAccent }}>Skill</span>Pulse
            </span>
          </div>

          {/* 404 */}
          <div className="nf-number" style={{ filter: `drop-shadow(0 0 40px ${c.numberShadow})` }}>404</div>
          <div className="nf-line" />

          <div className="nf-title" style={{ color: c.titleColor }}>Page not found</div>
          <p className="nf-sub" style={{ color: c.subColor }}>
            Looks like this page took an unexpected detour.<br/>
            Let's get you back on track.
          </p>

          <div className="nf-actions">
            <a className="nf-btn-primary" href="/" onClick={e => { e.preventDefault(); window.location.href = '/'; }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>
              </svg>
              Back to Home
            </a>
            <a
              className="nf-btn-ghost"
              href="/register"
              style={{ borderColor: c.ghostBorder, color: c.ghostColor }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = c.ghostHoverBorder; e.currentTarget.style.color = c.ghostHoverColor; e.currentTarget.style.background = c.ghostHoverBg; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = c.ghostBorder; e.currentTarget.style.color = c.ghostColor; e.currentTarget.style.background = "transparent"; }}
              onClick={e => { e.preventDefault(); window.location.href = '/register'; }}
            >
              Create Account
            </a>
          </div>

        </div>
      </div>
    </>
  );
};

export default NotFound;