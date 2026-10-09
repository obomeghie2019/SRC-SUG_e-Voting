import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import api from "../api";

const POLL_MS = 3000;

export default function Monitor() {
  const [d, setD] = useState(null);
  const [stale, setStale] = useState(false);
  const [updated, setUpdated] = useState(null);

  useEffect(() => {
    let alive = true;
    const tick = () => api.get("/admin/live")
      .then((r) => { if (alive) { setD(r.data); setStale(false); setUpdated(new Date()); } })
      .catch(() => alive && setStale(true));
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => { alive = false; clearInterval(id); };
  }, []);

  if (!d) return "Loading";
  const t = d.turnout;
  const brand = getComputedStyle(document.documentElement).getPropertyValue("--brand").trim() || "#0b6e4f";

  return (
    <>
      <div className="d-flex align-items-center gap-2 mb-3 small text-secondary">
        <span className="live-dot" style={stale ? { background: "#c0392b", animation: "none" } : {}} />
        {stale ? "Connection lost, retrying" : `Live. Updated ${updated?.toLocaleTimeString()}`}
      </div>

      <div className="row g-3 mb-4">
        <div className="col-md-4"><div className="card p-3"><div className="text-secondary small">Votes cast</div><div className="stat">{t.voted.toLocaleString()}</div></div></div>
        <div className="col-md-4"><div className="card p-3"><div className="text-secondary small">Registered voters</div><div className="stat">{t.registered.toLocaleString()}</div></div></div>
        <div className="col-md-4"><div className="card p-3"><div className="text-secondary small">Turnout</div><div className="stat">{t.pct}%</div>
          <div className="progress mt-2" style={{ height: 6 }}><div className="progress-bar" style={{ width: `${t.pct}%`, background: brand }} /></div></div></div>
      </div>

      <div className="row g-3">
        {d.results.map((p) => (
          <div key={p.position_id} className="col-xl-4 col-md-6">
            <div className="card p-3 h-100">
              <div className="d-flex justify-content-between"><h2 className="h6 mb-0">{p.title}</h2><span className="small text-secondary">{p.total_votes} votes</span></div>
              <div style={{ height: 40 + p.candidates.length * 44 }}>
                <ResponsiveContainer>
                  <BarChart data={p.candidates} layout="vertical" margin={{ left: 0, right: 24, top: 12 }}>
                    <CartesianGrid horizontal={false} strokeDasharray="3 3" />
                    <XAxis type="number" allowDecimals={false} />
                    <YAxis type="category" dataKey="full_name" width={110} tick={{ fontSize: 12 }} />
                    <Tooltip formatter={(v, _n, i) => [`${v} votes (${i.payload.pct}%)`, ""]} />
                    <Bar dataKey="votes" radius={[0, 4, 4, 0]} isAnimationActive={false}>
                      {p.candidates.map((c, i) => <Cell key={c.id} fill={i === 0 && p.total_votes > 0 ? brand : "#9aa5ad"} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        ))}
        {d.results.length === 0 && <p className="text-secondary">No positions configured yet.</p>}
      </div>
    </>
  );
}
