import { useEffect } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import api from "../api";
import { useConfig } from "../App.jsx";

const links = [
  ["monitor", "Live monitor"], ["analytics", "Analytics"], ["positions", "Positions & candidates"],
  ["voters", "Voters"], ["settings", "Settings"],
];

export default function AdminLayout() {
  const nav = useNavigate();
  const { institution_name, election_status } = useConfig();
  const token = sessionStorage.getItem("admin_token");

  useEffect(() => {
    if (!token) { nav("/admin/login"); return; }
    // any 401 from an admin call sends the admin back to sign in
    const id = api.interceptors.response.use((r) => r, (e) => {
      if (e.response?.status === 401 && e.config.url.startsWith("/admin")) { sessionStorage.removeItem("admin_token"); nav("/admin/login"); }
      return Promise.reject(e);
    });
    return () => api.interceptors.response.eject(id);
  }, [token, nav]);

  if (!token) return null;
  const badge = { draft: "secondary", open: "success", closed: "dark" }[election_status];

  return (
    <>
      <nav className="navbar navbar-expand-lg bg-white border-bottom">
        <div className="container-fluid px-4">
          <span className="navbar-brand fw-semibold">{institution_name || "Admin"} <span className={`badge text-bg-${badge} ms-2 fs-6 fw-normal`}>{election_status}</span></span>
          <div className="d-flex flex-wrap gap-1">
            {links.map(([to, label]) => (
              <NavLink key={to} to={to} className={({ isActive }) => "btn btn-sm " + (isActive ? "btn-primary" : "btn-outline-secondary border-0")}>{label}</NavLink>
            ))}
            <button className="btn btn-sm btn-outline-secondary border-0" onClick={() => { sessionStorage.removeItem("admin_token"); nav("/admin/login"); }}>Sign out</button>
          </div>
        </div>
      </nav>
      <main className="container-fluid px-4 py-4"><Outlet /></main>
    </>
  );
}
