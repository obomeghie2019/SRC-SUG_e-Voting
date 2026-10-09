import { useEffect, useState } from "react";
import api, { errMsg } from "../api";

const blank = { full_name: "", department: "", level: "", manifesto: "", photo_url: "" };

function CandidateForm({ initial, onSave, onCancel }) {
  const [c, setC] = useState(initial);
  const f = (k, label, extra = {}) => (
    <div className="col-md-6"><label className="form-label small mb-1">{label}</label>
      <input className="form-control form-control-sm" value={c[k]} onChange={(e) => setC({ ...c, [k]: e.target.value })} {...extra} /></div>
  );
  return (
    <div className="row g-2 bg-light p-3 rounded mb-2">
      {f("full_name", "Full name", { required: true })}{f("photo_url", "Photo URL")}
      {f("department", "Department")}{f("level", "Level")}
      <div className="col-12"><label className="form-label small mb-1">Manifesto</label>
        <textarea className="form-control form-control-sm" rows="2" value={c.manifesto} onChange={(e) => setC({ ...c, manifesto: e.target.value })} /></div>
      <div className="col-12 d-flex gap-2">
        <button className="btn btn-sm btn-primary" disabled={!c.full_name.trim()} onClick={() => onSave(c)}>Save candidate</button>
        <button className="btn btn-sm btn-outline-secondary" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

export default function Positions() {
  const [list, setList] = useState([]);
  const [err, setErr] = useState("");
  const [newPos, setNewPos] = useState({ title: "", display_order: 0 });
  const [editing, setEditing] = useState(null); // {pid, cand|null}

  const load = () => api.get("/admin/positions").then((r) => setList(r.data));
  useEffect(() => { load(); }, []);
  const run = async (fn) => { setErr(""); try { await fn(); await load(); } catch (e) { setErr(errMsg(e)); } };

  return (
    <div style={{ maxWidth: 900 }}>
      {err && <div className="alert alert-danger">{err}</div>}
      <form className="card p-3 mb-4 flex-row gap-2 align-items-end flex-wrap" onSubmit={(e) => { e.preventDefault(); run(async () => { await api.post("/admin/positions", newPos); setNewPos({ title: "", display_order: list.length + 1 }); }); }}>
        <div className="flex-grow-1"><label className="form-label small mb-1">New position</label>
          <input className="form-control" placeholder="e.g. Director of Sports" value={newPos.title} onChange={(e) => setNewPos({ ...newPos, title: e.target.value })} required /></div>
        <div style={{ width: 100 }}><label className="form-label small mb-1">Order</label>
          <input className="form-control" type="number" value={newPos.display_order} onChange={(e) => setNewPos({ ...newPos, display_order: +e.target.value })} /></div>
        <button className="btn btn-primary">Add position</button>
      </form>

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
              ? <CandidateForm key={c.id} initial={c} onCancel={() => setEditing(null)} onSave={(v) => run(async () => { await api.put(`/admin/candidates/${c.id}`, { ...v, position_id: p.id }); setEditing(null); })} />
              : <div key={c.id} className="leader-row py-2 border-top align-items-center">
                  <div><div className="fw-medium">{c.full_name}</div><div className="small text-secondary">{[c.department, c.level].filter(Boolean).join(", ")}</div></div>
                  <div className="d-flex gap-2">
                    <button className="btn btn-sm btn-outline-secondary" onClick={() => setEditing({ pid: p.id, cand: c })}>Edit</button>
                    <button className="btn btn-sm btn-outline-danger" onClick={() => window.confirm(`Remove ${c.full_name}?`) && run(() => api.delete(`/admin/candidates/${c.id}`))}>Remove</button>
                  </div>
                </div>
          ))}
          {editing?.pid === p.id && !editing.cand
            ? <CandidateForm initial={blank} onCancel={() => setEditing(null)} onSave={(v) => run(async () => { await api.post("/admin/candidates", { ...v, position_id: p.id }); setEditing(null); })} />
            : <button className="btn btn-sm btn-outline-primary align-self-start mt-2" onClick={() => setEditing({ pid: p.id, cand: null })}>Add candidate</button>}
        </div>
      ))}
    </div>
  );
}
