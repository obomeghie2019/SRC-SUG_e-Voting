import { useEffect, useState } from "react";
import api, { errMsg } from "../api";
import { useConfig } from "../App.jsx";

const COLS = [
  ["cast_at", "Time"], ["matric_no", "Matric no."], ["full_name", "Name"], ["department", "Dept"], ["level", "Level"],
  ["email", "Email"], ["phone", "Phone"], ["app", "App"], ["otp_channel", "OTP via"], ["ip", "IP address"],
  ["latitude", "Latitude"], ["longitude", "Longitude"], ["accuracy_m", "Accuracy (m)"], ["device_id", "Device"], ["receipt_code", "Receipt"],
];

const when = (iso) => (iso ? new Date(iso).toLocaleString() : "");
const fmt = (k, v) => (k === "cast_at" ? when(v) : k === "device_id" ? (v || "").slice(0, 8) : k === "accuracy_m" && v != null ? Math.round(v) : (v ?? ""));
const mapUrl = (r) => `https://www.openstreetmap.org/?mlat=${r.latitude}&mlon=${r.longitude}#map=17/${r.latitude}/${r.longitude}`;

function exportCsv(rows, name) {
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const head = [...COLS.map(([, l]) => l), "Shared IP", "Shared device", "No location"];
  const body = rows.map((r) => [...COLS.map(([k]) => esc(r[k])), r.shared_ip, r.shared_device, r.no_location].join(","));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([head.join(",") + "\n" + body.join("\n")], { type: "text/csv" }));
  a.download = name; a.click();
}

export default function Forensics() {
  const { institution_name, election_title } = useConfig();
  const [data, setData] = useState({ summary: {}, rows: [] });
  const [events, setEvents] = useState([]);
  const [q, setQ] = useState("");
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [tab, setTab] = useState("votes");
  const [err, setErr] = useState("");
  const [generated, setGenerated] = useState(new Date());

  const load = () => {
    api.get("/admin/reports/forensic", { params: { q } }).then((r) => { setData(r.data); setGenerated(new Date()); }).catch((e) => setErr(errMsg(e)));
    api.get("/admin/reports/events", { params: { limit: 500 } }).then((r) => setEvents(r.data)).catch(() => {});
  };
  useEffect(() => { const t = setTimeout(load, 300); return () => clearTimeout(t); }, [q]); // eslint-disable-line

  const s = data.summary;
  const rows = flaggedOnly ? data.rows.filter((r) => r.shared_ip || r.shared_device || r.no_location) : data.rows;
  const cards = [["Votes cast", s.total_votes], ["Distinct IPs", s.distinct_ips], ["Shared-IP votes", s.shared_ip_votes],
    ["Shared-device votes", s.shared_device_votes], ["Without location", s.votes_without_location], ["Failed code attempts", s.failed_otp_attempts]];

  return (
    <>
      <div className="print-only mb-3">
        <h1 className="h5 mb-0">{institution_name}: {election_title}</h1>
        <div>Forensic voting report. Generated {generated.toLocaleString()}. Shows who voted, when, from where; it does not show how anyone voted.</div>
      </div>

      <div className="no-print">
        {err && <div className="alert alert-danger">{err}</div>}
        <div className="d-flex flex-wrap gap-2 align-items-end mb-3">
          <div style={{ minWidth: 260 }}><label className="form-label small mb-1">Search matric, name or IP</label>
            <input className="form-control form-control-sm" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          <div className="form-check mb-1"><input id="fl" type="checkbox" className="form-check-input" checked={flaggedOnly} onChange={(e) => setFlaggedOnly(e.target.checked)} />
            <label htmlFor="fl" className="form-check-label small">Flagged only</label></div>
          <div className="ms-auto d-flex gap-2">
            <button className="btn btn-sm btn-outline-secondary" onClick={load}>Refresh</button>
            <button className="btn btn-sm btn-outline-primary" onClick={() => exportCsv(rows, "forensic-report.csv")}>Download CSV</button>
            <button className="btn btn-sm btn-primary" onClick={() => window.print()}>Print report</button>
          </div>
        </div>
        <div className="row g-2 mb-3">
          {cards.map(([label, v]) => (
            <div key={label} className="col-6 col-md-4 col-xl-2"><div className="card p-2 h-100"><div className="small text-secondary">{label}</div><div className="stat fs-4">{v ?? 0}</div></div></div>
          ))}
        </div>
        <ul className="nav nav-tabs mb-3">
          {[["votes", "Votes (who, when, where)"], ["events", "Security events"]].map(([k, l]) => (
            <li key={k} className="nav-item"><button className={"nav-link " + (tab === k ? "active" : "")} onClick={() => setTab(k)}>{l}</button></li>
          ))}
        </ul>
      </div>

      {tab === "votes" && (
        <div className="card"><div className="table-responsive"><table className="table table-sm table-hover align-middle mb-0">
          <thead><tr>{COLS.map(([k, l]) => <th key={k}>{l}</th>)}<th>Flags</th><th className="no-print">Map</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.receipt_code}>
                {COLS.map(([k]) => <td key={k} className="text-nowrap">{fmt(k, r[k])}</td>)}
                <td className="text-nowrap">
                  {r.shared_ip && <span className="badge text-bg-warning me-1">Shared IP</span>}
                  {r.shared_device && <span className="badge text-bg-warning me-1">Shared device</span>}
                  {r.no_location && <span className="badge text-bg-danger">No location</span>}
                </td>
                <td className="no-print">{!r.no_location && <a href={mapUrl(r)} target="_blank" rel="noreferrer">Map</a>}</td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={COLS.length + 2} className="text-center text-secondary py-4">No votes recorded yet.</td></tr>}
          </tbody>
        </table></div>
        <div className="card-footer small text-secondary">{rows.length} record(s). Location comes from the voter's device and can be faked; compare it with the IP address.</div></div>
      )}

      {tab === "events" && (
        <div className="card no-print"><div className="table-responsive"><table className="table table-sm mb-0">
          <thead><tr><th>Time</th><th>Event</th><th>Matric no.</th><th>IP address</th><th>Latitude</th><th>Longitude</th><th>Detail</th></tr></thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id}><td className="text-nowrap">{when(e.at)}</td><td><span className={"badge text-bg-" + (/failed/.test(e.event) ? "danger" : "light border")}>{e.event}</span></td>
                <td>{e.matric_no}</td><td>{e.ip}</td><td>{e.latitude ?? ""}</td><td>{e.longitude ?? ""}</td><td>{e.detail}</td></tr>
            ))}
            {events.length === 0 && <tr><td colSpan="7" className="text-center text-secondary py-4">No events yet.</td></tr>}
          </tbody>
        </table></div></div>
      )}
    </>
  );
}
