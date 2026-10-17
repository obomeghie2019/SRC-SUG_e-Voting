import { useEffect, useState } from "react";
import api, { assetUrl, errMsg } from "../api";
import { useConfig } from "../App.jsx";

export default function Settings() {
  const { reload } = useConfig();
  const [s, setS] = useState(null);
  const [msg, setMsg] = useState({ type: "", text: "" });
  const [resetText, setResetText] = useState("");

  const load = () => api.get("/admin/settings").then((r) => setS(r.data));
  useEffect(() => { load(); }, []);
  const flash = (type, text) => setMsg({ type, text });

  async function save(e) {
    e.preventDefault();
    try {
      const { election_status, ...rest } = s;
      await api.put("/admin/settings", rest);
      await reload(); flash("success", "Settings saved. Web and mobile apps now use them.");
    } catch (ex) { flash("danger", errMsg(ex)); }
  }
  async function uploadLogo(e) {
    const file = e.target.files[0]; if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    try { const { data } = await api.post("/admin/settings/logo", fd); setS((cur) => ({ ...cur, logo_url: data.logo_url })); await reload(); flash("success", "Logo updated."); }
    catch (ex) { flash("danger", errMsg(ex, "Could not upload the logo.")); }
    e.target.value = "";
  }
  async function removeLogo() {
    try { await api.delete("/admin/settings/logo"); setS((cur) => ({ ...cur, logo_url: "" })); await reload(); flash("success", "Logo removed."); }
    catch (ex) { flash("danger", errMsg(ex)); }
  }
  async function setStatus(status) {
    try { await api.post("/admin/election/status", { status }); await load(); await reload(); flash("success", `Election is now ${status}.`); }
    catch (ex) { flash("danger", errMsg(ex)); }
  }
  async function reset() {
    try { await api.post("/admin/election/reset", { confirm: resetText }); setResetText(""); await load(); await reload(); flash("success", "All votes cleared. Election returned to draft."); }
    catch (ex) { flash("danger", errMsg(ex)); }
  }

  if (!s) return "Loading";
  const set = (k) => (e) => setS({ ...s, [k]: e.target.type === "checkbox" ? String(e.target.checked) : e.target.value });

  return (
    <div className="row g-4">
      <div className="col-lg-7">
        {msg.text && <div className={`alert alert-${msg.type}`}>{msg.text}</div>}
        <form className="card p-4" onSubmit={save}>
          <h1 className="h5 mb-3">Institution and election details</h1>
          <label className="form-label">Institution name</label>
          <input className="form-control mb-3" value={s.institution_name} onChange={set("institution_name")} required />
          <label className="form-label">Election title</label>
          <input className="form-control mb-3" value={s.election_title} onChange={set("election_title")} required />
          <label className="form-label">School logo</label>
          <div className="d-flex align-items-center gap-3 mb-3">
            {s.logo_url ? <img src={assetUrl(s.logo_url)} alt="Logo" height="56" className="border rounded p-1 bg-white" /> : <div className="avatar bg-brand">{(s.institution_name || "E")[0]}</div>}
            <div className="flex-grow-1">
              <input type="file" accept="image/png,image/jpeg,image/gif,image/webp" className="form-control form-control-sm" onChange={uploadLogo} />
              <div className="form-text">PNG, JPG, GIF or WebP, up to 2 MB. A square or wide logo on a plain background works best.</div>
            </div>
            {s.logo_url && <button type="button" className="btn btn-sm btn-outline-danger" onClick={removeLogo}>Remove</button>}
          </div>
          <label className="form-label">Theme colour (web)</label>
          <input type="color" className="form-control form-control-color mb-3" value={s.theme_color} onChange={set("theme_color")} />
          <div className="form-check mb-4">
            <input id="sr" type="checkbox" className="form-check-input" checked={s.show_results_to_voters === "true"} onChange={set("show_results_to_voters")} />
            <label htmlFor="sr" className="form-check-label">Show final results to voters in the mobile app after the election closes</label>
          </div>
          <button className="btn btn-primary align-self-start">Save settings</button>
        </form>
      </div>

      <div className="col-lg-5">
        <div className="card p-4 mb-4">
          <h2 className="h5">Election status: {s.election_status}</h2>
          <p className="small text-secondary">Positions and candidates can only be added or removed while the election is a draft.</p>
          <div className="d-flex gap-2 flex-wrap">
            <button className="btn btn-primary" disabled={s.election_status === "open"} onClick={() => setStatus("open")}>Open voting</button>
            <button className="btn btn-outline-primary" disabled={s.election_status !== "open"} onClick={() => setStatus("closed")}>Close voting</button>
          </div>
        </div>
        <div className="card p-4 border-danger-subtle">
          <h2 className="h5">Clear all votes</h2>
          <p className="small text-secondary">Deletes every vote and receipt, then returns the election to draft. Use after a test run.</p>
          <input className="form-control mb-2" placeholder='Type RESET to confirm' value={resetText} onChange={(e) => setResetText(e.target.value)} />
          <button className="btn btn-danger" disabled={resetText !== "RESET"} onClick={reset}>Clear all votes</button>
        </div>
      </div>
    </div>
  );
}
