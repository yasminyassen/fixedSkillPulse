import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../../api/auth";

interface ProfileData {
  talent_overview: {
    candidates_evaluated: number;
    high_priority: number;
    profiles_shortlisted: number;
  };
  recent_activity: Array<{
    candidate_name: string;
    repo_name: string;
    skill_score: number | null;
    skill_score_level: string;
    sonar_health_score: number | null;
    sonar_state: string;
    quality_gate: string | null;
    run_id: number;
    completed_at: string | null;
  }>;
}

interface CandidateRow {
  candidate_name: string;
  github_login: string;
  skill_score: number | null;
  skill_score_level: string;
  sonar_health_score: number | null;
  sonar_state: string;
  quality_gate: string | null;
  bugs: number | null;
  code_smells: number | null;
  coverage: number | null;
  duplication_percentage: number | null;
  cognitive_complexity: number | null;
  lines_of_code: number | null;
  run_id: number;
}

const color = (score: number | null) => score === null ? "#94a3b8" : score >= 80 ? "#34d399" : score >= 60 ? "#fbbf24" : "#f87171";
const fmt = (value: number | string | null | undefined, suffix = "") => value === null || value === undefined ? "Unavailable" : `${value}${suffix}`;

export default function RecruiterDashboard() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [candidates, setCandidates] = useState<CandidateRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get<ProfileData>("/recruiter/profile-dashboard"),
      api.get<CandidateRow[]>("/analysis/recruiter/candidates"),
    ])
      .then(([profileRes, candidatesRes]) => {
        setProfile(profileRes.data);
        setCandidates(candidatesRes.data || []);
      })
      .finally(() => setLoading(false));
  }, []);

  const ranked = useMemo(
    () => candidates.slice().sort((a, b) => (b.skill_score ?? -1) - (a.skill_score ?? -1)),
    [candidates],
  );

  return (
    <div style={{ padding: 24, color: "var(--text-primary)" }}>
      <h1 style={{ margin: 0, fontFamily: "'Syne',sans-serif" }}>Recruiter Dashboard</h1>
      <p style={{ color: "var(--text-muted)", marginTop: 6 }}>Candidate ranking uses the Skill Score Engine: 70% Sonar health and 30% security.</p>

      {loading && <p style={{ color: "var(--text-muted)" }}>Loading recruiter dashboard...</p>}

      {profile && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, margin: "22px 0" }}>
          <Metric label="Candidates" value={profile.talent_overview.candidates_evaluated} />
          <Metric label="High Priority" value={profile.talent_overview.high_priority} />
          <Metric label="Shortlisted" value={profile.talent_overview.profiles_shortlisted} />
          <Metric label="Score Unavailable" value={candidates.filter((candidate) => candidate.skill_score === null).length} />
        </div>
      )}

      <section style={{ padding: 18, border: "1px solid var(--border)", borderRadius: 8, background: "var(--bg-card)", marginBottom: 18 }}>
        <h2 style={{ marginTop: 0, fontFamily: "'Syne',sans-serif" }}>Candidate Ranking</h2>
        {!ranked.length && <p style={{ color: "var(--text-muted)" }}>No completed candidate analyses yet.</p>}
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 820 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--text-muted)", fontSize: 12 }}>
                {["Candidate", "Overall Score", "Score Level", "Bugs", "Code Smells", "Coverage", "Duplication", "LOC", "Action"].map((header) => (
                  <th key={header} style={{ padding: 10, borderBottom: "1px solid var(--border)" }}>{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ranked.map((candidate) => (
                <tr key={candidate.run_id} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: 10, fontWeight: 700 }}>{candidate.candidate_name}</td>
                  <td style={{ padding: 10, color: color(candidate.skill_score), fontWeight: 800 }}>{fmt(candidate.skill_score)}</td>
                  <td style={{ padding: 10 }}>{candidate.skill_score_level || "Unavailable"}</td>
                  <td style={{ padding: 10 }}>{fmt(candidate.bugs)}</td>
                  <td style={{ padding: 10 }}>{fmt(candidate.code_smells)}</td>
                  <td style={{ padding: 10 }}>{fmt(candidate.coverage, candidate.coverage == null ? "" : "%")}</td>
                  <td style={{ padding: 10 }}>{fmt(candidate.duplication_percentage, candidate.duplication_percentage == null ? "" : "%")}</td>
                  <td style={{ padding: 10 }}>{fmt(candidate.lines_of_code)}</td>
                  <td style={{ padding: 10 }}>
                    <button onClick={() => navigate(`/analysis/${candidate.run_id}`)} style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid rgba(99,102,241,0.3)", background: "rgba(99,102,241,0.1)", color: "#818cf8", cursor: "pointer" }}>
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section style={{ padding: 18, border: "1px solid var(--border)", borderRadius: 8, background: "var(--bg-card)" }}>
        <h2 style={{ marginTop: 0, fontFamily: "'Syne',sans-serif" }}>Recent Activity</h2>
        {!profile?.recent_activity.length && <p style={{ color: "var(--text-muted)" }}>No recent candidate activity.</p>}
        {profile?.recent_activity.map((activity) => (
          <button key={activity.run_id} onClick={() => navigate(`/analysis/${activity.run_id}`)} style={{ display: "block", width: "100%", textAlign: "left", padding: "10px 0", border: 0, borderTop: "1px solid var(--border)", background: "transparent", color: "var(--text-primary)", cursor: "pointer" }}>
            <strong>{activity.candidate_name}</strong> · {activity.repo_name}
            <span style={{ marginLeft: 10, color: color(activity.skill_score), fontWeight: 800 }}>{fmt(activity.skill_score)} · {activity.skill_score_level}</span>
          </button>
        ))}
      </section>
    </div>
  );
}

function Metric({ label, value, color = "var(--text-primary)" }: { label: string; value: string | number; color?: string }) {
  return (
    <div style={{ padding: 16, borderRadius: 8, border: "1px solid var(--border)", background: "var(--bg-card)" }}>
      <div style={{ fontSize: 12, color: "var(--text-muted)", textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 900, color, marginTop: 6 }}>{value}</div>
    </div>
  );
}
