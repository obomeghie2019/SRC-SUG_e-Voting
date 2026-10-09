import { useConfig } from "../App.jsx";

export default function Brand({ light = false }) {
  const { institution_name, election_title, logo_url } = useConfig();
  return (
    <div className="d-flex align-items-center gap-3">
      {logo_url ? <img src={logo_url} alt="" height="44" /> : <div className="avatar bg-brand">{(institution_name || "E")[0]}</div>}
      <div className="lh-sm">
        <div className="fw-semibold">{institution_name}</div>
        <div className={light ? "small text-white-50" : "small text-secondary"}>{election_title}</div>
      </div>
    </div>
  );
}
