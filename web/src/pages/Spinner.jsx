export default function Spinner({ busy, text, children }) {
  if (!busy) return children;
  return (
    <>
      <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
      {text ?? children}
    </>
  );
}
