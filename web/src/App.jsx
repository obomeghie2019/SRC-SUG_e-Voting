import { createContext, useContext, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import api from "./api";
import VoterLogin from "./pages/VoterLogin.jsx";
import Ballot from "./pages/Ballot.jsx";
import AdminLogin from "./admin/AdminLogin.jsx";
import AdminLayout from "./admin/AdminLayout.jsx";
import Settings from "./admin/Settings.jsx";
import Positions from "./admin/Positions.jsx";
import Voters from "./admin/Voters.jsx";
import Monitor from "./admin/Monitor.jsx";
import Analytics from "./admin/Analytics.jsx";

const ConfigCtx = createContext({});
export const useConfig = () => useContext(ConfigCtx);

export default function App() {
  const [cfg, setCfg] = useState({ institution_name: "", election_title: "e-Voting", election_status: "draft", logo_url: "", theme_color: "#0b6e4f" });
  const reload = () => api.get("/config").then((r) => setCfg(r.data)).catch(() => {});

  useEffect(() => { reload(); }, []);
  useEffect(() => {
    document.title = `${cfg.election_title} | ${cfg.institution_name}`;
    document.documentElement.style.setProperty("--brand", cfg.theme_color || "#0b6e4f");
  }, [cfg]);

  return (
    <ConfigCtx.Provider value={{ ...cfg, reload }}>
      <Routes>
        <Route path="/" element={<VoterLogin />} />
        <Route path="/ballot" element={<Ballot />} />
        <Route path="/admin/login" element={<AdminLogin />} />
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<Navigate to="monitor" replace />} />
          <Route path="monitor" element={<Monitor />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="positions" element={<Positions />} />
          <Route path="voters" element={<Voters />} />
          <Route path="settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ConfigCtx.Provider>
  );
}
