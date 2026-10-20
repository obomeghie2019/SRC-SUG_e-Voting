import { useEffect, useState } from "react";
import api, { errMsg } from "../api";

// Field labels per SMS provider (the backend stores them in the same three fields)
const PROVIDERS = {
  "": { name: "None (SMS off)", fields: [] },
  termii: { name: "Termii", fields: [["sms_api_key", "API key", true], ["sms_sender_id", "Sender ID (must be approved by Termii)", false]] },
  africastalking: { name: "Africa's Talking", fields: [["sms_username", "Username", false], ["sms_api_key", "API key", true], ["sms_sender_id", "Sender ID (optional)", false]] },
  twilio: { name: "Twilio", fields: [["sms_username", "Account SID (starts with AC)", false], ["sms_api_key", "Auth token", true], ["sms_sender_id", "From: your Twilio number (+1202...), a Messaging Service SID (MG...), or a sender name of up to 11 letters/digits", false]] },
};

function Status({ title, ready, missing }) {
  return (
    <div className="card p-3 h-100">
      <div className="small text-secondary">{title}</div>
      <div className={"fw-semibold " + (ready ? "text-success" : "text-danger")}>{ready ? "Ready" : "Not set up"}</div>
      {!ready && missing?.length > 0 && <div className="small text-secondary">Missing: {missing.join(", ")}</div>}
    </div>
  );
}

