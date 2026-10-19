// Right-hand frame shown beside a CSV import: the columns, a sample, tips and a template download.
// Used by the Voters page and the Positions & candidates page.
export default function CsvTemplatePanel({ title, file, intro, columns, sample, tips }) {
  const href = `${import.meta.env.BASE_URL}templates/${file}`;
  return (
    <div className="sticky-top no-print" style={{ top: "1rem", zIndex: 1 }}>
      <div className="card">
        <div className="card-header bg-white d-flex justify-content-between align-items-center gap-2">
          <span className="fw-semibold">{title}</span>
          <a className="btn btn-sm btn-primary text-nowrap" href={href} download={file}>Download template</a>
        </div>
        <div className="card-body">
          <p className="small text-secondary mb-3">{intro}</p>

          <div className="fw-semibold small mb-1">Columns</div>
          <table className="table table-sm small align-middle mb-3">
            <tbody>
              {columns.map(([name, required, note]) => (
                <tr key={name}>
                  <td className="text-nowrap"><code>{name}</code></td>
                  <td><span className={"badge " + (required ? "text-bg-success" : "text-bg-light border")}>{required ? "required" : "optional"}</span></td>
                  <td className="text-secondary">{note}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="fw-semibold small mb-1">Example rows</div>
          <div className="table-responsive border rounded mb-3">
            <table className="table table-sm mb-0" style={{ fontSize: 11 }}>
              <thead className="table-light"><tr>{columns.map(([name]) => <th key={name} className="text-nowrap">{name}</th>)}</tr></thead>
              <tbody>{sample.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j} className="text-nowrap">{cell}</td>)}</tr>)}</tbody>
            </table>
          </div>

          <div className="fw-semibold small mb-1">Before you upload</div>
          <ul className="small text-secondary ps-3 mb-0">{tips.map((t) => <li key={t} className="mb-1">{t}</li>)}</ul>
        </div>
      </div>
    </div>
  );
}
