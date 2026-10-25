import { useEffect, useState } from "react";
import api, { assetUrl, errMsg } from "../api";
import { useConfig } from "../App.jsx";
import CsvTemplatePanel from "./CsvTemplatePanel.jsx";

const blank = { full_name: "", department: "", level: "", manifesto: "", photo_url: "" };

function CandidateForm({ initial, onSave, onCancel }) {
  const [c, setC] = useState(initial);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState("");
  const pick = (e) => {
    const f = e.target.files[0] || null;
    if (f && f.size > 2 * 1024 * 1024) { alert("That image is larger than 2 MB. Choose a smaller one."); e.target.value = ""; return; }
    setFile(f); setPreview(f ? URL.createObjectURL(f) : "");
  };
  const f = (k, label, extra = {}) => (
    <div className="col-md-6"><label className="form-label small mb-1">{label}</label>
      <input className="form-control form-control-sm" value={c[k]} onChange={(e) => setC({ ...c, [k]: e.target.value })} {...extra} /></div>
  );
  return (
    <div className="row g-2 bg-light p-3 rounded mb-2">
      {f("full_name", "Full name", { required: true })}
      <div className="col-md-6"><label className="form-label small mb-1">Photo (PNG, JPG, GIF or WebP, up to 2 MB)</label>
        <div className="d-flex align-items-center gap-2">
          {(preview || c.photo_url) && <img src={preview || assetUrl(c.photo_url)} alt="" className="avatar" />}
          <input type="file" accept="image/png,image/jpeg,image/gif,image/webp" className="form-control form-control-sm" onChange={pick} />
        </div></div>
      {f("department", "Department")}{f("level", "Level")}
      <div className="col-12"><label className="form-label small mb-1">Manifesto</label>
        <textarea className="form-control form-control-sm" rows="2" value={c.manifesto} onChange={(e) => setC({ ...c, manifesto: e.target.value })} /></div>
      <div className="col-12 d-flex gap-2">
        <button className="btn btn-sm btn-primary" disabled={!c.full_name.trim()} onClick={() => onSave(c, file)}>Save candidate</button>
        <button className="btn btn-sm btn-outline-secondary" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

const CANDIDATE_COLUMNS = [
  ["position", true, "Position title. Created if it does not exist; use the same spelling for the same position."],
  ["full_name", true, "Candidate's full name."],
  ["department", true, "Shown on the ballot."],
  ["level", true, "For example ND2 or HND1."],
  ["manifesto", false, "Short statement. Put it in quotes if it contains commas."],
  ["photo_url", false, "Leave blank. Add the photo afterwards with Edit, then choose a file."],
];
const CANDIDATE_SAMPLE = [
  ["President", "Amina Yusuf", "Computer Science", "ND2", "Better welfare...", ""],
  ["President", "Chidi Okafor", "Accountancy", "HND1", "Transparent funds...", ""],
  ["Vice President", "Ibrahim Musa", "Electrical Eng.", "ND2", "Industry links...", ""],
];
const CANDIDATE_TIPS = [
  "Open the template in Excel or Google Sheets, replace the example rows with your own, and save as CSV (comma delimited).",
  "Keep the first row (the column names) exactly as it is.",
  "Candidates already listed for a position are skipped, so you can safely upload the file again.",
  "Uploading works while voting is not open and no votes have been cast.",
];

export default function Positions() {
  const { election_status } = useConfig();
  const [list, setList] = useState([]);
  const [err, setErr] = useState("");
  const [newPos, setNewPos] = useState({ title: "", display_order: 0 });
  const [editing, setEditing] = useState(null); // {pid, cand|null}

  const load = () => api.get("/admin/positions").then((r) => setList(r.data));
  useEffect(() => { load(); }, []);
  const [imported, setImported] = useState(null);
  async function uploadCandidates(e) {
    const file = e.target.files[0]; if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    setErr("");
    try { const { data } = await api.post("/admin/candidates/import", fd); setImported(data); await load(); } catch (ex) { setErr(errMsg(ex)); }
    e.target.value = "";
  }
  // Saves the candidate first, then uploads the chosen photo (if any) to that candidate
  const savePhoto = async (id, file) => { if (file) { const fd = new FormData(); fd.append("file", file); await api.post(`/admin/candidates/${id}/photo`, fd); } };
  const run = async (fn) => { setErr(""); try { await fn(); await load(); } catch (e) { setErr(errMsg(e)); } };

  return (
    <div className="row g-4">
    <div className="col-xl-8">
      {election_status === "open" && <div className="alert alert-warning">Voting is open, so the ballot cannot be changed. Close voting in Settings to edit positions and candidates.</div>}
      {err && <div className="alert alert-danger">{err}</div>}
      <form className="card p-3 mb-4 flex-row gap-2 align-items-end flex-wrap" onSubmit={(e) => { e.preventDefault(); run(async () => { await api.post("/admin/positions", newPos); setNewPos({ title: "", display_order: list.length + 1 }); }); }}>
        <div className="flex-grow-1"><label className="form-label small mb-1">New position</label>
          <input className="form-control" placeholder="e.g. Director of Sports" value={newPos.title} onChange={(e) => setNewPos({ ...newPos, title: e.target.value })} required /></div>
        <div style={{ width: 100 }}><label className="form-label small mb-1">Order</label>
          <input className="form-control" type="number" value={newPos.display_order} onChange={(e) => setNewPos({ ...newPos, display_order: +e.target.value })} /></div>
        <button className="btn btn-primary">Add position</button>
      </form>

      <div className="card p-3 mb-4">
        <label className="form-label small mb-1">Upload candidates from a CSV file. Use the template on the right. Missing positions are created.</label>
        <input type="file" accept=".csv" className="form-control form-control-sm" onChange={uploadCandidates} />
        {imported && <div className="small mt-2">{imported.created.length} candidate(s) added, {imported.skipped.length} skipped{imported.skipped.length > 0 ? `: ${imported.skipped.slice(0, 3).map((r) => `${r.full_name || "(blank)"} (${r.reason})`).join("; ")}` : ""}.</div>}
      </div>

      {list.length === 0 && <p className="text-secondary">No positions yet. Add the first position above.</p>}
      {list.map((p) => (
        <div key={p.id} className="card p-3 mb-3">
          <div className="d-flex gap-2 mb-2">
            <input className="form-control fw-semibold" defaultValue={p.title} id={`t${p.id}`} />
            <input className="form-control" style={{ width: 90 }} type="number" defaultValue={p.display_order} id={`o${p.id}`} />
            <button className="btn btn-outline-primary" onClick={() => run(() => api.put(`/admin/positions/${p.id}`, { title: document.getElementById(`t${p.id}`).value, display_order: +document.getElementById(`o${p.id}`).value }))}>Save</button>
            <button className="btn btn-outline-danger" onClick={() => window.confirm(`Delete "${p.title}" and its candidates?`) && run(() => api.delete(`/admin/positions/${p.id}`))}>Delete</button>
          </div>
          {p.candidates.map((c) => (
            editing?.cand?.id === c.id
              ? <CandidateForm key={c.id} initial={c} onCancel={() => setEditing(null)} onSave={(v, file) => run(async () => { await api.put(`/admin/candidates/${c.id}`, { ...v, position_id: p.id }); await savePhoto(c.id, file); setEditing(null); })} />
              : <div key={c.id} className="leader-row py-2 border-top align-items-center">
                  <div className="d-flex align-items-center gap-2">
                    {c.photo_url ? <img className="avatar" src={assetUrl(c.photo_url)} alt="" /> : <div className="avatar">{c.full_name.split(" ").map((w) => w[0]).slice(0, 2).join("")}</div>}
                    <div><div className="fw-medium">{c.full_name}</div><div className="small text-secondary">{[c.department, c.level].filter(Boolean).join(", ")}</div></div>
                  </div>
                  <div className="d-flex gap-2">
                    <button className="btn btn-sm btn-outline-secondary" onClick={() => setEditing({ pid: p.id, cand: c })}>Edit</button>
                    <button className="btn btn-sm btn-outline-danger" onClick={() => window.confirm(`Remove ${c.full_name}?`) && run(() => api.delete(`/admin/candidates/${c.id}`))}>Remove</button>
                  </div>
                </div>
          ))}
          {editing?.pid === p.id && !editing.cand
            ? <CandidateForm initial={blank} onCancel={() => setEditing(null)} onSave={(v, file) => run(async () => { const { data } = await api.post("/admin/candidates", { ...v, position_id: p.id }); await savePhoto(data.id, file); setEditing(null); })} />
            : <button className="btn btn-sm btn-outline-primary align-self-start mt-2" onClick={() => setEditing({ pid: p.id, cand: null })}>Add candidate</button>}
        </div>
      ))}
    </div>
    <div className="col-xl-4">
      <CsvTemplatePanel title="Candidates CSV template" file="candidates_template.csv"
        intro="Add many candidates at once. Download the template, fill it in, then upload it on the left."
        columns={CANDIDATE_COLUMNS} sample={CANDIDATE_SAMPLE} tips={CANDIDATE_TIPS} />
    </div>
    </div>
  );
}
