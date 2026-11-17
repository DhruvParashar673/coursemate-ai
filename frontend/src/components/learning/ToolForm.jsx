import { useId, useState } from "react";
import { FileText } from "lucide-react";
import Card from "../ui/Card";
import Button from "../ui/Button";
import "./learning.css";

function parsePage(value) {
  if (value === "") return { ok: true, n: null };
  const n = Number(value);
  return Number.isInteger(n) && n >= 1 ? { ok: true, n } : { ok: false, n: null };
}

// Document + optional page-range controls shared by the Summary and Important Questions tools.
// `children` renders tool-specific controls (length / count). onSubmit receives {documentId, startPage, endPage}.
export default function ToolForm({
  documents,
  docsLoading,
  onOpenDocuments,
  onSubmit,
  loading,
  error,
  submitLabel,
  submitIcon,
  children,
}) {
  const uid = useId();
  const [docId, setDocId] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [formError, setFormError] = useState("");

  const ready = documents.filter((d) => d.status === "ready");
  const anyProcessing = documents.some((d) => d.status === "processing");
  const selected = ready.find((d) => String(d.id) === docId) ? docId : ready[0] ? String(ready[0].id) : "";

  if (docsLoading) {
    return (
      <div className="card skeleton-card" aria-busy="true">
        <div className="skeleton skeleton-line" style={{ width: "40%" }} />
        <div className="skeleton skeleton-line" />
      </div>
    );
  }

  if (ready.length === 0) {
    return (
      <Card className="lt-empty-docs">
        <div className="state-icon"><FileText size={26} /></div>
        <h3>No ready PDFs yet</h3>
        <p>
          {anyProcessing
            ? "Your PDFs are still processing. They'll appear here as soon as they're ready."
            : "Upload a PDF in the Documents tab to use this tool."}
        </p>
        <Button variant="secondary" onClick={onOpenDocuments}>Go to Documents</Button>
      </Card>
    );
  }

  const submit = (e) => {
    e.preventDefault();
    const s = parsePage(start);
    const en = parsePage(end);
    if (!s.ok || !en.ok) return setFormError("Page numbers must be whole numbers of 1 or more.");
    if (s.n !== null && en.n !== null && s.n > en.n) return setFormError("Start page must be less than or equal to end page.");
    setFormError("");
    onSubmit({ documentId: selected, startPage: s.n, endPage: en.n });
  };

  const message = formError || error;

  return (
    <Card className="lt-form">
      <form onSubmit={submit}>
        <div className="lt-grid">
          <div className="field lt-span">
            <label htmlFor={`${uid}-doc`}>PDF</label>
            <select
              id={`${uid}-doc`}
              className="input"
              value={selected}
              onChange={(e) => setDocId(e.target.value)}
              disabled={loading}
            >
              {ready.map((d) => (
                <option key={d.id} value={String(d.id)}>{d.name}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor={`${uid}-start`}>Start page</label>
            <input
              id={`${uid}-start`}
              className="input"
              type="number"
              min={1}
              step={1}
              inputMode="numeric"
              placeholder="First"
              value={start}
              onChange={(e) => { setStart(e.target.value); setFormError(""); }}
              disabled={loading}
            />
          </div>
          <div className="field">
            <label htmlFor={`${uid}-end`}>End page</label>
            <input
              id={`${uid}-end`}
              className="input"
              type="number"
              min={1}
              step={1}
              inputMode="numeric"
              placeholder="Last"
              value={end}
              onChange={(e) => { setEnd(e.target.value); setFormError(""); }}
              disabled={loading}
            />
          </div>
        </div>
        <div className="lt-hint">Leave the page range empty to cover the whole PDF.</div>

        {children}

        {message && (
          <div className="badge badge-danger lt-error" role="alert">{message}</div>
        )}

        <div className="lt-actions">
          <Button type="submit" icon={submitIcon} loading={loading}>{submitLabel}</Button>
        </div>
      </form>
    </Card>
  );
}
