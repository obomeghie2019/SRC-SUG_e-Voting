import { useState } from "react";
import api, { errMsg } from "../api";

// Shown instead of every page while the API reports a license problem (missing, changed, expired, clock, or hard-locked).
export default function LicenseBlocked({ info, onRetry }) {
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function unlock(e) {
    e.preventDefault(); setBusy(true); setMsg("");
    try { await api.post("/license/unlock", { token: code.trim() }); setCode(""); onRetry(); }
    catch (ex) { setMsg(errMsg(ex, "That code was not accepted.")); }
    finally { setBusy(false); }
  }

  const title = { expired: "License expired", locked: "Application locked", clock: "Check the server date and time" }[info.kind] || "License problem";

  return (
    <div className="container py-5" style={{ maxWidth: 560 }}>
      <div className="card shadow-sm p-4 border-danger">
        <h1 className="h4 text-danger mb-2">{title}</h1>
        <p className="mb-3">{info.message}</p>
        {info.licensee && <p className="small text-secondary mb-3">Licensed to {info.licensee}{info.expires ? `, valid until ${info.expires}` : ""}.</p>}

        {info.locked && (
          <form onSubmit={unlock} className="mb-3">
            <div className="small mb-1">Lock ID: <code>{info.lock_id}</code>. Send this ID to the system vendor, then enter the unlock code you receive.</div>
            <input className="form-control mb-2" placeholder="Unlock code" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="off" />
            {msg && <div className="alert alert-danger py-2 small">{msg}</div>}
            <button className="btn btn-danger btn-sm" disabled={busy || code.trim().length < 20}>{busy ? "Checking" : "Unlock"}</button>
          </form>
        )}

        <div>
          <button className="btn btn-outline-secondary btn-sm" onClick={onRetry}>Check again</button>
        </div>
        <p className="small text-secondary mt-3 mb-0">No election data has been changed or removed. The application resumes as soon as a valid license is in place.</p>
      </div>
    </div>
  );
}
