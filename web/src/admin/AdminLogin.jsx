import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { errMsg } from "../api";
import Brand from "../pages/Brand.jsx";

export default function AdminLogin() {
  const nav = useNavigate();
  const [f, setF] = useState({ username: "", password: "" });
  const [err, setErr] = useState("");

  async function submit(e) {
    e.preventDefault(); setErr("");
    try {
      const { data } = await api.post("/auth/admin/login", f);
      sessionStorage.setItem("admin_token", data.token);
      nav("/admin");
    } catch (ex) { setErr(errMsg(ex, "Could not sign in.")); }
  }

  return (
    <div className="container py-5" style={{ maxWidth: 420 }}>
      <Brand />
      <form className="card mt-4 p-4 shadow-sm" onSubmit={submit}>
        <h1 className="h4 mb-4">Administrator sign in</h1>
        {err && <div className="alert alert-danger py-2">{err}</div>}
        <label className="form-label">Username</label>
        <input className="form-control mb-3" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} required autoFocus />
        <label className="form-label">Password</label>
        <input className="form-control mb-4" type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} required />
        <button className="btn btn-primary">Sign in</button>
      </form>
      <div className="text-center mt-3"><Link to="/" className="small text-secondary">Back to voter sign in</Link></div>
    </div>
  );
}
