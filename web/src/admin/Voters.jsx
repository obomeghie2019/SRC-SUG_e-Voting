import { useEffect, useState } from "react";
import api, { errMsg } from "../api";

export default function Voters() {
  const [data, setData] = useState({ total: 0, voters: [] });
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");
  const [result, setResult] = useState(null); // {created, updated, skipped}

  const load = () => api.get("/admin/voters", { params: { q } }).then((r) => setData(r.data)).catch((e) => setErr(errMsg(e)));
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [q]); // eslint-disable-line

  async function upload(e) {
    const file = e.target.files[0]; if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    try { const { data } = await api.post("/admin/voters/import", fd); setResult(data); load(); } catch (ex) { setErr(errMsg(ex)); }
    e.target.value = "";
  }
  async function editContact(v) {
    const email = window.prompt(`Email for ${v.full_name}`, v.email || "");
    if (email === null) return;
    const phone = window.prompt(`Phone for ${v.full_name} (e.g. 08012345678)`, v.phone || "");
    if (phone === null) return;
    try { await api.put(`/admin/voters/${v.id}/contact`, { email, phone }); load(); } catch (ex) { setErr(errMsg(ex)); }
  }
  async function toggle(v) { await api.post(`/admin/voters/${v.id}/active`, null, { params: { active: !v.is_active } }); load(); }

  return (
    <>
      {err && <div className="alert alert-danger">{err}</div>}
      {result && (
        <div className="alert alert-info">
          <strong>Import finished:</strong> {result.created.length} added, {result.updated.length} contact(s) updated, {result.skipped.length} skipped.
          {result.skipped.length > 0 && <div className="small mt-1">{result.skipped.slice(0, 5).map((r) => `${r.matric_no || "(blank)"}: ${r.reason}`).join("; ")}{result.skipped.length > 5 ? "; ..." : ""}</div>}
          <div className="small mt-1">Voters sign in with their matric number and a one-time code sent to the email or phone listed here.</div>
          <button className="btn btn-sm btn-outline-secondary mt-2" onClick={() => setResult(null)}>Dismiss</button>
        </div>
      )}
      <div className="card p-3 mb-3 flex-row flex-wrap gap-3 align-items-center">
        <div><label className="form-label small mb-1">Import voters (CSV: matric_no, full_name, email, phone, department, level). Re-importing updates email and phone.</label>
          <input type="file" accept=".csv" className="form-control form-control-sm" onChange={upload} /></div>
        <div className="ms-auto" style={{ minWidth: 240 }}><label className="form-label small mb-1">Search</label>
          <input className="form-control form-control-sm" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Matric number or name" /></div>
      </div>
      <div className="card"><div className="table-responsive"><table className="table table-hover align-middle mb-0">
        <thead><tr><th>Matric no.</th><th>Name</th><th>Email</th><th>Phone</th><th>Department</th><th>Level</th><th>Status</th><th></th></tr></thead>
        <tbody>
          {data.voters.map((v) => (
            <tr key={v.id}>
              <td>{v.matric_no}</td><td>{v.full_name}</td><td>{v.email || <span className="text-danger small">none</span>}</td><td>{v.phone || <span className="text-danger small">none</span>}</td><td>{v.department}</td><td>{v.level}</td>
              <td>{!v.is_active ? <span className="badge text-bg-dark">Disabled</span> : v.has_voted ? <span className="badge text-bg-success">Voted</span> : <span className="badge text-bg-light border">Not voted</span>}</td>
              <td className="text-end text-nowrap">
                <button className="btn btn-sm btn-outline-secondary me-1" onClick={() => editContact(v)}>Edit contact</button>
                <button className="btn btn-sm btn-outline-secondary" onClick={() => toggle(v)}>{v.is_active ? "Disable" : "Enable"}</button>
              </td>
            </tr>
          ))}
          {data.voters.length === 0 && <tr><td colSpan="8" className="text-center text-secondary py-4">No voters yet. Import a CSV to register voters.</td></tr>}
        </tbody>
      </table></div>
      <div className="card-footer small text-secondary">Showing {data.voters.length} of {data.total}</div></div>
    </>
  );
}
