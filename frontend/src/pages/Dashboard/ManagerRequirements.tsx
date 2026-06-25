import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Eye, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import DashboardLayout from "../DashboardLayout";
import api from "../../api/auth";
import { ExtractedRequirementsReviewModal, PrdUploadDropZone } from "../../components/requirements/PrdWorkflow";

const role = localStorage.getItem("role") || "developer";
const accent = role === "manager" ? "#8b5cf6" : role === "recruiter" ? "#a855f7" : "#6366f1";

const TYPE_CFG: Record<string, { label: string; color: string; bg: string }> = {
  backend: { label: "Backend", color: "#a78bfa", bg: "rgba(139,92,246,0.15)" },
  frontend: { label: "Frontend", color: "#60a5fa", bg: "rgba(59,130,246,0.15)" },
  qa: { label: "QA", color: "#fbbf24", bg: "rgba(245,158,11,0.15)" },
};

const COVERAGE_CFG: Record<string, { label: string; color: string; bg: string }> = {
  implemented: { label: "Implemented", color: "#34d399", bg: "rgba(52,211,153,0.12)" },
  partially_implemented: { label: "Partial", color: "#fbbf24", bg: "rgba(251,191,36,0.12)" },
  not_implemented: { label: "Missing", color: "#f87171", bg: "rgba(248,113,113,0.12)" },
  COVERED: { label: "Covered", color: "#34d399", bg: "rgba(52,211,153,0.12)" },
  PARTIALLY_COVERED: { label: "Partial", color: "#fbbf24", bg: "rgba(251,191,36,0.12)" },
  NOT_COVERED: { label: "Missing", color: "#f87171", bg: "rgba(248,113,113,0.12)" },
};

type Contributor = { id: number; username: string; full_name: string; email?: string; specialization?: string | null };
type RepoRow = { repo_id: number; repo_name: string; branch: string; status: string; analysis_id: number };
type Task = {
  id?: number;
  task_id?: number;
  story_id: number;
  description: string;
  type: string;
  status: string;
  assigned_to?: number | null;
  assigned_name?: string | null;
  ac_ids: number[];
  due_date?: string | null;
};
type Story = {
  id?: number;
  story_id?: number;
  story_code: string;
  title: string;
  description: string;
  priority: string;
  acceptance_criteria: any[];
  technical_tasks?: Task[];
  tasks?: Task[];
  coverage_percent?: number;
  visible_coverage_percent?: number;
  status?: string;
};

type DraftTask = {
  description: string;
  type: string;
  status: string;
  assigned_to: number | null;
  ac_ids: number[];
  ac_ids_text: string;
};

type DraftStory = {
  title: string;
  description: string;
  priority: string;
  acceptance_criteria: { id: number; text: string }[];
  technical_tasks: DraftTask[];
};

const pct = (value?: number | null) => `${Math.round(Number(value || 0))}%`;
const confidencePct = (value?: number | null) => value === null || value === undefined ? null : `${Math.round(Number(value) * 100)}%`;
const storyId = (story: Story) => story.story_id ?? story.id ?? 0;
const taskId = (task: Task) => task.task_id ?? task.id ?? 0;
const hasCoverageStatus = (story: Story | any) => Boolean(story?.status && COVERAGE_CFG[story.status]);
const acId = (ac: any) => ac?.id ?? ac?.ac_id;

function mergeStoryForDrawer(current: Story, updated: Story): Story {
  const next: Story = { ...current, ...updated };
  if (updated.acceptance_criteria && current.acceptance_criteria) {
    const currentAcs = new Map((current.acceptance_criteria || []).map((ac: any) => [acId(ac), ac]));
    next.acceptance_criteria = (updated.acceptance_criteria || []).map((ac: any) => ({
      ...(currentAcs.get(acId(ac)) || {}),
      ...ac,
    }));
  }
  return next;
}

function Badge({ label, color, bg }: { label: string; color: string; bg: string }) {
  return <span style={{ padding: "3px 8px", borderRadius: 6, fontSize: 10, fontWeight: 800, color, background: bg, whiteSpace: "nowrap" }}>{label}</span>;
}

function InlineInput({ value, onSave, multiline = false }: { value: string; onSave: (value: string) => void; multiline?: boolean }) {
  const [draft, setDraft] = useState(value || "");
  useEffect(() => setDraft(value || ""), [value]);
  const save = () => {
    if ((draft || "").trim() !== (value || "").trim()) onSave(draft.trim());
  };
  if (multiline) {
    return <textarea className="rq-input" value={draft} onChange={e => setDraft(e.target.value)} onBlur={save} rows={3} />;
  }
  return <input className="rq-input" value={draft} onChange={e => setDraft(e.target.value)} onBlur={save} />;
}

const emptyDraftStory = (): DraftStory => ({
  title: "",
  description: "",
  priority: "medium",
  acceptance_criteria: [{ id: 1, text: "" }],
  technical_tasks: [{ description: "", type: "backend", status: "todo", assigned_to: null, ac_ids: [1], ac_ids_text: "1" }],
});

const parseAcIds = (value: string) => Array.from(new Set(
  value
    .split(/[,\s]+/)
    .map(v => Number(v.trim()))
    .filter(Boolean)
));

