import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { errMsg } from "../api";
import { useConfig } from "../App.jsx";
import { deviceId, geoSupport, getPosition, watchPermission } from "../lib/geo";
import Brand from "./Brand.jsx";

const STEPS = ["Location", "Matric number", "Delivery", "Code"];

function Stepper({ step }) {
  return (
    <ol className="list-unstyled d-flex gap-2 small mb-3 flex-wrap">
      {STEPS.map((s, i) => (
        <li key={s} className={i === step ? "fw-semibold text-brand" : i < step ? "text-secondary" : "text-body-tertiary"}>
          {i + 1}. {s}{i < STEPS.length - 1 && <span className="ms-2">›</span>}
        </li>
      ))}
    </ol>
  );
}

export default function VoterLogin() {
  const { election_status, location_required } = useConfig();
  const nav = useNavigate();
  const [step, setStep] = useState(0);
  const [pos, setPos] = useState(null);          // {latitude, longitude, accuracy_m}
  const [locErr, setLocErr] = useState("");
  const [matric, setMatric] = useState("");
  const [session, setSession] = useState(null);  // {session_id, channels, otp_ttl_minutes}
  const [channel, setChannel] = useState("");
  const [sentTo, setSentTo] = useState("");
  const [code, setCode] = useState("");
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [resendIn, setResendIn] = useState(0);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const asked = useRef(false);

  async function askLocation() {
    setBusy(true); setLocErr("");
    try { setPos(await getPosition()); setStep(1); }
    catch (e) { setLocErr(e.message); }
    finally { setBusy(false); }
  }

  // Location is the first thing we ask for. If it was blocked and the voter turns it ON later, continue automatically.
  useEffect(() => {
    if (!location_required && location_required !== undefined) { setStep(1); return; }
    if (!asked.current && geoSupport().ok) { asked.current = true; askLocation(); }
    else if (!geoSupport().ok) setLocErr(geoSupport().reason);
    return watchPermission((state) => { if (state === "granted" && step === 0 && !pos) askLocation(); });
    // eslint-disable-next-line
  }, [location_required]);

  useEffect(() => {
    if (secondsLeft <= 0 && resendIn <= 0) return;
    const t = setInterval(() => { setSecondsLeft((s) => Math.max(0, s - 1)); setResendIn((s) => Math.max(0, s - 1)); }, 1000);
    return () => clearInterval(t);
  }, [secondsLeft, resendIn]);

  const fresh = async () => { try { return await getPosition({ maxAgeMs: 30000 }); } catch { return pos; } };

  async function lookup(e) {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      const p = (await fresh()) || {};
      setPos(p.latitude ? p : pos);
      const { data } = await api.post("/auth/lookup", { matric_no: matric.trim(), device_id: deviceId(), ...(p.latitude ? p : {}) });
      setSession(data);
      setChannel(data.channels.length === 1 ? data.channels[0].channel : "");
      setStep(2);
    } catch (ex) { setErr(errMsg(ex)); if (ex.response?.status === 400) setStep(0); }
    finally { setBusy(false); }
  }

  async function sendCode() {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post("/auth/otp/send", { session_id: session.session_id, channel });
      setSentTo(data.sent_to); setSecondsLeft(data.expires_in_seconds); setResendIn(30); setCode(""); setStep(3);
    } catch (ex) { setErr(errMsg(ex)); }
    finally { setBusy(false); }
  }

  async function verify(e) {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      const p = (await fresh()) || {};
      const { data } = await api.post("/auth/otp/verify", { session_id: session.session_id, otp: code.trim(), ...(p.latitude ? p : {}) });
      sessionStorage.setItem("voter_token", data.token);
      sessionStorage.setItem("voter_name", data.voter.full_name);
      nav("/ballot");
    } catch (ex) {
      setErr(errMsg(ex));
      if ([409, 410].includes(ex.response?.status)) { setStep(2); }   // expired, locked or replaced: choose and send again
    } finally { setBusy(false); }
  }

  const label = { draft: "Voting has not started", open: "Voting is open", closed: "Voting has closed" }[election_status];
  const mm = String(Math.floor(secondsLeft / 60)).padStart(2, "0"), ss = String(secondsLeft % 60).padStart(2, "0");

  return (
    <div className="container py-5" style={{ maxWidth: 460 }}>
      <Brand />
      <div className="card mt-4 p-4 shadow-sm">
        <h1 className="h4 mb-1">Sign in to vote</h1>
        <p className="text-secondary small mb-3">{label}</p>
        <Stepper step={step} />
        {err && <div className="alert alert-danger py-2">{err}</div>}

        {step === 0 && (
          <>
            <h2 className="h6">Turn on your location</h2>
            <p className="small text-secondary">Voting needs your location to confirm you are voting from an allowed place.
              Your browser will ask for permission. Choose <strong>Allow</strong>.</p>
            {locErr && <div className="alert alert-warning py-2 small">{locErr}</div>}
            <button className="btn btn-primary w-100" disabled={busy} onClick={askLocation}>{busy ? "Checking location" : "Turn on location"}</button>
            <p className="small text-secondary mt-3 mb-0">If you blocked it earlier: tap the padlock beside the web address, set Location to Allow, and this page continues by itself.</p>
          </>
        )}

        {step === 1 && (
          <form onSubmit={lookup}>
            <p className="small text-success mb-3">✓ Location is on{pos?.accuracy_m ? ` (±${Math.round(pos.accuracy_m)} m)` : ""}</p>
            <label className="form-label">Matric number</label>
            <input className="form-control mb-3" value={matric} autoFocus required onChange={(e) => setMatric(e.target.value)} />
            <button className="btn btn-primary w-100" disabled={busy || !matric.trim()}>{busy ? "Checking" : "Continue"}</button>
          </form>
        )}

        {step === 2 && session && (
          <>
            <p className="small mb-2">Where should we send your one-time code? It goes only to the contact already on record for you.</p>
            <div className="d-grid gap-2 mb-3">
              {session.channels.map((c) => (
                <label key={c.channel} className="candidate">
                  <input type="radio" className="form-check-input m-0" name="ch" checked={channel === c.channel} onChange={() => setChannel(c.channel)} />
                  <div><div className="fw-medium">{c.channel === "email" ? "Email" : "SMS"}</div><div className="small text-secondary">{c.masked}</div></div>
                </label>
              ))}
            </div>
            <button className="btn btn-primary w-100" disabled={busy || !channel} onClick={sendCode}>{busy ? "Sending" : "Send code"}</button>
            <button className="btn btn-link btn-sm w-100 mt-2" onClick={() => { setStep(1); setErr(""); }}>Use a different matric number</button>
          </>
        )}

        {step === 3 && (
          <form onSubmit={verify}>
            <p className="small mb-2">We sent a 6-digit code to <strong>{sentTo}</strong>.{secondsLeft > 0 ? ` It expires in ${mm}:${ss}.` : " It has expired. Request a new one."}</p>
            <input className="form-control form-control-lg text-center mb-3" inputMode="numeric" autoComplete="one-time-code" maxLength={6}
              placeholder="000000" value={code} autoFocus required onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
            <button className="btn btn-primary w-100" disabled={busy || code.length !== 6}>{busy ? "Checking" : "Verify and continue"}</button>
            <div className="d-flex justify-content-between mt-2">
              <button type="button" className="btn btn-link btn-sm" disabled={busy || resendIn > 0} onClick={sendCode}>{resendIn > 0 ? `Resend in ${resendIn}s` : "Resend code"}</button>
              <button type="button" className="btn btn-link btn-sm" onClick={() => { setStep(2); setErr(""); }}>Change delivery option</button>
            </div>
          </form>
        )}
      </div>
      <p className="small text-secondary text-center mt-3 mb-0">Your location, IP address and device are recorded with your vote for election security.</p>
      
    </div>
  );
}
