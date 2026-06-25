import { useRef, useState } from "react";

type Contributor = { id: number; username: string; full_name: string; specialization?: string | null };
type Task = { id: number; type: string; description: string; status?: string; assigned_to?: number | null; ac_ids: number[] };
type Story = {
  id: number;
  story_code: string;
  title: string;
  description: string;
  acceptance_criteria: Array<{ id: number; text: string }>;
  technical_tasks: Task[];
};

const WorkflowStyles = ({ accent }: { accent: string }) => (
  <style>{`
    .ra-upload-drop-zone{border:1.5px dashed var(--border-hover);border-radius:12px;padding:32px 20px;text-align:center;cursor:pointer;transition:all .2s}
    .ra-upload-drop-zone:hover,.ra-upload-drop-zone.active{border-color:${accent}60;background:${accent}08}
    .ra-modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.75);backdrop-filter:blur(8px);z-index:100;display:flex;align-items:center;justify-content:center;padding:20px}
    .ra-modal{background:var(--bg-base);border:1px solid var(--border);border-radius:16px;width:100%;max-width:900px;max-height:90vh;display:flex;flex-direction:column;box-shadow:var(--shadow-card);overflow:hidden}
    .ra-modal-header{padding:24px 30px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;background:var(--bg-card)}
    .ra-modal-body{padding:30px;overflow-y:auto;flex:1}
    .ra-modal-footer{padding:20px 30px;border-top:1px solid var(--border);background:var(--bg-card);display:flex;justify-content:flex-end;gap:12px}
    .story-card{background:var(--bg-card);border:1px solid var(--border);border-radius:14px;padding:18px;margin-bottom:18px}
    .task-badge{font-size:10px;font-weight:800;text-transform:uppercase;padding:3px 7px;border-radius:999px;background:rgba(139,92,246,.15);color:#a78bfa}
    .task-badge.frontend{background:rgba(59,130,246,.15);color:#60a5fa}.task-badge.qa{background:rgba(245,158,11,.15);color:#fbbf24}
    .ra-btn-primary{display:inline-flex;align-items:center;gap:8px;padding:11px 24px;background:linear-gradient(135deg,${accent},#ec4899);border:none;border-radius:12px;color:white;font-family:'DM Sans',sans-serif;font-size:14px;font-weight:700;cursor:pointer}
    .ra-btn-primary:disabled{opacity:.5;cursor:not-allowed}
    .ra-btn-ghost{display:inline-flex;align-items:center;gap:7px;padding:9px 16px;background:var(--bg-card);border:1px solid var(--border);border-radius:9px;color:var(--text-secondary);font-family:'DM Sans',sans-serif;font-size:13px;font-weight:500;cursor:pointer}
    .ra-select{width:100%;padding:9px 12px;background:var(--bg-input);border:1px solid rgba(99,102,241,.25);border-radius:12px;color:var(--text-primary);font-size:14px;outline:none}
    .ra-select option{background:var(--bg-base);color:var(--text-primary)}
    .pulse-dot{width:8px;height:8px;border-radius:50%;background:#fbbf24;animation:pulse 1.4s ease-in-out infinite}
    @keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.8)}}
  `}</style>
);

export function PrdUploadDropZone({
  accent,
  uploading,
  onFile,
  disabledMessage,
}: {
  accent: string;
  uploading: boolean;
  onFile: (file: File) => void;
  disabledMessage?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const openPicker = () => {
    if (disabledMessage) {
      alert(disabledMessage);
      return;
    }
    inputRef.current?.click();
  };
  return (
    <>
      <WorkflowStyles accent={accent} />
      <div
        className={`ra-upload-drop-zone${dragOver ? " active" : ""}`}
        onDrop={e => {
          e.preventDefault();
          setDragOver(false);
          const file = e.dataTransfer.files[0];
          if (file) onFile(file);
        }}
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onClick={openPicker}
      >
        {uploading ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
            <div className="pulse-dot" style={{ background: accent }} />
            <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>Extracting AI Requirements...</div>
          </div>
        ) : (
          <>
            <div style={{ width: 40, height: 40, borderRadius: "50%", background: "var(--bg-card-hover)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 12px" }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            </div>
            <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 4 }}>Drop your PRD here or <span style={{ color: accent }}>browse</span></div>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>PDF, Markdown, text, or spreadsheet</div>
          </>
        )}
      </div>
      <input ref={inputRef} type="file" accept=".pdf,.xlsx,.xls,.md,.txt,.csv" style={{ display: "none" }} onChange={e => { const file = e.target.files?.[0]; if (file) onFile(file); }} />
    </>
  );
}

