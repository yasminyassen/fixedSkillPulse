import { createContext, useContext, useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";

// ─── Theme Context ─────────────────────────────────────────────────────────

type Theme = "dark" | "light";

const ThemeContext = createContext<{ theme: Theme; toggle: () => void }>({
  theme: "dark",
  toggle: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem("sp_theme") as Theme) || "dark"
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("sp_theme", theme);
  }, [theme]);

  const toggle = () => setTheme(t => (t === "dark" ? "light" : "dark"));

  return (
    <ThemeContext.Provider value={{ theme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export const useTheme = () => useContext(ThemeContext);

// ─── Types ─────────────────────────────────────────────────────────────────

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
}

interface DashboardLayoutProps {
  children: React.ReactNode;
}

// ─── Icons ─────────────────────────────────────────────────────────────────

const icons = {
  repo: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/>
      <path d="M9 18c-4.51 2-5-2-7-2"/>
    </svg>
  ),
  skills: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/>
    </svg>
  ),
  security: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  requirements: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>
    </svg>
  ),
  learning: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
    </svg>
  ),
  profile: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
    </svg>
  ),
  team: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
    </svg>
  ),
  candidate: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>
    </svg>
  ),
  signout: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
    </svg>
  ),
  sun: (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5"/>
      <line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
      <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
    </svg>
  ),
  moon: (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </svg>
  ),
};

// ─── Nav config ────────────────────────────────────────────────────────────

const navByRole: Record<string, NavItem[]> = {
  developer: [
    { label: "Repository Analysis", path: "/dashboard/developer/analysis",    icon: icons.repo         },
    { label: "Skills",              path: "/dashboard/developer/skills",       icon: icons.skills       },
    { label: "Security",            path: "/dashboard/developer/security",     icon: icons.security     },
    { label: "Requirements",        path: "/dashboard/developer/requirements", icon: icons.requirements },
    { label: "Learning",            path: "/dashboard/developer/learning",     icon: icons.learning     },
    { label: "Profile",             path: "/dashboard/developer/profile",      icon: icons.profile      },
  ],
  manager: [
    { label: "Repository Analysis", path: "/dashboard/manager/analysis",      icon: icons.repo         },
    { label: "Security",            path: "/dashboard/manager/security",       icon: icons.security     },
    { label: "Requirements",        path: "/dashboard/manager/requirements",   icon: icons.requirements },
    { label: "Profile",             path: "/dashboard/manager/profile",        icon: icons.profile      },
    { label: "Team Dashboard",      path: "/dashboard/manager/team",           icon: icons.team         },
  ],
  recruiter: [
    { label: "Repository Analysis", path: "/dashboard/recruiter/analysis",    icon: icons.repo         },
    { label: "Profile",             path: "/dashboard/recruiter/profile",      icon: icons.profile      },
    { label: "Candidate View",      path: "/dashboard/recruiter/candidates",   icon: icons.candidate    },
  ],
};

const roleColors: Record<string, string> = { developer: "#6366f1", manager: "#8b5cf6", recruiter: "#a855f7" };
const roleLabels: Record<string, string> = { developer: "Developer", manager: "Manager", recruiter: "Recruiter" };

// ─── Layout ────────────────────────────────────────────────────────────────

