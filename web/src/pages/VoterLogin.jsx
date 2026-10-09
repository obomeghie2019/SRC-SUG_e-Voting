import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { errMsg } from "../api";
import { useConfig } from "../App.jsx";
import Brand from "./Brand.jsx";

export default function VoterLogin() {
  const { election_status } = useConfig();
  const nav = useNavigate();
  const [f, setF] = useState({ matric_no: "", password: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const { data } = await api.post("/auth/login", f);
      sessionStorage.setItem("voter_token", data.token);
      nav("/ballot");
    } catch (ex) {
      setErr(errMsg(ex, "Could not sign in."));
    } finally { setBusy(false); }
  }

  const label = { draft: "Voting has not started", open: "Voting is open", closed: "Voting has closed" }[election_status];

  return (
    <div className="container py-5" style={{ maxWidth: 440 }}>
      <Brand />
      <div className="card mt-4 p-4 shadow-sm">
        <h1 className="h4 mb-1">Sign in to vote</h1>
        <p className="text-secondary small mb-4">{label}</p>
        {err && <div className="alert alert-danger py-2">{err}</div>}
        <form onSubmit={submit}>
          <label className="form-label">Matric number</label>
          <input className="form-control mb-3" value={f.matric_no} autoFocus required
            onChange={(e) => setF({ ...f, matric_no: e.target.value })} />
          <label className="form-label">Voting PIN</label>
          <input className="form-control mb-4" type="password" value={f.password} required inputMode="numeric"
            onChange={(e) => setF({ ...f, password: e.target.value })} />
          <button className="btn btn-primary w-100" disabled={busy}>{busy ? "Signing in" : "Sign in"}</button>
        </form>
      </div>
      <div className="text-center mt-3"><Link to="/admin/login" className="small text-secondary">Administrator sign in</Link></div>
    </div>
  );
}
