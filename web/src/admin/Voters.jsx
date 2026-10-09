import { useEffect, useState } from "react";
import api, { errMsg } from "../api";

function downloadCsv(rows, name) {
  const csv = "matric_no,full_name,pin\n" + rows.map((r) => [r.matric_no, `"${r.full_name}"`, r.pin].join(",")).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = name; a.click();
}

export default function Voters() {
  const [data, setData] = useState({ total: 0, voters: [] });
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");
  const [issued, setIssued] = useState(null); // {created, skipped}

  const load = () => api.get("/admin/voters", { params: { q } }).then((r) => setData(r.data)).catch((e) => setErr(errMsg(e)));
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [q]); // eslint-disable-line

  async function upload(e) {
    const file = e.target.files[0]; if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    try { const { data } = await api.post("/admin/voters/import", fd); setIssued(data); load(); } catch (ex) { setErr(errMsg(ex)); }
    e.target.value = "";
  }
  async function resetPin(v) {
    if (!window.confirm(`Issue a new PIN for ${v.full_name}?`)) return;
    try { const { data } = await api.post(`/admin/voters/${v.id}/reset-pin`); setIssued({ created: [data], skipped: [] }); } catch (ex) { setErr(errMsg(ex)); }
  }
  async function toggle(v) { await api.post(`/admin/voters/${v.id}/active`, null, { params: { active: !v.is_active } }); load(); }

  return (
    <>
      {err && <div className="alert alert-danger">{err}</div>}
      {issued && (
        <div className="alert alert-warning">
          <strong>{issued.created.length} PIN(s) issued.</strong> PINs are shown only now and are stored hashed. Download them before leaving this page.
          {issued.skipped.length > 0 && <div className="small mt-1">{issued.skipped.length} row(s) skipped (duplicates or missing fields).</div>}
          <div className="mt-2 d-flex gap-2">
            <button className="btn btn-sm btn-primary" onClick={() => downloadCsv(issued.created, "voter-pins.csv")}>Download PIN list</button>
            <button className="btn btn-sm btn-outline-secondary" onClick={() => setIssued(null)}>Dismiss</button>
          </div>
        </div>
      )}
      <div className="card p-3 mb-3 flex-row flex-wrap gap-3 align-items-center">
        <div><label className="form-label small mb-1">Import voters (CSV: matric_no, full_name, email, department, level)</label>
          <input type="file" accept=".csv" className="form-control form-control-sm" onChange={upload} /></div>
        <div className="ms-auto" style={{ minWidth: 240 }}><label className="form-label small mb-1">Search</label>
          <input className="form-control form-control-sm" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Matric number or name" /></div>
      </div>
      <div className="card"><div className="table-responsive"><table className="table table-hover align-middle mb-0">
        <thead><tr><th>Matric no.</th><th>Name</th><th>Department</th><th>Level</th><th>Status</th><th></th></tr></thead>
        <tbody>
          {data.voters.map((v) => (
            <tr key={v.id}>
              <td>{v.matric_no}</td><td>{v.full_name}</td><td>{v.department}</td><td>{v.level}</td>
              <td>{!v.is_active ? <span className="badge text-bg-dark">Disabled</span> : v.has_voted ? <span className="badge text-bg-success">Voted</span> : <span className="badge text-bg-light border">Not voted</span>}</td>
              <td className="text-end text-nowrap">
                <button className="btn btn-sm btn-outline-secondary me-1" onClick={() => resetPin(v)}>New PIN</button>
                <button className="btn btn-sm btn-outline-secondary" onClick={() => toggle(v)}>{v.is_active ? "Disable" : "Enable"}</button>
              </td>
            </tr>
          ))}
          {data.voters.length === 0 && <tr><td colSpan="6" className="text-center text-secondary py-4">No voters yet. Import a CSV to register voters.</td></tr>}
        </tbody>
      </table></div>
      <div className="card-footer small text-secondary">Showing {data.voters.length} of {data.total}</div></div>
    </>
  );
}