export function ExtractedRequirementsReviewModal({
  accent,
  stories,
  contributors,
  selectedTaskIds,
  setSelectedTaskIds,
  onClose,
  onConfirm,
  onEdit,
  onMerge,
  onTaskUpdate,
}: {
  accent: string;
  stories: Story[];
  contributors: Contributor[];
  selectedTaskIds: number[];
  setSelectedTaskIds: (ids: number[]) => void;
  onClose: () => void;
  onConfirm: () => void;
  onEdit: (type: "story" | "ac" | "story_desc" | "task", storyId: number, text: string, title: string, itemId?: number) => void;
  onMerge: (storyId: number) => void;
  onTaskUpdate: (taskId: number, patch: Partial<Task>) => void;
}) {
  if (!stories.length) return null;
  return (
    <>
      <WorkflowStyles accent={accent} />
      <div className="ra-modal-overlay">
        <div className="ra-modal">
          <div className="ra-modal-header">
            <div>
              <h2 style={{ margin: 0, fontSize: 20, color: "var(--text-primary)", fontFamily: "'Syne', sans-serif" }}>Review Extracted Requirements</h2>
              <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>AI has extracted {stories.length} user stories. Review, edit if needed, and confirm to proceed.</div>
            </div>
            <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 20, lineHeight: 1 }}>x</button>
          </div>
          <div className="ra-modal-body">
            {stories.map(story => {
              const selectedInStory = story.technical_tasks.filter(task => selectedTaskIds.includes(task.id));
              return (
                <div key={story.id} className="story-card">
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                    <span style={{ color: accent, fontWeight: 700, fontSize: 14 }}>{story.story_code}</span>
                    <span style={{ color: "var(--text-primary)", fontSize: 16, fontWeight: 600 }}>{story.title}</span>
                    <button onClick={() => onEdit("story", story.id, story.title, "Edit Story Title")} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>Edit</button>
                  </div>
                  <div style={{ fontSize: 13.5, color: "var(--text-secondary)", marginBottom: 16, background: "var(--bg-input)", padding: 12, borderRadius: 8 }}>
                    {story.description}
                    <button onClick={() => onEdit("story_desc", story.id, story.description, "Edit Story Description")} style={{ marginLeft: 12, background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>Edit</button>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: "rgba(167,139,250,0.8)", textTransform: "uppercase", letterSpacing: ".8px", marginBottom: 8 }}>Acceptance Criteria</div>
                      <div style={{ display: "grid", gap: 6 }}>
                        {story.acceptance_criteria.map(ac => (
                          <div key={ac.id} style={{ color: "var(--text-secondary)", fontSize: 13, lineHeight: 1.6, background: "var(--bg-card-hover)", padding: "6px 8px", borderRadius: 6 }}>
                            {ac.text}
                            <button onClick={() => onEdit("ac", story.id, ac.text, "Edit Acceptance Criteria", ac.id)} style={{ marginLeft: 8, background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>Edit</button>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: "rgba(167,139,250,0.8)", textTransform: "uppercase", letterSpacing: ".8px", marginBottom: 8, display: "flex", justifyContent: "space-between" }}>
                        <span>Technical Tasks</span>
                        {selectedInStory.length >= 2 && <button className="ra-btn-primary" style={{ padding: "4px 10px", fontSize: 11 }} onClick={() => onMerge(story.id)}>Merge {selectedInStory.length}</button>}
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {story.technical_tasks.map(task => (
                          <div key={task.id} style={{ background: "var(--bg-card-hover)", padding: "10px 12px", borderRadius: 8, border: "1px solid var(--border)" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                <input type="checkbox" checked={selectedTaskIds.includes(task.id)} onChange={e => setSelectedTaskIds(e.target.checked ? [...selectedTaskIds, task.id] : selectedTaskIds.filter(id => id !== task.id))} style={{ width: 14, height: 14, cursor: "pointer", accentColor: accent }} />
                                <span className={`task-badge ${task.type}`}>{task.type}</span>
                              </div>
                              <button onClick={() => onEdit("task", story.id, task.description, "Edit Technical Task", task.id)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>Edit</button>
                            </div>
                            <div style={{ fontSize: 13, color: "var(--text-primary)", lineHeight: 1.4 }}>{task.description}</div>
                            {!!task.ac_ids?.length && <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>Covers AC: {task.ac_ids.map(id => `#${id}`).join(", ")}</div>}
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 10 }}>
                              <select className="ra-select" value={task.assigned_to ?? ""} onChange={e => onTaskUpdate(task.id, { assigned_to: e.target.value ? Number(e.target.value) : null })} style={{ padding: "7px 9px", fontSize: 12 }}>
                                <option value="">Unassigned</option>
                                {contributors.filter(c => !task.type || !c.specialization || c.specialization === task.type).map(c => <option key={c.id} value={c.id}>{c.full_name || c.username}</option>)}
                              </select>
                              <select className="ra-select" value={task.status || "todo"} onChange={e => onTaskUpdate(task.id, { status: e.target.value })} style={{ padding: "7px 9px", fontSize: 12 }}>
                                <option value="todo">To Do</option>
                                <option value="in_progress">In Progress</option>
                                <option value="done">Done</option>
                              </select>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="ra-modal-footer">
            <button className="ra-btn-ghost" onClick={onClose}>Cancel</button>
            <button className="ra-btn-primary" onClick={onConfirm}>Confirm & Publish</button>
          </div>
        </div>
      </div>
    </>
  );
}
