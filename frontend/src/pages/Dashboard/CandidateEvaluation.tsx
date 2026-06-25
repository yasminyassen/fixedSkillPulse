import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../../api/auth";

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
  reliability_rating: string | null;
  maintainability_rating: string | null;
  technical_debt_minutes: number | null;
  lines_of_code: number | null;
  security: number;
  repo_count: number;
  contribution_count: number;
  run_id: number;
}

const scoreColor = (score: number | null) => {
  if (score === null) return "#94a3b8";
  if (score >= 80) return "#34d399";
  if (score >= 60) return "#fbbf24";
  return "#f87171";
};

const fmt = (value: number | string | null | undefined, suffix = "") =>
  value === null || value === undefined ? "Unavailable" : `${value}${suffix}`;

export default function CandidateEvaluation() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<CandidateRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    api.get<CandidateRow[]>("/analysis/recruiter/candidates")
      .then((res) => setRows(res.data || []))
      .catch((err) => setError(err?.response?.data?.detail || "Unable to load candidates."))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows
      .filter((row) => !needle || row.candidate_name.toLowerCase().includes(needle) || row.github_login.toLowerCase().includes(needle))
      .sort((a, b) => (b.skill_score ?? -1) - (a.skill_score ?? -1));
  }, [rows, query]);

  const readyScores = rows.map((row) => row.skill_score).filter((score): score is number => score !== null);
  const average = readyScores.length ? Math.round(readyScores.reduce((sum, score) => sum + score, 0) / readyScores.length) : null;

  return (
    <div style={{ padding: 24, color: "var(--text-primary)" }}>
      <h1 style={{ margin: 0, fontFamily: "'Syne',sans-serif" }}>Candidate Evaluation</h1>
      <p style={{ color: "var(--text-muted)", marginTop: 6 }}>Candidate ranking uses the Skill Score Engine: 70% Sonar health and 30% security.</p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, margin: "22px 0" }}>
        <Metric label="Candidates" value={rows.length} />
        <Metric label="Average Overall Score" value={fmt(average)} color={scoreColor(average)} />
        <Metric label="Score Unavailable" value={rows.filter((row) => row.skill_score === null).length} />
      </div>

      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search candidates"
        style={{ width: "100%", maxWidth: 360, padding: "10px 12px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--bg-card)", color: "var(--text-primary)", marginBottom: 16 }}
      />

      {loading && <p style={{ color: "var(--text-muted)" }}>Loading candidates...</p>}
      {error && <p style={{ color: "#f87171" }}>{error}</p>}

      {!loading && !error && (
        <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: 8, background: "var(--bg-card)" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 920 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--text-muted)", fontSize: 12 }}>
                {["Candidate", "Overall Score", "Score Level", "Bugs", "Code Smells", "Coverage", "Duplication", "Cognitive Complexity", "LOC", "Action"].map((header) => (
                  <th key={header} style={{ padding: 12, borderBottom: "1px solid var(--border)" }}>{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr key={row.run_id} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: 12, fontWeight: 700 }}>{row.candidate_name}</td>
                  <td style={{ padding: 12, color: scoreColor(row.skill_score), fontWeight: 800 }}>{fmt(row.skill_score)}</td>
                  <td style={{ padding: 12 }}>{row.skill_score_level || "Unavailable"}</td>
                  <td style={{ padding: 12 }}>{fmt(row.bugs)}</td>
                  <td style={{ padding: 12 }}>{fmt(row.code_smells)}</td>
                  <td style={{ padding: 12 }}>{fmt(row.coverage, row.coverage === null ? "" : "%")}</td>
                  <td style={{ padding: 12 }}>{fmt(row.duplication_percentage, row.duplication_percentage === null ? "" : "%")}</td>
                  <td style={{ padding: 12 }}>{fmt(row.cognitive_complexity)}</td>
                  <td style={{ padding: 12 }}>{fmt(row.lines_of_code)}</td>
                  <td style={{ padding: 12 }}>
                    <button onClick={() => navigate(`/analysis/${row.run_id}`)} style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid rgba(99,102,241,0.3)", background: "rgba(99,102,241,0.1)", color: "#818cf8", cursor: "pointer" }}>
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
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