function RequirementFormModal({
  draft,
  contributors,
  saving,
  onChange,
  onClose,
  onSubmit,
}: {
  draft: DraftStory;
  contributors: Contributor[];
  saving: boolean;
  onChange: (draft: DraftStory) => void;
  onClose: () => void;
  onSubmit: () => void;
}) {
  const updateTaskDraft = (index: number, patch: Partial<DraftTask>) => {
    onChange({
      ...draft,
      technical_tasks: draft.technical_tasks.map((task, idx) => idx === index ? { ...task, ...patch } : task),
    });
  };
  const updateAcDraft = (index: number, text: string) => {
    onChange({
      ...draft,
      acceptance_criteria: draft.acceptance_criteria.map((ac, idx) => idx === index ? { ...ac, text } : ac),
    });
  };
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 360, background: "rgba(0,0,0,0.68)", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }} onClick={onClose}>
      <div className="rq-panel" onClick={e => e.stopPropagation()} style={{ width: "min(980px, 96vw)", maxHeight: "90vh", overflow: "auto", padding: 0, borderColor: "rgba(139,92,246,0.22)", background: "#10101b" }}>
        <div style={{ padding: "22px 24px", borderBottom: "1px solid rgba(255,255,255,0.08)", display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
          <div>
            <div style={{ color: accent, fontSize: 11, fontWeight: 900, letterSpacing: ".8px", textTransform: "uppercase", marginBottom: 7 }}>Manual requirement</div>
            <h2 style={{ margin: 0, color: "white", fontFamily: "'Syne', sans-serif", fontSize: 22 }}>Add Requirement</h2>
            <p style={{ margin: "7px 0 0", color: "rgba(255,255,255,0.5)", fontSize: 13 }}>Create a user story, criteria, implementation tasks, and optional assignments.</p>
          </div>
          <button className="rq-btn-ghost" onClick={onClose}>Cancel</button>
        </div>

        <div style={{ padding: 24, display: "grid", gap: 16 }}>
          <div className="rq-panel" style={{ background: "rgba(255,255,255,0.035)", borderColor: "rgba(255,255,255,0.09)" }}>
            <h3 style={{ margin: "0 0 14px", color: "white", fontSize: 15 }}>Story</h3>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 180px", gap: 12 }}>
              <label style={{ display: "grid", gap: 6 }}>
                <span style={{ color: "rgba(255,255,255,0.55)", fontSize: 11, fontWeight: 800 }}>Story title</span>
                <input className="rq-input" value={draft.title} onChange={e => onChange({ ...draft, title: e.target.value })} placeholder="e.g. Task reassignment workflow" />
              </label>
              <label style={{ display: "grid", gap: 6 }}>
                <span style={{ color: "rgba(255,255,255,0.55)", fontSize: 11, fontWeight: 800 }}>Priority</span>
                <select className="rq-select" value={draft.priority} onChange={e => onChange({ ...draft, priority: e.target.value })}>
                  <option value="critical">Critical</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
              </label>
              <label style={{ display: "grid", gap: 6, gridColumn: "1 / -1" }}>
                <span style={{ color: "rgba(255,255,255,0.55)", fontSize: 11, fontWeight: 800 }}>User story description</span>
                <textarea className="rq-input" value={draft.description} onChange={e => onChange({ ...draft, description: e.target.value })} placeholder="As a..., I want..., so that..." rows={3} />
              </label>
            </div>
          </div>

          <div className="rq-panel" style={{ background: "rgba(139,92,246,0.055)", borderColor: "rgba(139,92,246,0.18)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <div>
                <h3 style={{ margin: 0, color: "white", fontSize: 15 }}>Acceptance Criteria</h3>
                <div style={{ color: "rgba(255,255,255,0.4)", fontSize: 12, marginTop: 3 }}>Define the business behaviors that coverage will evaluate later.</div>
              </div>
              <button className="rq-btn-ghost" onClick={() => onChange({ ...draft, acceptance_criteria: [...draft.acceptance_criteria, { id: Math.max(0, ...draft.acceptance_criteria.map(ac => ac.id)) + 1, text: "" }] })}><Plus size={13} /> Add AC</button>
            </div>
            <div style={{ display: "grid", gap: 8 }}>
              {draft.acceptance_criteria.map((ac, idx) => (
                <div key={ac.id} style={{ display: "grid", gridTemplateColumns: "76px 1fr 38px", gap: 10, alignItems: "center", padding: 10, borderRadius: 10, background: "rgba(0,0,0,0.18)", border: "1px solid rgba(255,255,255,0.06)" }}>
                  <span style={{ color: accent, fontSize: 12, fontWeight: 900 }}>AC #{idx + 1}</span>
                  <input className="rq-input" value={ac.text} onChange={e => updateAcDraft(idx, e.target.value)} placeholder="Acceptance criterion" />
                  <button className="rq-btn-ghost" onClick={() => onChange({ ...draft, acceptance_criteria: draft.acceptance_criteria.filter((_, acIdx) => acIdx !== idx) })} disabled={draft.acceptance_criteria.length <= 1}><Trash2 size={13} /></button>
                </div>
              ))}
            </div>
          </div>

          <div className="rq-panel" style={{ background: "rgba(59,130,246,0.045)", borderColor: "rgba(96,165,250,0.16)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <div>
                <h3 style={{ margin: 0, color: "white", fontSize: 15 }}>Technical Tasks</h3>
                <div style={{ color: "rgba(255,255,255,0.4)", fontSize: 12, marginTop: 3 }}>Break the requirement into implementation work and assign ownership when ready.</div>
              </div>
              <button className="rq-btn-ghost" onClick={() => onChange({ ...draft, technical_tasks: [...draft.technical_tasks, { description: "", type: "backend", status: "todo", assigned_to: null, ac_ids: [], ac_ids_text: "" }] })}><Plus size={13} /> Add Task</button>
            </div>
            <div style={{ display: "grid", gap: 10 }}>
              {draft.technical_tasks.map((task, idx) => (
                <div key={idx} style={{ display: "grid", gridTemplateColumns: "1fr 125px 170px 125px 38px", gap: 10, alignItems: "end", padding: 12, borderRadius: 10, background: "rgba(0,0,0,0.18)", border: "1px solid rgba(255,255,255,0.06)" }}>
                  <label style={{ display: "grid", gap: 6 }}>
                    <span style={{ color: "rgba(255,255,255,0.5)", fontSize: 11, fontWeight: 800 }}>Task description</span>
                    <input className="rq-input" value={task.description} onChange={e => updateTaskDraft(idx, { description: e.target.value })} placeholder="Implementation work" />
                  </label>
                  <label style={{ display: "grid", gap: 6 }}>
                    <span style={{ color: "rgba(255,255,255,0.5)", fontSize: 11, fontWeight: 800 }}>Type</span>
                    <select className="rq-select" value={task.type} onChange={e => updateTaskDraft(idx, { type: e.target.value })}>
                      <option value="backend">Backend</option>
                      <option value="frontend">Frontend</option>
                      <option value="qa">QA</option>
                    </select>
                  </label>
                  <label style={{ display: "grid", gap: 6 }}>
                    <span style={{ color: "rgba(255,255,255,0.5)", fontSize: 11, fontWeight: 800 }}>Developer</span>
                    <select className="rq-select" value={task.assigned_to || ""} onChange={e => updateTaskDraft(idx, { assigned_to: e.target.value ? Number(e.target.value) : null })}>
                      <option value="">Unassigned</option>
                      {contributors.filter(c => !task.type || !c.specialization || c.specialization === task.type).map(c => <option key={c.id} value={c.id}>{c.full_name || c.username}</option>)}
                    </select>
                  </label>
                  <label style={{ display: "grid", gap: 6 }}>
                    <span style={{ color: "rgba(255,255,255,0.5)", fontSize: 11, fontWeight: 800 }}>Status</span>
                    <select className="rq-select" value={task.status} onChange={e => updateTaskDraft(idx, { status: e.target.value })}>
                      <option value="todo">To Do</option>
                      <option value="in_progress">In Progress</option>
                      <option value="done">Done</option>
                    </select>
                  </label>
                  <button className="rq-btn-ghost" onClick={() => onChange({ ...draft, technical_tasks: draft.technical_tasks.filter((_, taskIdx) => taskIdx !== idx) })} disabled={draft.technical_tasks.length <= 1}><Trash2 size={13} /></button>
                  <label style={{ display: "grid", gap: 6, gridColumn: "1 / -1" }}>
                    <span style={{ color: "rgba(255,255,255,0.5)", fontSize: 11, fontWeight: 800 }}>Linked AC IDs</span>
                    <input
                      className="rq-input"
                      value={task.ac_ids_text ?? task.ac_ids.join(", ")}
                      onChange={e => updateTaskDraft(idx, { ac_ids_text: e.target.value, ac_ids: parseAcIds(e.target.value) })}
                      placeholder="e.g. 1, 2, 3"
                    />
                  </label>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, padding: "18px 24px", borderTop: "1px solid rgba(255,255,255,0.08)", background: "rgba(0,0,0,0.14)" }}>
          <button className="rq-btn-ghost" onClick={onClose}>Cancel</button>
          <button className="rq-btn-primary" disabled={saving} onClick={onSubmit}>{saving ? "Saving..." : "Create Requirement"}</button>
        </div>
      </div>
    </div>
  );
}

function StoryDetailsDrawer({
  story,
  contributors,
  onClose,
  onStoryUpdate,
  onTaskUpdate,
  onTaskCreate,
  onTaskDelete,
  onStoryDelete,
}: {
  story: Story | null;
  contributors: Contributor[];
  onClose: () => void;
  onStoryUpdate: (id: number, patch: any) => void;
  onTaskUpdate: (id: number, patch: any) => void;
  onTaskCreate: (storyId: number, task: DraftTask) => void;
  onTaskDelete: (taskId: number) => void;
  onStoryDelete: (story: Story) => void;
}) {
  const [addingTask, setAddingTask] = useState(false);
  const [newTask, setNewTask] = useState<DraftTask>({ description: "", type: "backend", status: "todo", assigned_to: null, ac_ids: [], ac_ids_text: "" });
  if (!story) return null;
  const acs = story.acceptance_criteria || [];
  const tasks = story.technical_tasks || story.tasks || [];
  const nextAcId = Math.max(0, ...acs.map((ac: any) => Number(acId(ac)) || 0)) + 1;
  const updateTaskLink = (task: Task, linkedAcId: number, checked: boolean) => {
    const current = new Set(task.ac_ids || []);
    if (checked) current.add(linkedAcId);
    else current.delete(linkedAcId);
    onTaskUpdate(taskId(task), { ac_ids: Array.from(current).sort((a, b) => a - b) });
  };
  const addAcceptanceCriterion = () => {
    onStoryUpdate(storyId(story), {
      acceptance_criteria: [...acs, { id: nextAcId, text: "" }],
    });
  };
  const deleteAcceptanceCriterion = (deletedAcId: number) => {
    if (!window.confirm(`Delete AC #${deletedAcId}? Linked tasks will be updated.`)) return;
    onStoryUpdate(storyId(story), {
      acceptance_criteria: acs.filter((ac: any) => acId(ac) !== deletedAcId),
    });
    tasks
      .filter(task => (task.ac_ids || []).includes(deletedAcId))
      .forEach(task => onTaskUpdate(taskId(task), { ac_ids: (task.ac_ids || []).filter(id => id !== deletedAcId) }));
  };
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 300, display: "flex", justifyContent: "flex-end", background: "rgba(0,0,0,0.55)" }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ width: "min(760px, 92vw)", height: "100%", background: "#10101b", borderLeft: "1px solid rgba(255,255,255,0.1)", padding: 28, overflowY: "auto" }}>
        <button className="rq-btn-ghost" onClick={onClose} style={{ marginBottom: 18 }}>Close</button>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
          <div>
            <h2 style={{ margin: 0, color: "white", fontFamily: "'Syne', sans-serif", fontSize: 22 }}>Story Details</h2>
            <div style={{ color: accent, fontSize: 12, fontWeight: 900, margin: "8px 0 16px" }}>{story.story_code}</div>
          </div>
          {role === "manager" && <button className="rq-btn-ghost" style={{ color: "#f87171" }} onClick={() => onStoryDelete(story)}><Trash2 size={13} /> Delete Requirement</button>}
        </div>
        {role === "manager" ? (
          <div className="rq-panel" style={{ marginBottom: 14 }}>
            <div style={{ display: "grid", gap: 10 }}>
              <InlineInput value={story.title} onSave={value => onStoryUpdate(storyId(story), { title: value })} />
              <InlineInput value={story.description} multiline onSave={value => onStoryUpdate(storyId(story), { description: value })} />
            </div>
          </div>
        ) : (
          <>
            <h3 style={{ color: "white", margin: "0 0 8px" }}>{story.title}</h3>
            <p style={{ color: "rgba(255,255,255,0.48)", lineHeight: 1.6 }}>{story.description}</p>
          </>
        )}

        <div className="rq-panel" style={{ marginBottom: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", marginBottom: 12 }}>
            <h3 style={{ color: "white", margin: 0, fontSize: 15 }}>Technical Tasks & Assignments</h3>
            {role === "manager" && <button className="rq-btn-ghost" onClick={() => setAddingTask(prev => !prev)}><Plus size={13} /> Add Task</button>}
          </div>
          {addingTask && (
            <div style={{ marginBottom: 12, padding: 12, borderRadius: 10, background: "rgba(59,130,246,0.05)", border: "1px solid rgba(96,165,250,0.16)", display: "grid", gap: 10 }}>
              <input className="rq-input" value={newTask.description} onChange={e => setNewTask(prev => ({ ...prev, description: e.target.value }))} placeholder="Task description" />
              <div style={{ display: "grid", gridTemplateColumns: "120px 160px 120px", gap: 8 }}>
                <select className="rq-select" value={newTask.type} onChange={e => setNewTask(prev => ({ ...prev, type: e.target.value }))}>
                  <option value="backend">Backend</option>
                  <option value="frontend">Frontend</option>
                  <option value="qa">QA</option>
                </select>
                <select className="rq-select" value={newTask.assigned_to || ""} onChange={e => setNewTask(prev => ({ ...prev, assigned_to: e.target.value ? Number(e.target.value) : null }))}>
                  <option value="">Unassigned</option>
                  {contributors.filter(c => !newTask.type || !c.specialization || c.specialization === newTask.type).map(c => <option key={c.id} value={c.id}>{c.full_name || c.username}</option>)}
                </select>
                <select className="rq-select" value={newTask.status} onChange={e => setNewTask(prev => ({ ...prev, status: e.target.value }))}>
                  <option value="todo">To Do</option>
                  <option value="in_progress">In Progress</option>
                  <option value="done">Done</option>
                </select>
              </div>
              <div style={{ display: "grid", gap: 8 }}>
                <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 11, fontWeight: 800 }}>Linked Acceptance Criteria</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {acs.map((ac: any) => {
                    const id = acId(ac);
                    return (
                      <label key={id} style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 9px", borderRadius: 8, background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.72)", fontSize: 12 }}>
                        <input type="checkbox" checked={newTask.ac_ids.includes(id)} onChange={e => setNewTask(prev => ({ ...prev, ac_ids: e.target.checked ? Array.from(new Set([...prev.ac_ids, id])).sort((a, b) => a - b) : prev.ac_ids.filter(item => item !== id) }))} />
                        AC #{id}
                      </label>
                    );
                  })}
                </div>
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                <button className="rq-btn-ghost" onClick={() => { setAddingTask(false); setNewTask({ description: "", type: "backend", status: "todo", assigned_to: null, ac_ids: [], ac_ids_text: "" }); }}>Cancel</button>
                <button className="rq-btn-primary" onClick={() => {
                  onTaskCreate(storyId(story), newTask);
                  setAddingTask(false);
                  setNewTask({ description: "", type: "backend", status: "todo", assigned_to: null, ac_ids: [], ac_ids_text: "" });
                }}>Create Task</button>
              </div>
            </div>
          )}
          <div style={{ display: "grid", gap: 8 }}>
            {tasks.map(task => {
              const cfg = TYPE_CFG[task.type] || TYPE_CFG.backend;
              return (
                <div key={taskId(task)} style={{ padding: 10, borderRadius: 9, background: "rgba(0,0,0,0.18)", border: "1px solid rgba(255,255,255,0.05)", display: "grid", gridTemplateColumns: role === "manager" ? "1fr 130px 160px 120px 36px" : "1fr 110px 90px", gap: 8, alignItems: "center" }}>
                  {role === "manager" ? <InlineInput value={task.description} onSave={value => onTaskUpdate(taskId(task), { description: value })} /> : <div style={{ color: "rgba(255,255,255,0.82)", fontSize: 13 }}>{task.description}</div>}
                  <Badge label={cfg.label} color={cfg.color} bg={cfg.bg} />
                  {role === "manager" ? (
                    <select className="rq-select" value={task.assigned_to || ""} onChange={e => onTaskUpdate(taskId(task), { assigned_to: e.target.value ? Number(e.target.value) : null })}>
                      <option value="">Unassigned</option>
                      {contributors.filter(c => !task.type || !c.specialization || c.specialization === task.type).map(c => <option key={c.id} value={c.id}>{c.full_name || c.username}</option>)}
                    </select>
                  ) : <span style={{ color: "rgba(255,255,255,0.58)", fontSize: 12 }}>Assigned to you</span>}
                  {role === "manager" ? (
                    <select className="rq-select" value={task.status || "todo"} onChange={e => onTaskUpdate(taskId(task), { status: e.target.value })}>
                      <option value="todo">To Do</option>
                      <option value="in_progress">In Progress</option>
                      <option value="done">Done</option>
                    </select>
                  ) : <span style={{ color: "rgba(255,255,255,0.52)", fontSize: 12 }}>{task.status}</span>}
                  {role === "manager" && <button className="rq-btn-ghost" onClick={() => onTaskDelete(taskId(task))}><Trash2 size={13} /></button>}
                  <div style={{ gridColumn: "1 / -1", display: "grid", gap: 8 }}>
                    <div style={{ color: "rgba(255,255,255,0.36)", fontSize: 11, fontWeight: 800 }}>Linked Acceptance Criteria</div>
                    {role === "manager" ? (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                        {acs.map((ac: any) => {
                          const id = acId(ac);
                          return (
                            <label key={id} style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 9px", borderRadius: 8, background: (task.ac_ids || []).includes(id) ? `${accent}22` : "rgba(255,255,255,0.04)", border: `1px solid ${(task.ac_ids || []).includes(id) ? `${accent}55` : "rgba(255,255,255,0.08)"}`, color: "rgba(255,255,255,0.72)", fontSize: 12 }}>
                              <input type="checkbox" checked={(task.ac_ids || []).includes(id)} onChange={e => updateTaskLink(task, id, e.target.checked)} />
                              AC #{id}
                            </label>
                          );
                        })}
                      </div>
                    ) : (
                      <div style={{ color: "rgba(255,255,255,0.42)", fontSize: 11 }}>
                        {(task.ac_ids || []).map(id => `AC #${id}`).join(", ") || "No linked acceptance criteria."}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
            <h3 style={{ color: "white", margin: "4px 0 0", fontSize: 15 }}>Acceptance Criteria, Coverage & Evidence</h3>
            {role === "manager" && <button className="rq-btn-ghost" onClick={addAcceptanceCriterion}><Plus size={13} /> Add AC</button>}
          </div>
          {acs.map((ac: any) => {
            const cfg = COVERAGE_CFG[ac.status] || COVERAGE_CFG.not_implemented;
            const confidence = confidencePct(ac.confidence);
            return (
              <div key={ac.ac_id ?? ac.id} className="rq-panel">
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
                  <div>
                    <div style={{ color: accent, fontSize: 12, fontWeight: 800 }}>AC #{ac.ac_id ?? ac.id}</div>
                    {role === "manager" ? (
                      <InlineInput
                        value={ac.text}
                        onSave={value => {
                          const updated = (story.acceptance_criteria || []).map((item: any) => acId(item) === acId(ac) ? { ...item, text: value } : item);
                          onStoryUpdate(storyId(story), { acceptance_criteria: updated });
                        }}
                      />
                    ) : (
                      <div style={{ color: "rgba(255,255,255,0.86)", fontSize: 14, lineHeight: 1.55 }}>{ac.text}</div>
                    )}
                  </div>
                  {ac.status && (
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 5, flexShrink: 0 }}>
                      <Badge label={`${cfg.label}${confidence ? ` (${confidence})` : ""}`} color={cfg.color} bg={cfg.bg} />
                      <span style={{ color: "rgba(255,255,255,0.34)", fontSize: 10, fontWeight: 800, textTransform: "uppercase", letterSpacing: ".5px" }}>
                        Confidence
                      </span>
                    </div>
                  )}
                  {role === "manager" && (
                    <button className="rq-btn-ghost" style={{ color: "#f87171", flexShrink: 0 }} onClick={() => deleteAcceptanceCriterion(acId(ac))}>
                      <Trash2 size={13} /> Delete AC
                    </button>
                  )}
                </div>
                {ac.llm_reason && <p style={{ color: "rgba(255,255,255,0.45)", fontSize: 12.5, lineHeight: 1.55 }}>{ac.llm_reason}</p>}
                {(ac.evidence || []).map((ev: any, idx: number) => (
                  <div key={`${ev.chunk_id || ev.file_path}-${idx}`} style={{ marginTop: 8, padding: 10, borderRadius: 8, background: "rgba(0,0,0,0.22)", border: "1px solid rgba(255,255,255,0.06)" }}>
                    <div style={{ color: "rgba(255,255,255,0.82)", fontSize: 12, fontWeight: 700 }}>{ev.file_path}</div>
                    <div style={{ color: "rgba(255,255,255,0.34)", fontSize: 11, marginTop: 3 }}>{ev.symbol_name || "chunk"} · lines {ev.start_line || "?"}-{ev.end_line || "?"} · {ev.retrieval_source || "primary"}</div>
                    {ev.excerpt && <pre style={{ whiteSpace: "pre-wrap", color: "rgba(255,255,255,0.45)", fontSize: 11, marginTop: 8, maxHeight: 140, overflow: "auto" }}>{ev.excerpt}</pre>}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default function RequirementsPage() {
  const [repos, setRepos] = useState<RepoRow[]>([]);
  const [selectedRepo, setSelectedRepo] = useState("");
  const [stories, setStories] = useState<Story[]>([]);
  const [coverage, setCoverage] = useState<any>(null);
  const [contributors, setContributors] = useState<Contributor[]>([]);
  const [loading, setLoading] = useState(false);
  const [coverageRunning, setCoverageRunning] = useState(false);
  const [query, setQuery] = useState("");
  const [filterCoverage, setFilterCoverage] = useState("all");
  const [selectedStory, setSelectedStory] = useState<Story | null>(null);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const [uploadingPrd, setUploadingPrd] = useState(false);
  const [reviewStories, setReviewStories] = useState<Story[]>([]);
  const [reviewDocId, setReviewDocId] = useState<number | null>(null);
  const [reviewSelectedTaskIds, setReviewSelectedTaskIds] = useState<number[]>([]);
  const [showAddRequirement, setShowAddRequirement] = useState(false);
  const [requirementDraft, setRequirementDraft] = useState<DraftStory>(emptyDraftStory());
  const [savingRequirement, setSavingRequirement] = useState(false);
  const dirtyRequirementIdsRef = useRef<number[]>([]);
  const dirtyTaskIdsRef = useRef<number[]>([]);

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3000);
  };

  const markCoverageStale = (
    reason: string,
    options: { ownership?: boolean } = {}
  ) => {
    setCoverage((prev: any) => {
      if (!prev?.run) return prev;
      const staleReasons = Array.from(new Set([...(prev.run.stale_reasons || []), reason]));
      return {
        ...prev,
        run: {
          ...prev.run,
          is_stale: true,
          ownership_stale: Boolean(prev.run.ownership_stale || options.ownership),
          implementation_stale: Boolean(prev.run.implementation_stale),
          stale_reasons: staleReasons,
        },
      };
    });
  };

  const removeCoverageStaleReason = (reason: string) => {
    setCoverage((prev: any) => {
      if (!prev?.run) return prev;
      const staleReasons = (prev.run.stale_reasons || []).filter((item: string) => item !== reason);
      const ownershipStale = Boolean(prev.run.ownership_stale && staleReasons.some((item: string) => item === "ownership_changed"));
      return {
        ...prev,
        run: {
          ...prev.run,
          stale_reasons: staleReasons,
          ownership_stale: ownershipStale,
          is_stale: staleReasons.length > 0,
        },
      };
    });
  };

  useEffect(() => {
    api.get("/analysis/history?limit=100")
      .then((analysisRes) => {
        const seen = new Set<number>();
        const eligibleHistory = (analysisRes.data.history || []).filter((item: RepoRow) => item.status === "completed");
        const merged = eligibleHistory.filter((item: RepoRow) => {
          if (seen.has(item.repo_id)) return false;
          seen.add(item.repo_id);
          return true;
        });
        setRepos(merged);
      })
      .catch(() => setRepos([]));
  }, []);

  const loadManagerData = useCallback(async (repoId: string) => {
    setLoading(true);
    try {
      try { await api.post(`/requirements/repositories/${repoId}/sync-contributors`); } catch {}
      const [storiesRes, contributorsRes, coverageRes] = await Promise.all([
        api.get(`/requirements/repositories/${repoId}/stories`),
        api.get(`/requirements/repositories/${repoId}/contributors`),
        api.get(`/requirements/coverage/repositories/${repoId}`).catch(() => ({ data: null })),
      ]);
      setStories(storiesRes.data || []);
      setContributors(contributorsRes.data || []);
      setCoverage(coverageRes.data);
    } catch {
      showToast("Failed to load requirements", false);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDeveloperData = useCallback(async (repoId: string) => {
    setLoading(true);
    try {
      const coverageRes = await api.get(`/requirements/coverage/repositories/${repoId}/developer`).catch(() => ({ data: null }));
      setCoverage(coverageRes.data);
      setStories(coverageRes.data?.stories || []);
    } catch {
      showToast("Failed to load assigned coverage", false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!selectedRepo) {
      setStories([]);
      setCoverage(null);
      return;
    }
    if (role === "manager") loadManagerData(selectedRepo);
    else loadDeveloperData(selectedRepo);
  }, [selectedRepo, loadManagerData, loadDeveloperData]);

  const refresh = () => {
    if (!selectedRepo) return;
    if (role === "manager") loadManagerData(selectedRepo);
    else loadDeveloperData(selectedRepo);
  };

  useEffect(() => {
    if (!selectedRepo || role !== "manager" || !coverage?.is_analysis_running) return;
    const timer = window.setInterval(() => {
      loadManagerData(selectedRepo);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [selectedRepo, coverage?.is_analysis_running, loadManagerData]);

  const updateStory = async (id: number, patch: any) => {
    try {
      const res = await api.patch(`/requirements/stories/${id}`, patch);
      const updated = res.data;
      setStories(prev => prev.map(s => storyId(s) === id ? { ...s, ...updated } : s));
      setSelectedStory(prev => prev && storyId(prev) === id ? mergeStoryForDrawer(prev, updated) : prev);
      dirtyRequirementIdsRef.current = Array.from(new Set([...dirtyRequirementIdsRef.current, id]));
      markCoverageStale("requirements_changed");
      showToast("Story saved");
    } catch {
      showToast("Story update failed", false);
    }
  };

  const adjustCoverageAfterStoryDelete = (deletedStoryId: number) => {
    setCoverage((prev: any) => {
      if (!prev?.stories) return prev;
      const removed = (prev.stories || []).find((s: any) => storyId(s) === deletedStoryId || s.story_id === deletedStoryId);
      const nextStories = (prev.stories || []).filter((s: any) => storyId(s) !== deletedStoryId && s.story_id !== deletedStoryId);
      if (!prev.summary || !removed) return { ...prev, stories: nextStories };
      return {
        ...prev,
        stories: nextStories,
        summary: {
          ...prev.summary,
          total_stories: Math.max(0, Number(prev.summary.total_stories || 0) - 1),
          implemented_stories: Math.max(0, Number(prev.summary.implemented_stories || 0) - (removed.status === "implemented" ? 1 : 0)),
          partially_implemented_stories: Math.max(0, Number(prev.summary.partially_implemented_stories || 0) - (removed.status === "partially_implemented" ? 1 : 0)),
          missing_stories: Math.max(0, Number(prev.summary.missing_stories || 0) - (removed.status === "not_implemented" ? 1 : 0)),
        },
      };
    });
  };

  const createRequirement = async () => {
    if (!selectedRepo) return;
    if (!requirementDraft.title.trim() || !requirementDraft.description.trim()) {
      showToast("Story title and description are required", false);
      return;
    }
    const acceptanceCriteria = requirementDraft.acceptance_criteria
      .filter(ac => ac.text.trim())
      .map((ac, idx) => ({ id: idx + 1, text: ac.text.trim() }));
    if (!acceptanceCriteria.length) {
      showToast("At least one acceptance criterion is required", false);
      return;
    }
    setSavingRequirement(true);
    try {
      const res = await api.post(`/requirements/repositories/${selectedRepo}/stories`, {
        title: requirementDraft.title.trim(),
        description: requirementDraft.description.trim(),
        role: "user",
        feature: requirementDraft.title.trim(),
        benefit: "business value",
        priority: requirementDraft.priority,
        acceptance_criteria: acceptanceCriteria,
        tags: [],
        technical_tasks: requirementDraft.technical_tasks
          .filter(task => task.description.trim())
          .map(task => ({
            description: task.description.trim(),
            type: task.type,
            status: task.status,
            assigned_to: task.assigned_to,
            ac_ids: task.ac_ids,
          })),
      });
      const created = res.data;
      setStories(prev => [...prev, created]);
      setSelectedStory(created);
      dirtyRequirementIdsRef.current = Array.from(new Set([...dirtyRequirementIdsRef.current, storyId(created)]));
      markCoverageStale("requirements_changed");
      setRequirementDraft(emptyDraftStory());
      setShowAddRequirement(false);
      showToast("Requirement created");
    } catch (err: any) {
      showToast(err.response?.data?.detail || "Requirement creation failed", false);
    } finally {
      setSavingRequirement(false);
    }
  };

  const deleteStory = async (story: Story) => {
    const id = storyId(story);
    if (!id) return;
    if (!window.confirm(`Delete "${story.title}"? This removes its acceptance criteria and tasks.`)) return;
    const deletedTaskIds = (story.technical_tasks || story.tasks || []).map(task => taskId(task)).filter(Boolean);
    try {
      await api.delete(`/requirements/stories/${id}`);
      setStories(prev => prev.filter(s => storyId(s) !== id));
      setSelectedStory(prev => prev && storyId(prev) === id ? null : prev);
      adjustCoverageAfterStoryDelete(id);
      dirtyRequirementIdsRef.current = dirtyRequirementIdsRef.current.filter(item => item !== id);
      if (dirtyRequirementIdsRef.current.length === 0) removeCoverageStaleReason("requirements_changed");
      if (deletedTaskIds.length) {
        dirtyTaskIdsRef.current = dirtyTaskIdsRef.current.filter(item => !deletedTaskIds.includes(item));
        if (dirtyTaskIdsRef.current.length === 0) removeCoverageStaleReason("technical_tasks_changed");
      }
      showToast("Requirement deleted");
    } catch (err: any) {
      showToast(err.response?.data?.detail || "Requirement deletion failed", false);
    }
  };

  const updateTask = async (id: number, patch: any) => {
    try {
      const res = await api.patch(`/requirements/tasks/${id}`, patch);
      const updated = res.data;
      const assignmentChanged = Object.prototype.hasOwnProperty.call(patch, "assigned_to");
      setStories(prev => prev.map(s => ({
        ...s,
        technical_tasks: (s.technical_tasks || []).map(t => taskId(t) === id ? { ...t, ...updated } : t),
        tasks: (s.tasks || []).map(t => taskId(t) === id ? { ...t, ...updated } : t),
      })));
      setSelectedStory(prev => prev ? {
        ...prev,
        technical_tasks: (prev.technical_tasks || []).map(t => taskId(t) === id ? { ...t, ...updated } : t),
        tasks: (prev.tasks || []).map(t => taskId(t) === id ? { ...t, ...updated } : t),
      } : prev);
      if (assignmentChanged) {
        markCoverageStale("ownership_changed", { ownership: true });
      } else {
        dirtyTaskIdsRef.current = Array.from(new Set([...dirtyTaskIdsRef.current, id]));
        markCoverageStale("technical_tasks_changed");
      }
      showToast("Task saved");
    } catch {
      showToast("Task update failed", false);
    }
  };

  const createTask = async (storyIdValue: number, task: DraftTask) => {
    if (!task.description?.trim()) {
      showToast("Task description is required", false);
      return;
    }
    try {
      const res = await api.post(`/requirements/stories/${storyIdValue}/tasks`, {
        description: task.description.trim(),
        type: task.type,
        status: task.status,
        assigned_to: task.assigned_to,
        ac_ids: task.ac_ids || [],
      });
      const created = res.data;
      setStories(prev => prev.map(story => storyId(story) === storyIdValue ? {
        ...story,
        technical_tasks: [...(story.technical_tasks || story.tasks || []), created],
        tasks: story.tasks ? [...story.tasks, created] : story.tasks,
      } : story));
      setSelectedStory(prev => prev && storyId(prev) === storyIdValue ? {
        ...prev,
        technical_tasks: [...(prev.technical_tasks || prev.tasks || []), created],
        tasks: prev.tasks ? [...prev.tasks, created] : prev.tasks,
      } : prev);
      dirtyTaskIdsRef.current = Array.from(new Set([...dirtyTaskIdsRef.current, taskId(created)]));
      markCoverageStale("technical_tasks_changed");
      showToast("Task created");
    } catch (err: any) {
      showToast(err.response?.data?.detail || "Task creation failed", false);
    }
  };

  const deleteTask = async (id: number) => {
    if (!window.confirm("Delete this technical task?")) return;
    try {
      await api.delete(`/requirements/tasks/${id}`);
      setStories(prev => prev.map(story => ({
        ...story,
        technical_tasks: (story.technical_tasks || []).filter(task => taskId(task) !== id),
        tasks: (story.tasks || []).filter(task => taskId(task) !== id),
      })));
      setSelectedStory(prev => prev ? {
        ...prev,
        technical_tasks: (prev.technical_tasks || []).filter(task => taskId(task) !== id),
        tasks: (prev.tasks || []).filter(task => taskId(task) !== id),
      } : prev);
      dirtyTaskIdsRef.current = dirtyTaskIdsRef.current.filter(item => item !== id);
      if (dirtyTaskIdsRef.current.length === 0) removeCoverageStaleReason("technical_tasks_changed");
      showToast("Task deleted");
    } catch (err: any) {
      showToast(err.response?.data?.detail || "Task deletion failed", false);
    }
  };

  const detectCoverage = async () => {
    if (!selectedRepo) return;
    setCoverageRunning(true);
    try {
      await api.post(`/requirements/coverage/repositories/${selectedRepo}/detect`);
      showToast(coverage ? "Coverage re-detection started" : "Coverage detection started");
      setTimeout(refresh, 2500);
    } catch (err: any) {
      showToast(err.response?.data?.detail || "Coverage detection failed", false);
    } finally {
      setCoverageRunning(false);
    }
  };

  const refreshOwnership = async () => {
    if (!selectedRepo) return;
    try {
      const res = await api.post(`/requirements/coverage/repositories/${selectedRepo}/refresh-ownership`);
      setCoverage(res.data);
      showToast("Ownership mappings refreshed");
      setTimeout(refresh, 250);
    } catch (err: any) {
      showToast(err.response?.data?.detail || "Ownership refresh failed", false);
    }
  };

  const uploadPrd = async (file: File) => {
    if (!selectedRepo || !file) return;
    setUploadingPrd(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("repository_id", selectedRepo);
      const uploaded = await api.post("/requirements/upload", form, { headers: { "Content-Type": "multipart/form-data" } });
      setReviewDocId(uploaded.data.document_id);
      const storiesRes = await api.get(`/requirements/${uploaded.data.document_id}/stories`);
      setReviewStories(storiesRes.data || []);
      try { await api.post(`/requirements/repositories/${selectedRepo}/sync-contributors`); } catch {}
      const contributorsRes = await api.get(`/requirements/repositories/${selectedRepo}/contributors`).catch(() => ({ data: [] }));
      setContributors(contributorsRes.data || []);
      showToast("Requirements extracted");
    } catch (err: any) {
      showToast(err.response?.data?.detail || "PRD extraction failed", false);
    } finally {
      setUploadingPrd(false);
    }
  };

  const updateReviewTask = async (id: number, patch: any) => {
    try {
      const res = await api.patch(`/requirements/tasks/${id}`, patch);
      setReviewStories(prev => prev.map(story => ({
        ...story,
        technical_tasks: (story.technical_tasks || []).map(task => taskId(task) === id ? { ...task, ...res.data } : task),
      })));
    } catch {
      showToast("Assignment update failed", false);
    }
  };

  const editReviewItem = async (type: "story" | "ac" | "story_desc" | "task", storyIdValue: number, text: string, title: string, itemId?: number) => {
    const next = window.prompt(title, text);
    if (next === null || next.trim() === text.trim()) return;
    try {
      if (type === "task" && itemId) {
        await updateReviewTask(itemId, { description: next.trim() });
        return;
      }
      if (type === "story") {
        await api.patch(`/requirements/stories/${storyIdValue}`, { title: next.trim() });
        setReviewStories(prev => prev.map(story => storyId(story) === storyIdValue ? { ...story, title: next.trim() } : story));
        return;
      }
      if (type === "story_desc") {
        await api.patch(`/requirements/stories/${storyIdValue}`, { description: next.trim() });
        setReviewStories(prev => prev.map(story => storyId(story) === storyIdValue ? { ...story, description: next.trim() } : story));
        return;
      }
      if (type === "ac" && itemId) {
        const story = reviewStories.find(s => storyId(s) === storyIdValue);
        if (!story) return;
        const updatedAcs = (story.acceptance_criteria || []).map((ac: any) => (ac.id ?? ac.ac_id) === itemId ? { ...ac, text: next.trim() } : ac);
        await api.patch(`/requirements/stories/${storyIdValue}`, { acceptance_criteria: updatedAcs });
        setReviewStories(prev => prev.map(s => storyId(s) === storyIdValue ? { ...s, acceptance_criteria: updatedAcs } : s));
      }
    } catch (err: any) {
      showToast(err.response?.data?.detail || "Review update failed", false);
    }
  };

  const mergeReviewTasks = async (storyIdValue: number) => {
    const story = reviewStories.find(s => storyId(s) === storyIdValue);
    if (!story) return;
    const selectedInStory = (story.technical_tasks || []).filter(task => reviewSelectedTaskIds.includes(taskId(task)));
    if (selectedInStory.length < 2) return;
    const combined = selectedInStory.map(task => `- [${task.type?.toUpperCase?.() || "TASK"}] ${task.description}`).join("\n\n");
    const next = window.prompt("Edit merged task description", combined);
    if (!next?.trim()) return;
    try {
      const res = await api.post(`/requirements/stories/${storyIdValue}/tasks/merge`, {
        task_ids: selectedInStory.map(task => taskId(task)),
        new_description: next.trim(),
      });
      const mergedTask = res.data;
      setReviewStories(prev => prev.map(s => {
        if (storyId(s) !== storyIdValue) return s;
        const selectedIds = new Set(selectedInStory.map(task => taskId(task)));
        return { ...s, technical_tasks: [...(s.technical_tasks || []).filter(task => !selectedIds.has(taskId(task))), mergedTask] };
      }));
      setReviewSelectedTaskIds(prev => prev.filter(id => !selectedInStory.some(task => taskId(task) === id)));
    } catch (err: any) {
      showToast(err.response?.data?.detail || "Task merge failed", false);
    }
  };

  const confirmReview = async () => {
    if (!reviewDocId) return;
    try {
      await api.post(`/requirements/${reviewDocId}/confirm`);
      setReviewStories([]);
      setReviewDocId(null);
      setReviewSelectedTaskIds([]);
      showToast("Requirements confirmed");
      refresh();
    } catch (err: any) {
      showToast(err.response?.data?.detail || "Confirmation failed", false);
    }
  };

  const mergedStories: Story[] = useMemo(() => {
    if (role !== "manager" || !coverage?.stories) return stories;
    const byId = new Map((coverage.stories || []).map((s: Story) => [storyId(s), s]));
    return stories.map(s => {
      const cov: any = byId.get(storyId(s));
      if (!cov) return s;
      const covAcs = new Map((cov.acceptance_criteria || []).map((ac: any) => [ac.ac_id, ac]));
      return {
        ...s,
        coverage_percent: cov.coverage_percent,
        status: cov.status,
        matched_symbols: cov.matched_symbols,
        acceptance_criteria: (s.acceptance_criteria || []).map((ac: any) => ({
          ...ac,
          ...(covAcs.get(ac.id) || {}),
          id: ac.id,
          text: ac.text,
        })),
      };
    });
  }, [stories, coverage]);

  const filteredStories = mergedStories.filter(story => {
    const text = `${story.story_code} ${story.title} ${story.description}`.toLowerCase();
    if (query && !text.includes(query.toLowerCase())) return false;
    if (filterCoverage !== "all" && story.status !== filterCoverage) return false;
    return true;
  });
  const hasRequirements = mergedStories.length > 0;
  const isReviewingPrd = role === "manager" && reviewStories.length > 0;
  const hasConfirmedRequirements = hasRequirements && !isReviewingPrd;

  const allTasks = filteredStories.flatMap(story => (story.technical_tasks || story.tasks || []).map(task => ({ ...task, story })));
  const assignedCount = allTasks.filter(t => t.assigned_to).length;
  const coverageRun = coverage?.run;
  const activeRun = coverage?.active_run;
  const isAnalysisRunning = Boolean(coverage?.is_analysis_running || activeRun);
  const canDetect = role === "manager" && selectedRepo && hasConfirmedRequirements;
  const detectLabel = isAnalysisRunning ? "Analysis Running" : coverageRun ? "Re-Detect Coverage" : "Detect Coverage";
  const overallCoverage = coverageRun ? Number(coverageRun.overall_coverage_percent || 0) : null;
  const readinessStatus = !coverageRun
    ? "Not Assessed"
    : Number(overallCoverage) >= 85
      ? "Ready"
      : Number(overallCoverage) >= 70
        ? "Mostly Ready"
        : Number(overallCoverage) >= 45
          ? "At Risk"
          : "Blocked";
  const readinessColor = readinessStatus === "Ready" ? "#14b8a6" : readinessStatus === "Mostly Ready" ? "#3b82f6" : readinessStatus === "At Risk" ? "#f59e0b" : readinessStatus === "Blocked" ? "#ef4444" : "rgba(255,255,255,0.42)";
  const readinessBorderColor = readinessStatus === "Not Assessed" ? "rgba(255,255,255,0.12)" : `${readinessColor}55`;
  const readinessSoftBg = readinessStatus === "Not Assessed" ? "rgba(255,255,255,0.07)" : `${readinessColor}22`;
  const confirmedStoryIds = new Set(stories.map(story => storyId(story)));
  const coverageStories = (coverage?.stories || []).filter((story: any) => confirmedStoryIds.has(storyId(story) || story.story_id) && hasCoverageStatus(story));
  const highPriorityGaps = coverageStories
    .filter((s: any) => ["critical", "high"].includes(s.priority) && s.status !== "implemented")
    .sort((a: any, b: any) => (a.coverage_percent || 0) - (b.coverage_percent || 0))
    .slice(0, 5);
  const previousCoverage = coverage?.trends?.length > 1 ? Number(coverage.trends[coverage.trends.length - 2]?.overall_coverage_percent || 0) : null;
  const coverageDelta = previousCoverage === null || overallCoverage === null ? null : Math.round(overallCoverage - previousCoverage);
  const staleReasonLabels: Record<string, string> = {
    requirements_changed: "Requirements changed",
    technical_tasks_changed: "Technical tasks changed",
    ownership_changed: "Ownership changed",
    repository_changed: "Repository changed",
    branch_changed: "Branch changed",
    commit_changed: "Commit changed",
    new_analysis_run_available: "New analysis available",
    repository_branch_changed: "Repository branch changed",
    repository_commit_changed: "Repository commit changed",
  };
  const staleReasons: string[] = Array.from(new Set<string>((coverageRun?.stale_reasons || []).map((reason: unknown) => String(reason))))
    .filter(reason => reason !== "assignments_changed");

  return (
    <DashboardLayout>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500;600;700&display=swap');
        .rq-input,.rq-select{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:9px;color:white;font-family:'DM Sans',sans-serif;font-size:13px;outline:none;padding:8px 10px;box-sizing:border-box}
        .rq-input:focus,.rq-select:focus{border-color:${accent}80;background:rgba(255,255,255,0.06)}
        .rq-select option{background:#1a1a2e;color:white}
        .rq-btn-ghost{display:inline-flex;align-items:center;gap:7px;padding:8px 13px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:9px;color:rgba(255,255,255,0.7);font-family:'DM Sans',sans-serif;font-size:12px;font-weight:700;cursor:pointer}
        .rq-btn-primary{display:inline-flex;align-items:center;gap:8px;padding:9px 15px;background:linear-gradient(135deg,${accent},#ec4899);border:none;border-radius:9px;color:white;font-family:'DM Sans',sans-serif;font-size:12px;font-weight:800;cursor:pointer}
        .rq-btn-primary:disabled{opacity:.45;cursor:not-allowed}
        .rq-panel{background:rgba(255,255,255,0.025);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:14px}
        .rq-table{width:100%;border-collapse:separate;border-spacing:0 8px}
        .rq-table th{text-align:left;color:rgba(255,255,255,0.32);font-size:10px;text-transform:uppercase;letter-spacing:.7px;padding:0 10px}
        .rq-table td{background:rgba(255,255,255,0.025);border-top:1px solid rgba(255,255,255,0.06);border-bottom:1px solid rgba(255,255,255,0.06);padding:10px;font-size:12px;color:rgba(255,255,255,0.78);vertical-align:top}
        .rq-table td:first-child{border-left:1px solid rgba(255,255,255,0.06);border-radius:10px 0 0 10px}
        .rq-table td:last-child{border-right:1px solid rgba(255,255,255,0.06);border-radius:0 10px 10px 0}
      `}</style>

      {toast && (
        <div style={{ position: "fixed", right: 26, bottom: 26, zIndex: 500, padding: "11px 16px", borderRadius: 10, background: "#181826", border: `1px solid ${toast.ok ? "rgba(52,211,153,.35)" : "rgba(248,113,113,.35)"}`, color: toast.ok ? "#34d399" : "#f87171", fontSize: 13, fontWeight: 800 }}>{toast.msg}</div>
      )}
      <StoryDetailsDrawer
        story={selectedStory}
        contributors={contributors}
        onClose={() => setSelectedStory(null)}
        onStoryUpdate={updateStory}
        onTaskUpdate={updateTask}
        onTaskCreate={createTask}
        onTaskDelete={deleteTask}
        onStoryDelete={deleteStory}
      />
      {showAddRequirement && (
        <RequirementFormModal
          draft={requirementDraft}
          contributors={contributors}
          saving={savingRequirement}
          onChange={setRequirementDraft}
          onClose={() => setShowAddRequirement(false)}
          onSubmit={createRequirement}
        />
      )}
      <div style={{ padding: "32px 36px 80px", maxWidth: 1280, fontFamily: "'DM Sans', sans-serif" }}>
        <div style={{ marginBottom: 24 }}>
          <h1 style={{ margin: "0 0 6px", color: "white", fontFamily: "'Syne', sans-serif", fontSize: 26 }}>Requirements Workspace</h1>
          <p style={{ margin: 0, color: "rgba(255,255,255,0.38)", fontSize: 14 }}>
            {role === "manager" ? "Manage confirmed requirements, assignments, and coverage evidence." : "Track coverage for your assigned stories and tasks."}
          </p>
        </div>

        <div className="rq-panel" style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 18 }}>
          <select className="rq-select" value={selectedRepo} onChange={e => setSelectedRepo(e.target.value)} style={{ minWidth: 250, width: 312, flex: "0 0 312px" }}>
            <option value="">Select repository</option>
            {repos.map(repo => <option key={repo.repo_id} value={repo.repo_id}>{repo.repo_name} ({repo.branch})</option>)}
          </select>
          {selectedRepo && hasConfirmedRequirements && (
            <>
              <div style={{ position: "relative", flex: "1 1 260px" }}>
                <Search size={14} style={{ position: "absolute", left: 10, top: 10, color: "rgba(255,255,255,0.3)" }} />
                <input className="rq-input" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search stories or tasks" style={{ width: "100%", paddingLeft: 30 }} />
              </div>
              {role === "manager" && (
                <select className="rq-select" value={filterCoverage} onChange={e => setFilterCoverage(e.target.value)}>
                  <option value="all">All Coverage</option>
                  <option value="implemented">Implemented</option>
                  <option value="partially_implemented">Partial</option>
                  <option value="not_implemented">Missing</option>
                </select>
              )}
            </>
          )}
          <button className="rq-btn-ghost" onClick={refresh}><RefreshCw size={13} /> Refresh</button>
        </div>

        {selectedRepo && role === "manager" && hasConfirmedRequirements && isAnalysisRunning && (
          <div className="rq-panel" style={{ marginBottom: 18, borderColor: "rgba(96,165,250,0.28)", background: "rgba(59,130,246,0.08)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14 }}>
            <div>
              <div style={{ color: "#93c5fd", fontSize: 13, fontWeight: 900 }}>Coverage Analysis In Progress</div>
              <div style={{ color: "rgba(255,255,255,0.52)", fontSize: 12, marginTop: 4 }}>
                {coverageRun
                  ? "Showing the latest completed coverage results until the new analysis finishes."
                  : "Coverage analysis is running. Results will appear here when the first completed run is ready."}
              </div>
            </div>
            <div style={{ color: "rgba(255,255,255,0.46)", fontSize: 12, fontWeight: 800, textTransform: "capitalize" }}>
              {activeRun?.status || "running"}
            </div>
          </div>
        )}

        {selectedRepo && role === "manager" && hasConfirmedRequirements && (
          <>
          <div className="rq-panel" style={{ marginBottom: 18, background: "linear-gradient(135deg, rgba(20,184,166,0.13), rgba(59,130,246,0.07))", borderColor: readinessBorderColor }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 24, alignItems: "center" }}>
              <div>
                <div style={{ color: readinessColor, fontSize: 13, fontWeight: 900, marginBottom: 8 }}>Project Readiness</div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
                  <span style={{ color: "white", fontSize: 44, fontWeight: 900, letterSpacing: "-1px" }}>{coverageRun ? pct(overallCoverage) : "—"}</span>
                  <span style={{ color: "rgba(255,255,255,0.48)", fontSize: 16 }}>complete</span>
                </div>
                <div style={{ color: "rgba(255,255,255,0.45)", fontSize: 13, marginTop: 4 }}>
                  Tracks business value delivered against confirmed PRD requirements.
                </div>
                <div style={{ display: "inline-flex", alignItems: "center", gap: 8, marginTop: 14, padding: "7px 12px", borderRadius: 999, background: readinessSoftBg, color: readinessColor, fontSize: 12, fontWeight: 900 }}>
                  Deployment Readiness: {readinessStatus}
                </div>
              </div>
              <div style={{ width: 124, height: 124, borderRadius: "50%", border: `12px solid ${readinessColor}`, display: "flex", alignItems: "center", justifyContent: "center", boxShadow: `0 0 0 12px ${readinessSoftBg}` }}>
                <div style={{ textAlign: "center" }}>
                  <div style={{ color: "white", fontSize: 24, fontWeight: 900 }}>{coverageRun ? pct(overallCoverage) : "—"}</div>
                  <div style={{ color: "rgba(255,255,255,0.45)", fontSize: 11 }}>coverage</div>
                </div>
              </div>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(130px, 1fr))", gap: 14, marginBottom: 18 }}>
            {[
              ["Total Requirements", coverage?.summary?.total_stories ?? stories.length, "#a78bfa"],
              ["Covered Requirements", coverage?.summary?.implemented_stories ?? 0, "#14b8a6"],
              ["Partial Requirements", coverage?.summary?.partially_implemented_stories ?? 0, "#f59e0b"],
              ["Missing Requirements", coverage?.summary?.missing_stories ?? 0, "#ef4444"],
              ["Critical Gaps", highPriorityGaps.length, "#fb7185"],
            ].map(([label, value, color]) => (
              <div key={label as string} className="rq-panel" style={{ minHeight: 96 }}>
                <div style={{ width: 26, height: 26, borderRadius: 8, background: `${color}22`, marginBottom: 14 }} />
                <div style={{ color: "white", fontSize: 24, fontWeight: 900 }}>{value}</div>
                <div style={{ color: "rgba(255,255,255,0.38)", fontSize: 12, marginTop: 4 }}>{label}</div>
              </div>
            ))}
          </div>

          <div className="rq-panel" style={{ marginBottom: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 14, gap: 12 }}>
              <div style={{ color: coverageRun?.is_stale ? "#fbbf24" : "rgba(255,255,255,0.38)", fontSize: 12, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                {coverageRun?.is_stale && <AlertTriangle size={14} />}
                {!coverageRun && "No coverage run exists yet."}
                {coverageRun && !coverageRun.is_stale && `Last run ${coverageRun.completed_at || coverageRun.created_at}`}
                {coverageRun?.is_stale && (
                  <>
                    <span style={{ fontWeight: 900 }}>Coverage outdated</span>
                    {coverageRun.ownership_stale && <Badge label="Ownership stale" color="#fbbf24" bg="rgba(251,191,36,0.12)" />}
                    {staleReasons.filter(reason => reason !== "ownership_changed").map(reason => (
                      <Badge key={reason} label={staleReasonLabels[reason] || reason.replace(/_/g, " ")} color="#f59e0b" bg="rgba(245,158,11,0.12)" />
                    ))}
                  </>
                )}
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                {coverageRun?.ownership_stale && (
                  <button className="rq-btn-ghost" onClick={refreshOwnership}>Refresh Ownership</button>
                )}
                <button className="rq-btn-ghost" onClick={() => {
                  setRequirementDraft(emptyDraftStory());
                  setShowAddRequirement(true);
                }}>
                  <Plus size={13} /> Add Requirement
                </button>
                <button className="rq-btn-primary" disabled={!canDetect || coverageRunning || isAnalysisRunning} onClick={detectCoverage}>
                  {coverageRunning ? "Starting..." : detectLabel}
                </button>
              </div>
            </div>
          </div>
          </>
        )}

        {false && selectedRepo && role === "manager" && coverage && (
          <div className="rq-panel" style={{ marginBottom: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <h2 style={{ margin: 0, color: "white", fontSize: 16 }}>Coverage Results</h2>
              <span style={{ color: "rgba(255,255,255,0.34)", fontSize: 12 }}>Trend-ready: {coverage.trends?.length || 0} runs</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1fr 1fr", gap: 12 }}>
              <div style={{ padding: 14, borderRadius: 10, background: "rgba(0,0,0,0.18)", border: "1px solid rgba(255,255,255,0.05)" }}>
                <div style={{ color: "rgba(255,255,255,0.32)", fontSize: 10, textTransform: "uppercase", letterSpacing: ".7px" }}>Missing Features</div>
                <div style={{ marginTop: 8, display: "grid", gap: 6 }}>
                  {(coverage.stories || []).filter((s: any) => s.status === "not_implemented").slice(0, 4).map((s: any) => (
                    <button key={s.story_id} onClick={() => setSelectedStory(mergedStories.find(ms => storyId(ms) === s.story_id) || s)} style={{ textAlign: "left", border: "none", background: "transparent", color: "#f87171", cursor: "pointer", fontSize: 12 }}>{s.story_code} · {s.title}</button>
                  ))}
                  {!(coverage.stories || []).some((s: any) => s.status === "not_implemented") && <span style={{ color: "rgba(255,255,255,0.42)", fontSize: 12 }}>No fully missing stories.</span>}
                </div>
              </div>
              <div style={{ padding: 14, borderRadius: 10, background: "rgba(0,0,0,0.18)", border: "1px solid rgba(255,255,255,0.05)" }}>
                <div style={{ color: "rgba(255,255,255,0.32)", fontSize: 10, textTransform: "uppercase", letterSpacing: ".7px" }}>Critical Gaps</div>
                <div style={{ marginTop: 8, display: "grid", gap: 6 }}>
                  {(coverage.stories || []).filter((s: any) => ["critical", "high"].includes(s.priority) && s.status !== "implemented").slice(0, 4).map((s: any) => (
                    <button key={s.story_id} onClick={() => setSelectedStory(mergedStories.find(ms => storyId(ms) === s.story_id) || s)} style={{ textAlign: "left", border: "none", background: "transparent", color: "#fbbf24", cursor: "pointer", fontSize: 12 }}>{s.story_code} · {s.coverage_percent}% · {s.title}</button>
                  ))}
                  {!(coverage.stories || []).some((s: any) => ["critical", "high"].includes(s.priority) && s.status !== "implemented") && <span style={{ color: "rgba(255,255,255,0.42)", fontSize: 12 }}>No critical gaps.</span>}
                </div>
              </div>
              <div style={{ padding: 14, borderRadius: 10, background: "rgba(0,0,0,0.18)", border: "1px solid rgba(255,255,255,0.05)" }}>
                <div style={{ color: "rgba(255,255,255,0.32)", fontSize: 10, textTransform: "uppercase", letterSpacing: ".7px" }}>Coverage Insights</div>
                <p style={{ color: "rgba(255,255,255,0.5)", fontSize: 12, lineHeight: 1.55, margin: "8px 0 0" }}>
                  Repository coverage is {pct(coverageRun?.overall_coverage_percent)} across {coverage.summary?.total_stories || 0} confirmed stories. Open any story for AC explanations, evidence, and missing areas.
                </p>
              </div>
            </div>
          </div>
        )}

        {selectedRepo && role !== "manager" && coverage && (
          <div className="rq-panel" style={{ marginBottom: 18 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(120px, 1fr))", gap: 12 }}>
              {[
                ["My Stories", coverage.summary?.assigned_stories ?? 0],
                ["My Tasks", coverage.summary?.assigned_tasks ?? 0],
                ["Covered", coverage.summary?.covered_criteria ?? 0],
                ["Needs Work", coverage.summary?.partial_criteria ?? 0],
                ["Missing", coverage.summary?.missing_criteria ?? 0],
              ].map(([label, value]) => (
                <div key={label} style={{ padding: 12, borderRadius: 10, background: "rgba(0,0,0,0.18)", border: "1px solid rgba(255,255,255,0.05)" }}>
                  <div style={{ color: "rgba(255,255,255,0.32)", fontSize: 10, textTransform: "uppercase", letterSpacing: ".7px" }}>{label}</div>
                  <div style={{ color: "white", fontSize: 22, fontWeight: 900, marginTop: 4 }}>{value}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {loading && <div className="rq-panel" style={{ color: "rgba(255,255,255,0.45)" }}>Loading requirements...</div>}

        {!loading && selectedRepo && role === "manager" && isReviewingPrd && (
          <ExtractedRequirementsReviewModal
            accent={accent}
            stories={reviewStories as any}
            contributors={contributors}
            selectedTaskIds={reviewSelectedTaskIds}
            setSelectedTaskIds={setReviewSelectedTaskIds}
            onClose={() => {
              setReviewStories([]);
              setReviewDocId(null);
            }}
            onConfirm={confirmReview}
            onEdit={editReviewItem}
            onMerge={mergeReviewTasks}
            onTaskUpdate={updateReviewTask}
          />
        )}

        {!loading && selectedRepo && role === "manager" && !hasRequirements && !isReviewingPrd && (
          <div className="rq-panel" style={{ color: "rgba(255,255,255,0.72)", padding: 28 }}>
            <div style={{ display: "grid", gap: 16 }}>
              <div>
                <div style={{ color: accent, fontSize: 11, fontWeight: 900, letterSpacing: ".8px", textTransform: "uppercase", marginBottom: 8 }}>Requirements analysis has not started</div>
                <h2 style={{ color: "white", margin: "0 0 6px", fontSize: 18 }}>Business Requirements <span style={{ color: "rgba(255,255,255,0.34)", fontSize: 12 }}>optional</span></h2>
                <p style={{ color: "rgba(255,255,255,0.42)", margin: 0, fontSize: 13 }}>
                  Upload a PRD to extract and map requirements to code automatically.
                </p>
              </div>
              <PrdUploadDropZone accent={accent} uploading={uploadingPrd} onFile={uploadPrd} />
            </div>
          </div>
        )}

        {!loading && selectedRepo && role !== "manager" && !hasRequirements && (
          <div className="rq-panel" style={{ color: "rgba(255,255,255,0.72)", padding: 28 }}>
            No assigned coverage is available for your tasks yet.
          </div>
        )}

        {!loading && selectedRepo && hasConfirmedRequirements && filteredStories.length === 0 && (
          <div className="rq-panel" style={{ color: "rgba(255,255,255,0.72)", padding: 28 }}>
            <h2 style={{ color: "white", margin: "0 0 6px", fontSize: 18 }}>No requirements match the current filters.</h2>
            <p style={{ color: "rgba(255,255,255,0.42)", margin: 0, fontSize: 13 }}>
              Adjust the search text or coverage status filter to see confirmed requirements.
            </p>
          </div>
        )}

        {!loading && hasConfirmedRequirements && filteredStories.length > 0 && (
          <>
            <div className="rq-panel" style={{ marginBottom: 18 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <h2 style={{ margin: 0, color: "white", fontSize: 16 }}>Confirmed Requirements Summary</h2>
                <span style={{ color: "rgba(255,255,255,0.32)", fontSize: 12 }}>{filteredStories.length} visible</span>
              </div>
              <table className="rq-table">
                <thead>
                  <tr>
                    <th>Story</th>
                    <th>Coverage</th>
                    <th>Status</th>
                    <th>Assigned Tasks</th>
                    <th>Last Coverage Run</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredStories.map(story => {
                    const evaluated = hasCoverageStatus(story);
                    const cfg = evaluated ? COVERAGE_CFG[story.status || ""] : null;
                    const storyTasks = story.technical_tasks || story.tasks || [];
                    return (
                      <tr key={storyId(story)}>
                        <td style={{ minWidth: 280 }}>
                          <div style={{ color: "white", fontWeight: 800 }}>{story.title}</div>
                          <div style={{ color: accent, marginTop: 4, fontSize: 11, fontWeight: 900 }}>{story.story_code} · {story.priority}</div>
                        </td>
                        <td>
                          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                            <strong style={{ color: evaluated ? "white" : "rgba(255,255,255,0.42)" }}>
                              {evaluated ? pct(story.coverage_percent ?? story.visible_coverage_percent) : "N/A"}
                            </strong>
                          </div>
                        </td>
                        <td>
                          {cfg ? <Badge label={cfg.label} color={cfg.color} bg={cfg.bg} /> : <Badge label="Not Evaluated" color="rgba(255,255,255,0.58)" bg="rgba(255,255,255,0.08)" />}
                        </td>
                        <td>{storyTasks.filter(t => t.assigned_to).length}/{storyTasks.length} Tasks</td>
                        <td>{evaluated && coverageRun?.completed_at ? new Date(coverageRun.completed_at).toLocaleString() : "No run"}</td>
                        <td>
                          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                            <button className="rq-btn-ghost" onClick={() => setSelectedStory(story)}><Eye size={13} /> Open Story</button>
                            {role === "manager" && <button className="rq-btn-ghost" style={{ color: "#f87171" }} onClick={() => deleteStory(story)}><Trash2 size={13} /> Delete</button>}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {role === "manager" && coverage && (
              <>
                <div className="rq-panel" style={{ marginBottom: 18 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
                    <h2 style={{ margin: 0, color: "white", fontSize: 16 }}>Requirement Progress</h2>
                    <span style={{ color: "rgba(255,255,255,0.34)", fontSize: 12 }}>Coverage Trend: {coverageDelta === null ? "first run" : `${coverageDelta >= 0 ? "+" : ""}${coverageDelta}% since last run`}</span>
                  </div>
                  <div style={{ display: "grid", gap: 12 }}>
                    {coverageStories.slice().sort((a: any, b: any) => (b.coverage_percent || 0) - (a.coverage_percent || 0)).slice(0, 6).map((s: any) => {
                      const riskColor = s.status === "implemented" ? "#14b8a6" : s.status === "partially_implemented" ? "#3b82f6" : "#f97316";
                      const label = s.status === "implemented" ? "Ready" : s.status === "partially_implemented" ? "In Progress" : "At Risk";
                      return (
                        <button key={s.story_id} onClick={() => setSelectedStory(mergedStories.find(ms => storyId(ms) === s.story_id) || s)} style={{ textAlign: "left", border: "1px solid rgba(255,255,255,0.06)", background: "rgba(0,0,0,0.16)", borderRadius: 10, padding: 13, cursor: "pointer" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", gap: 14, marginBottom: 9 }}>
                            <div>
                              <div style={{ color: "white", fontSize: 13, fontWeight: 900 }}>{s.title}</div>
                              <div style={{ color: "rgba(255,255,255,0.42)", fontSize: 11, marginTop: 3 }}>{label}</div>
                            </div>
                            <div style={{ color: riskColor, fontSize: 20, fontWeight: 900 }}>{Math.round(s.coverage_percent || 0)}%</div>
                          </div>
                          <div style={{ height: 8, borderRadius: 99, background: "rgba(255,255,255,0.12)", overflow: "hidden" }}>
                            <div style={{ height: "100%", width: `${Math.min(100, Math.max(0, s.coverage_percent || 0))}%`, background: riskColor }} />
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="rq-panel" style={{ marginBottom: 18, background: "rgba(99,102,241,0.08)", borderColor: "rgba(129,140,248,0.22)" }}>
                  <h2 style={{ margin: "0 0 10px", color: "white", fontSize: 16 }}>AI Project Insights</h2>
                  <div style={{ display: "grid", gap: 7, color: "rgba(255,255,255,0.62)", fontSize: 13, lineHeight: 1.55 }}>
                    <div>Deployment readiness is <strong style={{ color: readinessColor }}>{readinessStatus}</strong> based on confirmed requirement coverage.</div>
                    {highPriorityGaps.length > 0 && <div>{highPriorityGaps.length} critical or high-priority requirement{highPriorityGaps.length === 1 ? "" : "s"} remain uncovered or partially covered.</div>}
                    {coverageDelta !== null && <div>Coverage {coverageDelta >= 0 ? "improved" : "dropped"} by {Math.abs(coverageDelta)}% since the previous run.</div>}
                    {assignedCount < allTasks.length && <div>{allTasks.length - assignedCount} task{allTasks.length - assignedCount === 1 ? "" : "s"} still need ownership before release planning is complete.</div>}
                  </div>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
