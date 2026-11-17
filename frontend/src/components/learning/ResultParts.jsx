import { AlertCircle, FileText, Info, Loader2, ShieldAlert, ShieldCheck } from "lucide-react";
import "./learning.css";

export function CitationChip({ citation }) {
  return (
    <span className="lt-cite" title={citation.filename}>
      <FileText size={13} />
      <span className="lt-cite-name">{citation.filename}</span>
      {citation.page !== null && <span className="lt-cite-page">p. {citation.page}</span>}
    </span>
  );
}

export function ResultMeta({ pageRange, grounded, partial, provider }) {
  return (
    <div className="lt-meta">
      {pageRange && <span className="badge badge-info"><FileText size={13} /> {pageRange}</span>}
      {grounded === true && <span className="badge badge-success"><ShieldCheck size={13} /> Grounded in your PDF</span>}
      {grounded === false && <span className="badge badge-warning"><ShieldAlert size={13} /> Not grounded in your PDF</span>}
      {partial && <span className="badge badge-warning"><AlertCircle size={13} /> Partial result</span>}
      {provider && <span className="lt-provider">via {provider}</span>}
    </div>
  );
}

// Partial results get a warning (backend message if present); other backend messages show as info.
export function ResultNotice({ partial, message, partialFallback }) {
  if (!partial && !message) return null;
  return (
    <div className={`lt-banner ${partial ? "lt-banner-warning" : "lt-banner-info"}`} role={partial ? "alert" : undefined}>
      {partial ? <AlertCircle size={16} /> : <Info size={16} />}
      <span>{partial ? message || partialFallback : message}</span>
    </div>
  );
}

export function GroundedNote({ grounded }) {
  if (grounded !== false) return null;
  return (
    <div className="lt-banner lt-banner-warning">
      <ShieldAlert size={16} />
      <span>This content isn't backed by your uploaded document. Verify it before relying on it.</span>
    </div>
  );
}

export function ToolLoading({ label }) {
  return (
    <div className="card lt-loading" aria-busy="true" aria-live="polite">
      <div className="lt-loading-label"><Loader2 size={16} className="spin" /> {label}</div>
      <div className="skeleton skeleton-line" style={{ width: "30%", height: 16 }} />
      <div className="skeleton skeleton-line" />
      <div className="skeleton skeleton-line" />
      <div className="skeleton skeleton-line" style={{ width: "75%" }} />
      <div className="skeleton skeleton-line" style={{ width: "55%" }} />
    </div>
  );
}