export default function Delivery() {
  const [d, setD] = useState(null);                 // what the server returned
  const [f, setF] = useState({});                   // edited values
  const [secrets, setSecrets] = useState({ smtp_password: "", sms_api_key: "" });
  const [clear, setClear] = useState({ smtp_password: false, sms_api_key: false });
  const [msg, setMsg] = useState({ type: "", text: "" });
  const [testTo, setTestTo] = useState({ email: "", sms: "" });
  const [busy, setBusy] = useState("");

  const apply = (data) => { setD(data); setF({ ...data }); setSecrets({ smtp_password: "", sms_api_key: "" }); setClear({ smtp_password: false, sms_api_key: false }); };
  const load = () => api.get("/admin/delivery").then((r) => apply(r.data)).catch((e) => setMsg({ type: "danger", text: errMsg(e) }));
  useEffect(() => { load(); }, []);
  const flash = (type, text) => { setMsg({ type, text }); window.scrollTo({ top: 0, behavior: "smooth" }); };
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  async function save(e) {
    e.preventDefault(); setBusy("save");
    const body = {
      smtp_host: f.smtp_host, smtp_port: Number(f.smtp_port), smtp_user: f.smtp_user, smtp_from: f.smtp_from, smtp_starttls: !!f.smtp_starttls,
      sms_provider: f.sms_provider, sms_username: f.sms_username, sms_sender_id: f.sms_sender_id,
      default_country_code: f.default_country_code, otp_dev_mode: !!f.otp_dev_mode,
      otp_ttl_minutes: Number(f.otp_ttl_minutes), otp_max_attempts: Number(f.otp_max_attempts), otp_send_limit: Number(f.otp_send_limit),
      clear_secrets: Object.keys(clear).filter((k) => clear[k]),
    };
    if (secrets.smtp_password) body.smtp_password = secrets.smtp_password;   // blank = keep the saved one
    if (secrets.sms_api_key) body.sms_api_key = secrets.sms_api_key;
    try { const { data } = await api.put("/admin/delivery", body); apply(data); flash("success", "Saved. Voters see the new options immediately; no restart is needed."); }
    catch (ex) { flash("danger", errMsg(ex)); }
    finally { setBusy(""); }
  }

  async function test(kind) {
    setBusy(kind);
    try { const { data } = await api.post(`/admin/delivery/test-${kind}`, { to: testTo[kind] }); flash("success", data.message); }
    catch (ex) { flash("danger", `Test failed: ${errMsg(ex)}`); }
    finally { setBusy(""); }
  }

  // The test buttons use the SAVED settings, so they stay disabled while the form has unsaved changes.
  const FORM_KEYS = ["smtp_host", "smtp_port", "smtp_user", "smtp_from", "smtp_starttls", "sms_provider", "sms_username", "sms_sender_id", "default_country_code", "otp_dev_mode", "otp_ttl_minutes", "otp_max_attempts", "otp_send_limit"];
  const dirty = d && (FORM_KEYS.some((k) => String(f[k] ?? "") !== String(d[k] ?? "")) || secrets.smtp_password || secrets.sms_api_key || clear.smtp_password || clear.sms_api_key);

  if (!d) return msg.text ? <div className="alert alert-danger">{msg.text}</div> : "Loading";
  const src = (k) => (d.sources[k] === "env" ? <span className="badge text-bg-light border ms-1" title="Using the value from the server's .env file. Saving here overrides it.">from .env</span> : null);
  const provider = PROVIDERS[f.sms_provider] || PROVIDERS[""];
  const r = d.readiness;

  return (
    <div style={{ maxWidth: 920 }}>
      {msg.text && <div className={`alert alert-${msg.type}`}>{msg.text}</div>}

      <div className="row g-3 mb-3">
        <div className="col-md-4"><Status title="Email (SMTP)" ready={r.email.ready} missing={r.email.missing} /></div>
        <div className="col-md-4"><Status title={`SMS (${PROVIDERS[d.sms_provider]?.name || "none"})`} ready={r.sms.ready} missing={r.sms.missing} /></div>
        <div className="col-md-4"><div className="card p-3 h-100"><div className="small text-secondary">Test mode</div>
          <div className={"fw-semibold " + (r.test_mode ? "text-danger" : "text-success")}>{r.test_mode ? "ON: codes are not sent" : "Off"}</div></div></div>
      </div>

      {r.test_mode && <div className="alert alert-warning">
        <strong>Test mode is ON.</strong> One-time codes are printed in the server console and are <strong>not</strong> sent to voters. Turn it off before a real election.</div>}

      <form onSubmit={save}>
        <div className="card p-4 mb-3">
          <h1 className="h5">Email (SMTP)</h1>
          <p className="small text-secondary">Use the SMTP details from your email provider (Brevo, SendGrid, Mailgun, your school mail server, or Gmail with an app password: smtp.gmail.com, port 587).</p>
          <div className="row g-3">
            <div className="col-md-8"><label className="form-label">SMTP host {src("smtp_host")}</label><input className="form-control" value={f.smtp_host} onChange={set("smtp_host")} placeholder="smtp.example.com" /></div>
            <div className="col-md-4"><label className="form-label">Port {src("smtp_port")}</label><input className="form-control" type="number" value={f.smtp_port} onChange={set("smtp_port")} /></div>
            <div className="col-md-6"><label className="form-label">Username {src("smtp_user")}</label><input className="form-control" value={f.smtp_user} onChange={set("smtp_user")} autoComplete="off" /></div>
            <div className="col-md-6"><label className="form-label">Password {src("smtp_password")}</label>
              <input className="form-control" type="password" autoComplete="new-password" value={secrets.smtp_password} onChange={(e) => setSecrets({ ...secrets, smtp_password: e.target.value })}
                placeholder={d.secrets_set.smtp_password ? "A password is saved. Leave blank to keep it." : "Not set"} />
              {d.secrets_set.smtp_password && <div className="form-check mt-1"><input id="cp" type="checkbox" className="form-check-input" checked={clear.smtp_password} onChange={(e) => setClear({ ...clear, smtp_password: e.target.checked })} /><label htmlFor="cp" className="form-check-label small">Remove the saved password</label></div>}</div>
            <div className="col-md-8"><label className="form-label">From address {src("smtp_from")}</label><input className="form-control" value={f.smtp_from} onChange={set("smtp_from")} placeholder="votes@yourschool.edu.ng" /></div>
            <div className="col-md-4 d-flex align-items-end"><div className="form-check mb-2"><input id="tls" type="checkbox" className="form-check-input" checked={!!f.smtp_starttls} onChange={set("smtp_starttls")} /><label htmlFor="tls" className="form-check-label">Use STARTTLS</label></div></div>
          </div>
          <hr />
          <label className="form-label small mb-1">Send a test email (uses the saved settings)</label>
          <div className="input-group input-group-sm" style={{ maxWidth: 480 }}>
            <input className="form-control" type="email" placeholder="you@example.com" value={testTo.email} onChange={(e) => setTestTo({ ...testTo, email: e.target.value })} />
            <button type="button" className="btn btn-outline-primary" disabled={!testTo.email || busy === "email" || dirty} onClick={() => test("email")}>{busy === "email" ? "Sending" : "Send test email"}</button>
          </div>
        </div>

        <div className="card p-4 mb-3">
          <h2 className="h5">SMS provider</h2>
          <p className="small text-secondary">Choose the company that sends your text messages. Nigerian networks usually need a registered sender ID.</p>
          <div className="row g-3">
            <div className="col-md-5"><label className="form-label">Provider {src("sms_provider")}</label>
              <select className="form-select" value={f.sms_provider} onChange={set("sms_provider")}>
                {Object.entries(PROVIDERS).map(([k, v]) => <option key={k} value={k}>{v.name}</option>)}
              </select></div>
            {provider.fields.map(([key, label, secret]) => (
              <div key={key} className="col-md-6">
                <label className="form-label">{label} {src(key)}</label>
                {secret
                  ? <input className="form-control" type="password" autoComplete="new-password" value={secrets[key]} onChange={(e) => setSecrets({ ...secrets, [key]: e.target.value })}
                      placeholder={d.secrets_set[key] ? "Saved. Leave blank to keep it." : "Not set"} />
                  : <input className="form-control" value={f[key]} onChange={set(key)} autoComplete="off" />}
                {secret && d.secrets_set[key] && <div className="form-check mt-1"><input id={"c" + key} type="checkbox" className="form-check-input" checked={clear[key]} onChange={(e) => setClear({ ...clear, [key]: e.target.checked })} /><label htmlFor={"c" + key} className="form-check-label small">Remove the saved value</label></div>}
              </div>
            ))}
            <div className="col-md-4"><label className="form-label">Default country code {src("default_country_code")}</label><input className="form-control" value={f.default_country_code} onChange={set("default_country_code")} />
              <div className="form-text">Turns 0801... into +234801...</div></div>
          </div>
          <hr />
          <label className="form-label small mb-1">Send a test SMS (uses the saved settings)</label>
          <div className="input-group input-group-sm" style={{ maxWidth: 480 }}>
            <input className="form-control" placeholder="08012345678" value={testTo.sms} onChange={(e) => setTestTo({ ...testTo, sms: e.target.value })} />
            <button type="button" className="btn btn-outline-primary" disabled={!testTo.sms || busy === "sms" || dirty} onClick={() => test("sms")}>{busy === "sms" ? "Sending" : "Send test SMS"}</button>
          </div>
        </div>

        <div className="card p-4 mb-3">
          <h2 className="h5">One-time code rules</h2>
          <div className="row g-3">
            <div className="col-md-4"><label className="form-label">Code lasts (minutes) {src("otp_ttl_minutes")}</label><input className="form-control" type="number" min="1" max="30" value={f.otp_ttl_minutes} onChange={set("otp_ttl_minutes")} /></div>
            <div className="col-md-4"><label className="form-label">Wrong tries before lock {src("otp_max_attempts")}</label><input className="form-control" type="number" min="1" max="10" value={f.otp_max_attempts} onChange={set("otp_max_attempts")} /></div>
            <div className="col-md-4"><label className="form-label">Codes per voter per 10 min {src("otp_send_limit")}</label><input className="form-control" type="number" min="1" max="20" value={f.otp_send_limit} onChange={set("otp_send_limit")} /></div>
          </div>
          <hr />
          <div className="form-check"><input id="dev" type="checkbox" className="form-check-input" checked={!!f.otp_dev_mode} onChange={set("otp_dev_mode")} />
            <label htmlFor="dev" className="form-check-label"><strong>Test mode</strong> {src("otp_dev_mode")}: do not send codes; print them in the server console instead.</label>
            <div className="form-text text-danger">For trying the system only. Never leave it on during a real election.</div></div>
        </div>

        {dirty && <div className="alert alert-warning py-2 small">You have changes that are not saved yet. Click <strong>Save delivery settings</strong>, then use the test buttons.</div>}
        <button className="btn btn-primary" disabled={busy === "save"}>{busy === "save" ? "Saving" : "Save delivery settings"}</button>
        <span className="small text-secondary ms-3">Passwords and API keys are stored encrypted and are never shown again.</span>
      </form>
    </div>
  );
}
