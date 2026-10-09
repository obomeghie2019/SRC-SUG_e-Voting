import { useEffect, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import api from "../api";

const PALETTE = ["#0b6e4f", "#2a6fdb", "#d98e04", "#8e44ad", "#c0392b", "#16a085", "#7f8c8d"];

function Panel({ title, note, children, height = 280 }) {
  return (
    <div className="card p-3 h-100">
      <h2 className="h6 mb-0">{title}</h2>
      {note && <div className="small text-secondary">{note}</div>}
      <div style={{ height }} className="mt-2"><ResponsiveContainer>{children}</ResponsiveContainer></div>
    </div>
  );
}

function Breakdown({ title, rows }) {
  return (
    <Panel title={title} note="Voted vs. registered">
      <BarChart data={rows} margin={{ top: 8 }}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={60} />
        <YAxis allowDecimals={false} />
        <Tooltip /><Legend verticalAlign="top" />
        <Bar dataKey="registered" name="Registered" fill="#c9d1d6" radius={[4, 4, 0, 0]} />
        <Bar dataKey="voted" name="Voted" fill="#0b6e4f" radius={[4, 4, 0, 0]} />
      </BarChart>
    </Panel>
  );
}

export default function Analytics() {
  const [a, setA] = useState(null);
  const load = () => api.get("/admin/analytics").then((r) => setA(r.data));
  useEffect(() => { load(); }, []);
  if (!a) return "Loading";

  return (
    <>
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h1 className="h5 mb-0">Turnout: {a.turnout.voted} of {a.turnout.registered} voters ({a.turnout.pct}%)</h1>
        <button className="btn btn-sm btn-outline-primary" onClick={load}>Refresh</button>
      </div>
      <div className="row g-3">
        <div className="col-lg-8"><Panel title="Votes over time" note="Ballots submitted per hour (UTC)">
          <AreaChart data={a.timeline} margin={{ top: 8 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="time" tick={{ fontSize: 11 }} /><YAxis allowDecimals={false} /><Tooltip />
            <Area type="monotone" dataKey="votes" stroke="#0b6e4f" fill="#0b6e4f" fillOpacity={0.18} />
          </AreaChart>
        </Panel></div>
        <div className="col-lg-4"><Panel title="Web vs. mobile" note="Where ballots were cast">
          <PieChart>
            <Pie data={a.by_channel} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} label>
              {a.by_channel.map((_, i) => <Cell key={i} fill={PALETTE[i]} />)}
            </Pie><Legend /><Tooltip />
          </PieChart>
        </Panel></div>
        <div className="col-lg-6"><Breakdown title="Turnout by department" rows={a.by_department} /></div>
        <div className="col-lg-6"><Breakdown title="Turnout by level" rows={a.by_level} /></div>

        {a.results.map((p) => (
          <div key={p.position_id} className="col-lg-4 col-md-6">
            <Panel title={p.title} note={`${p.total_votes} votes`} height={260}>
              <PieChart>
                <Pie data={p.candidates} dataKey="votes" nameKey="full_name" outerRadius={80} label={(e) => `${e.pct}%`}>
                  {p.candidates.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
                </Pie><Legend /><Tooltip />
              </PieChart>
            </Panel>
          </div>
        ))}
      </div>
    </>
  );
}
