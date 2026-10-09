import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { errMsg } from "../api";
import { useConfig } from "../App.jsx";
import Brand from "./Brand.jsx";

const initials = (n) => n.split(" ").map((w) => w[0]).slice(0, 2).join("");

export default function Ballot() {
  const nav = useNavigate();
  const { election_status, reload } = useConfig();
  const [ballot, setBallot] = useState(null);
  const [sel, setSel] = useState({});
  const [err, setErr] = useState("");
  const [receipt, setReceipt] = useState("");
  const [confirming, setConfirming] = useState(false);

  const logout = () => { sessionStorage.removeItem("voter_token"); nav("/"); };

  useEffect(() => {
    reload();
    api.get("/ballot").then((r) => setBallot(r.data)).catch((e) => {
      if (e.response?.status === 401) logout(); else setErr(errMsg(e));
    });
    // eslint-disable-next-line
  }, []);

  async function submit() {
    setErr("");
    try {
      const { data } = await api.post("/vote", { selections: sel });
      setReceipt(data.receipt_code); setConfirming(false);
    } catch (e) { setErr(errMsg(e)); setConfirming(false); }
  }

  const header = (
    <div className="bg-white border-bottom"><div className="container py-3 d-flex justify-content-between align-items-center">
      <Brand /><button className="btn btn-sm btn-outline-secondary" onClick={logout}>Sign out</button>
    </div></div>
  );

  if (!ballot) return <>{header}<div className="container py-5">{err ? <div className="alert alert-danger">{err}</div> : "Loading ballot"}</div></>;

  if (receipt || ballot.has_voted) return (
    <>{header}<div className="container py-5 text-center" style={{ maxWidth: 520 }}>
      <h1 className="h3">Your vote has been recorded</h1>
      {receipt && <><p className="text-secondary mt-3">Keep this receipt code. It proves your ballot was counted without revealing your choices.</p>
        <div className="display-6 fw-semibold text-brand">{receipt}</div></>}
      {!receipt && <p className="text-secondary mt-3">You have already voted in this election.</p>}
    </div></>
  );

  if (election_status !== "open") return (
    <>{header}<div className="container py-5 text-center">
      <h1 className="h4">{election_status === "closed" ? "Voting has closed" : "Voting has not started yet"}</h1>
    </div></>
  );

  const chosen = Object.keys(sel).length;
  return (
    <>{header}
      <div className="container py-4" style={{ maxWidth: 760 }}>
        {err && <div className="alert alert-danger">{err}</div>}
        {ballot.positions.map((p) => (
          <section key={p.id} className="mb-4">
            <h2 className="h5 mb-3">{p.title}</h2>
            <div className="d-grid gap-2">
              {p.candidates.map((c) => (
                <label key={c.id} className="candidate">
                  <input type="radio" className="form-check-input m-0" name={`p${p.id}`} checked={sel[p.id] === c.id}
                    onChange={() => setSel({ ...sel, [p.id]: c.id })} />
                  {c.photo_url ? <img className="avatar" src={c.photo_url} alt="" /> : <div className="avatar">{initials(c.full_name)}</div>}
                  <div>
                    <div className="fw-medium">{c.full_name}</div>
                    <div className="small text-secondary">{[c.department, c.level].filter(Boolean).join(", ")}</div>
                    {c.manifesto && <div className="small mt-1">{c.manifesto}</div>}
                  </div>
                </label>
              ))}
            </div>
          </section>
        ))}
        <button className="btn btn-primary btn-lg w-100" disabled={!chosen} onClick={() => setConfirming(true)}>
          Review your choices ({chosen} of {ballot.positions.length})
        </button>
      </div>

      {confirming && (
        <div className="modal d-block" style={{ background: "rgba(0,0,0,.45)" }}>
          <div className="modal-dialog modal-dialog-centered"><div className="modal-content">
            <div className="modal-header"><h2 className="modal-title h5">Confirm your vote</h2></div>
            <div className="modal-body">
              {ballot.positions.map((p) => {
                const c = p.candidates.find((x) => x.id === sel[p.id]);
                return <div key={p.id} className="leader-row py-1"><span className="text-secondary">{p.title}</span><strong>{c ? c.full_name : "No selection"}</strong></div>;
              })}
              <p className="small text-secondary mt-3 mb-0">You cannot change your vote after submitting.</p>
            </div>
            <div className="modal-footer">
              <button className="btn btn-outline-secondary" onClick={() => setConfirming(false)}>Go back</button>
              <button className="btn btn-primary" onClick={submit}>Submit vote</button>
            </div>
          </div></div>
        </div>
      )}
    </>
  );
}