function DashboardLayoutInner({ children }: DashboardLayoutProps) {
  const navigate  = useNavigate();
  const location  = useLocation();
  const { theme, toggle } = useTheme();

  const role      = localStorage.getItem("role") || "developer";
  const fullName  = localStorage.getItem("full_name") || "User";
  const initials  = fullName.split(" ").map((n: string) => n[0]).join("").toUpperCase().slice(0, 2);
  const [collapsed, setCollapsed] = useState(false);

  const navItems    = navByRole[role] || navByRole.developer;
  const accentColor = roleColors[role];
  const isLight     = theme === "light";

  // Sidebar width as a number so we can use it for the margin offset
  const sidebarWidth = collapsed ? 72 : 240;

  const handleSignOut = () => { localStorage.clear(); navigate("/login"); };
  const isActive = (path: string) => location.pathname === path;

  return (
    <div style={{
      display: "flex",
      minHeight: "100vh",
      background: "var(--bg-base)",
      fontFamily: "'DM Sans', system-ui, sans-serif",
      transition: "background 0.3s ease",
    }}>

      {/* ── Sidebar (fixed) ── */}
      <aside style={{
        position: "fixed",
        top: 0,
        left: 0,
        width: `${sidebarWidth}px`,
        height: "100vh",
        background: "var(--bg-sidebar)",
        borderRight: "1px solid var(--border-sidebar)",
        display: "flex",
        flexDirection: "column",
        transition: "width 0.25s cubic-bezier(0.4,0,0.2,1), background 0.3s ease, border-color 0.3s ease",
        zIndex: 100,
        overflow: "hidden",
        backdropFilter: "blur(20px)",
      }}>

        {/* Logo row */}
        <div style={{
          padding: collapsed ? "20px 0" : "20px",
          display: "flex", alignItems: "center", gap: "10px",
          borderBottom: "1px solid var(--border-sidebar)",
          justifyContent: collapsed ? "center" : "space-between",
          minHeight: "65px",
          flexShrink: 0,
        }}>
          {!collapsed && (
            <div style={{ display: "flex", alignItems: "center", gap: "9px" }}>
              <div style={{ display: "flex", gap: "2.5px", alignItems: "flex-end" }}>
                {[10, 16, 24, 18, 12].map((h, i) => (
                  <span key={i} style={{
                    display: "block", width: "3.5px", height: `${h}px`, borderRadius: "2px",
                    background: i < 3 ? accentColor : i === 3 ? "#ec4899" : "#c4b5fd",
                    opacity: i === 4 ? 0.6 : 1,
                  }} />
                ))}
              </div>
              <span style={{ fontFamily: "'Syne', sans-serif", fontSize: "16px", fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-0.3px", whiteSpace: "nowrap" }}>
                <span style={{ color: accentColor }}>Skill</span>Pulse
              </span>
            </div>
          )}
          {collapsed && (
            <div style={{ display: "flex", gap: "2px", alignItems: "flex-end" }}>
              {[6, 10, 14].map((h, i) => (
                <span key={i} style={{ display: "block", width: "3px", height: `${h}px`, borderRadius: "2px", background: accentColor }} />
              ))}
            </div>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: "4px", display: "flex", alignItems: "center", justifyContent: "center", borderRadius: "6px", transition: "color 0.2s", flexShrink: 0 }}
            onMouseEnter={e => (e.currentTarget.style.color = "var(--text-primary)")}
            onMouseLeave={e => (e.currentTarget.style.color = "var(--text-muted)")}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              {collapsed ? <path d="M9 18l6-6-6-6"/> : <path d="M15 18l-6-6 6-6"/>}
            </svg>
          </button>
        </div>

        {/* Role badge */}
        {!collapsed && (
          <div style={{ padding: "12px 20px 8px", flexShrink: 0 }}>
            <div style={{ display: "inline-flex", alignItems: "center", gap: "6px", background: `${accentColor}15`, border: `1px solid ${accentColor}30`, borderRadius: "20px", padding: "4px 10px" }}>
              <div style={{ width: "6px", height: "6px", borderRadius: "50%", background: accentColor }} />
              <span style={{ fontSize: "11px", fontWeight: 600, color: accentColor, letterSpacing: "0.5px" }}>{roleLabels[role]}</span>
            </div>
          </div>
        )}

        {/* Nav — scrollable if needed */}
        <nav style={{ flex: 1, padding: collapsed ? "8px 10px" : "8px 12px", display: "flex", flexDirection: "column", gap: "2px", overflowY: "auto" }}>
          {navItems.map(item => {
            const active = isActive(item.path);
            return (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                title={collapsed ? item.label : undefined}
                style={{
                  display: "flex", alignItems: "center", gap: "10px",
                  padding: collapsed ? "10px" : "9px 12px",
                  justifyContent: collapsed ? "center" : "flex-start",
                  borderRadius: "10px", border: "none", cursor: "pointer",
                  background: active ? `${accentColor}18` : "transparent",
                  color: active ? "var(--text-nav-active)" : "var(--text-nav)",
                  fontSize: "13.5px", fontWeight: active ? 600 : 400,
                  transition: "all 0.15s",
                  position: "relative", width: "100%", textAlign: "left", whiteSpace: "nowrap",
                  flexShrink: 0,
                }}
                onMouseEnter={e => { if (!active) { e.currentTarget.style.background = "var(--bg-nav-hover)"; e.currentTarget.style.color = "var(--text-secondary)"; } }}
                onMouseLeave={e => { if (!active) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-nav)"; } }}
              >
                {active && (
                  <span style={{ position: "absolute", left: 0, top: "50%", transform: "translateY(-50%)", width: "3px", height: "18px", borderRadius: "0 3px 3px 0", background: accentColor }} />
                )}
                <span style={{ color: active ? accentColor : "inherit", flexShrink: 0 }}>{item.icon}</span>
                {!collapsed && <span>{item.label}</span>}
              </button>
            );
          })}
        </nav>

        {/* Bottom: theme toggle + user + sign out */}
        <div style={{ padding: collapsed ? "12px 10px" : "12px", borderTop: "1px solid var(--border-sidebar)", display: "flex", flexDirection: "column", gap: "6px", flexShrink: 0 }}>

          {/* Theme toggle */}
          <button
            onClick={toggle}
            title={isLight ? "Switch to Dark Mode" : "Switch to Light Mode"}
            style={{
              display: "flex", alignItems: "center", gap: "8px",
              padding: collapsed ? "10px" : "8px 10px",
              justifyContent: collapsed ? "center" : "flex-start",
              borderRadius: "8px", border: "1px solid var(--border)",
              cursor: "pointer",
              background: isLight ? "rgba(99,102,241,0.08)" : "rgba(255,255,255,0.04)",
              color: isLight ? accentColor : "var(--text-muted)",
              fontSize: "12.5px", fontWeight: 500,
              transition: "all 0.2s", width: "100%",
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = accentColor; e.currentTarget.style.color = accentColor; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.color = isLight ? accentColor : "var(--text-muted)"; }}
          >
            {isLight ? icons.moon : icons.sun}
            {!collapsed && <span>{isLight ? "Dark Mode" : "Light Mode"}</span>}
          </button>

          {/* User info */}
          {!collapsed && (
            <div style={{ display: "flex", alignItems: "center", gap: "10px", padding: "8px 10px", borderRadius: "10px", background: "var(--bg-user)" }}>
              <div style={{ width: "32px", height: "32px", borderRadius: "50%", flexShrink: 0, background: `linear-gradient(135deg, ${accentColor}, #ec4899)`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: "12px", fontWeight: 700, color: "white" }}>
                {initials}
              </div>
              <div style={{ overflow: "hidden" }}>
                <div style={{ fontSize: "12.5px", fontWeight: 600, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{fullName}</div>
                <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>{roleLabels[role]}</div>
              </div>
            </div>
          )}

          {/* Sign out */}
          <button
            onClick={handleSignOut}
            title={collapsed ? "Sign Out" : undefined}
            style={{
              display: "flex", alignItems: "center", gap: "8px",
              padding: collapsed ? "10px" : "8px 10px",
              justifyContent: collapsed ? "center" : "flex-start",
              borderRadius: "8px", border: "none", cursor: "pointer",
              background: "transparent", color: "var(--text-muted)",
              fontSize: "13px", transition: "all 0.15s", width: "100%",
            }}
            onMouseEnter={e => { e.currentTarget.style.background = "rgba(239,68,68,0.1)"; e.currentTarget.style.color = "#f87171"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-muted)"; }}
          >
            {icons.signout}
            {!collapsed && <span>Sign Out</span>}
          </button>
        </div>
      </aside>

      {/* ── Main — offset by sidebar width ── */}
      <main style={{
        marginLeft: `${sidebarWidth}px`,
        flex: 1,
        minHeight: "100vh",
        overflowY: "auto",
        transition: "margin-left 0.25s cubic-bezier(0.4,0,0.2,1)",
      }}>
        {children}
      </main>
    </div>
  );
}

// ─── Export with provider ──────────────────────────────────────────────────

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  return (
    <ThemeProvider>
      <DashboardLayoutInner>{children}</DashboardLayoutInner>
    </ThemeProvider>
  );
}
