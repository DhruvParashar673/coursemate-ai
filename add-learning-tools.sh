#!/usr/bin/env bash
# add-learning-tools.sh — run from the project root.
# Works with ./frontend (frontend/src/...) or ./ (src/...).
# Existing files are backed up to <app>/.learning-backup-<timestamp>/ before being changed.
# No deletions are performed.
set -euo pipefail

if [ -d "frontend/src" ]; then
  APP="frontend"
elif [ -d "src" ] && [ -f "package.json" ]; then
  APP="."
else
  echo "Error: could not find frontend/src or ./src with package.json. Run from the project root." >&2
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$APP/.learning-backup-$STAMP"

for dep in "src/pages/CourseDetail.jsx" "src/services/api.js" "src/services/documents.js" \
           "src/hooks/useDocuments.js" \
           "src/components/ui/Button.jsx" "src/components/ui/Card.jsx" "src/components/ui/Badge.jsx" \
           "src/pages/pages.css"; do
  [ -f "$APP/$dep" ] || { echo "Error: required existing file missing: $APP/$dep (run add-dashboard.sh and add-course-detail.sh first)" >&2; exit 1; }
done
echo "==> App directory: $APP"

backup() {
  local rel="${1#"$APP"/}"
  mkdir -p "$BACKUP_DIR/$(dirname "$rel")"
  cp -p "$1" "$BACKUP_DIR/$rel"
  echo "    backed up: $1"
}

write_file() {
  local f="$1"
  if [ -e "$f" ]; then backup "$f"; fi
  mkdir -p "$(dirname "$f")"
  cat > "$f"
  echo "    wrote: $f"
}

# ------------------------------------------------------------ services/learning.js
write_file "$APP/src/services/learning.js" <<'LEARNINGAPI_EOF'
import api from "./api";

const enc = encodeURIComponent;

export const SUMMARY_LENGTHS = ["short", "medium", "detailed"];
export const MIN_QUESTIONS = 1;
export const MAX_QUESTIONS = 15;

// "Pages 3–7" / "Page 4". Accepts [a, b], {start_page, end_page} or a string; returns null if unknown.
export function formatPageRange(range) {
  if (range == null) return null;
  if (typeof range === "string") {
    const s = range.trim();
    if (!s) return null;
    return /^\d/.test(s) ? `Pages ${s}` : s;
  }
  let a;
  let b;
  if (Array.isArray(range)) [a, b] = range;
  else if (typeof range === "object") {
    a = range.start_page ?? range.start ?? range.from;
    b = range.end_page ?? range.end ?? range.to;
  }
  if (a == null && b == null) return null;
  if (a == null || b == null || a === b) return `Page ${a ?? b}`;
  return `Pages ${a}–${b}`;
}

export function normalizeCitation(c) {
  if (!c || typeof c !== "object") return null;
  const page = Number.isFinite(c.page_number) ? c.page_number : Number.isFinite(c.page) ? c.page : null;
  return { documentId: c.document_id ?? null, filename: c.filename || "Document", page };
}

function uniqueCitations(list) {
  const seen = new Set();
  const out = [];
  (Array.isArray(list) ? list : []).forEach((raw) => {
    const c = normalizeCitation(raw);
    if (!c) return;
    const key = `${c.documentId}|${c.filename}|${c.page}`;
    if (!seen.has(key)) {
      seen.add(key);
      out.push(c);
    }
  });
  return out;
}

function toTextList(list) {
  if (!Array.isArray(list)) return [];
  return list
    .map((item) => (typeof item === "string" ? item : item?.text ?? item?.point ?? item?.content ?? ""))
    .map((s) => String(s).trim())
    .filter(Boolean);
}

const common = (d) => ({
  pageRange: formatPageRange(d?.page_range),
  partial: d?.partial === true,
  provider: d?.provider ?? null,
  grounded: typeof d?.grounded === "boolean" ? d.grounded : null,
  message: typeof d?.message === "string" && d.message.trim() ? d.message.trim() : null,
});

// Only maps what the backend returned; nothing is invented.
export function normalizeSummary(d) {
  return {
    ...common(d),
    summary: typeof d?.summary === "string" ? d.summary : "",
    keyPoints: toTextList(d?.key_points),
    citations: uniqueCitations(d?.citations),
  };
}

export function normalizeQuestions(d) {
  const raw = Array.isArray(d?.questions) ? d.questions : [];
  return {
    ...common(d),
    questions: raw
      .map((q) => ({
        question: typeof q?.question === "string" ? q.question.trim() : "",
        type: typeof q?.type === "string" && q.type ? q.type : null,
        why: typeof q?.why_important === "string" && q.why_important.trim() ? q.why_important.trim() : null,
        citation: normalizeCitation(q?.citation),
      }))
      .filter((q) => q.question),
  };
}

export const learningApi = {
  summarize: (courseId, { documentId, startPage = null, endPage = null, length = "medium" }) =>
    api
      .post(`/courses/${enc(courseId)}/summaries`, {
        document_id: documentId,
        start_page: startPage,
        end_page: endPage,
        length,
      })
      .then((r) => normalizeSummary(r.data)),

  importantQuestions: (courseId, { documentId, startPage = null, endPage = null, count = 10 }) =>
    api
      .post(`/courses/${enc(courseId)}/important-questions`, {
        document_id: documentId,
        start_page: startPage,
        end_page: endPage,
        count,
      })
      .then((r) => normalizeQuestions(r.data)),
};
LEARNINGAPI_EOF

# ------------------------------------------------------------ components/learning/learning.css
write_file "$APP/src/components/learning/learning.css" <<'LEARNINGCSS_EOF'
/* Tabs */
.course-tabs { display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 1px solid var(--border); overflow-x: auto; scrollbar-width: none; }
.course-tabs::-webkit-scrollbar { display: none; }
.course-tab {
  display: inline-flex; align-items: center; gap: 8px; padding: 11px 16px; white-space: nowrap; font-family: inherit;
  font-size: 14px; font-weight: 600; color: var(--text-muted); background: transparent; border: none; cursor: pointer;
  border-bottom: 2px solid transparent; margin-bottom: -1px; transition: color 0.2s, border-color 0.2s, background 0.2s;
  border-radius: 8px 8px 0 0;
}
.course-tab:hover { color: var(--text); background: rgba(99, 102, 241, 0.08); }
.course-tab.active { color: #fff; border-bottom-color: var(--primary-2); }

.docs-section[hidden] { display: none; }

/* Tool form */
.lt-tool { display: flex; flex-direction: column; gap: 16px; }
.lt-form form { display: flex; flex-direction: column; gap: 16px; }
.lt-grid { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 14px; }
.lt-hint { font-size: 12px; color: var(--text-muted); }
select.input { color-scheme: dark; cursor: pointer; }

.seg { display: inline-flex; padding: 3px; gap: 3px; border-radius: var(--radius-sm); background: rgba(10, 13, 31, 0.7); border: 1px solid var(--border); width: fit-content; max-width: 100%; }
.seg button {
  font-family: inherit; font-size: 13px; font-weight: 600; padding: 7px 16px; border-radius: 8px; border: none;
  background: transparent; color: var(--text-muted); cursor: pointer; text-transform: capitalize; transition: all 0.2s ease;
}
.seg button:hover:not(.on) { color: var(--text); }
.seg button.on { background: var(--grad); color: #fff; box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4); }

.lt-range { display: flex; align-items: center; gap: 14px; }
.lt-range input[type="range"] { flex: 1; accent-color: var(--primary-2); }
.lt-range-value { min-width: 32px; text-align: center; font-family: var(--font-display); font-weight: 700; font-size: 18px; }

.lt-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.lt-error { display: block; border-radius: 10px; padding: 10px 12px; font-weight: 500; white-space: normal; }
.lt-empty-docs { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 10px; padding: 36px 20px; }
.lt-empty-docs h3 { font-size: 18px; }
.lt-empty-docs p { color: var(--text-muted); font-size: 14px; max-width: 380px; margin-bottom: 4px; }

/* Loading */
.lt-loading { display: flex; flex-direction: column; gap: 12px; }
.lt-loading-label { display: flex; align-items: center; gap: 8px; color: var(--text-muted); font-size: 13px; }

/* Results */
.lt-result-head { display: flex; flex-direction: column; gap: 10px; margin-bottom: 14px; }
.lt-result-title { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.lt-result-title h3 { font-size: 18px; }
.lt-result-doc { font-size: 13px; color: var(--text-muted); overflow-wrap: anywhere; }
.lt-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 10px; }
.lt-provider { font-size: 12px; color: var(--text-muted); }
.lt-banner { display: flex; align-items: flex-start; gap: 8px; padding: 10px 12px; border-radius: var(--radius-sm); font-size: 13.5px; line-height: 1.5; margin-bottom: 14px; }
.lt-banner svg { flex-shrink: 0; margin-top: 2px; }
.lt-banner-warning { color: var(--warning); background: rgba(251, 191, 36, 0.09); border: 1px solid rgba(251, 191, 36, 0.28); }
.lt-banner-info { color: var(--accent-blue); background: rgba(56, 189, 248, 0.09); border: 1px solid rgba(56, 189, 248, 0.28); }

.lt-text { font-size: 14.5px; line-height: 1.75; white-space: pre-wrap; overflow-wrap: anywhere; }
.lt-empty-text { color: var(--text-muted); font-style: italic; }
.lt-section-title { font-size: 12px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-muted); margin: 20px 0 10px; }

.lt-points { list-style: none; display: flex; flex-direction: column; gap: 10px; }
.lt-points li { display: flex; gap: 10px; font-size: 14.5px; line-height: 1.6; overflow-wrap: anywhere; }
.lt-points li::before { content: ""; width: 7px; height: 7px; margin-top: 9px; border-radius: 50%; background: var(--grad); flex-shrink: 0; }

.lt-cites { display: flex; flex-wrap: wrap; gap: 8px; }
.lt-cite { display: inline-flex; align-items: center; gap: 6px; max-width: 100%; padding: 4px 10px; border-radius: 999px; font-size: 12px; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.28); color: var(--accent-blue); }
.lt-cite svg { flex-shrink: 0; }
.lt-cite-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 240px; }
.lt-cite-page { font-weight: 700; color: #fff; }

.lt-questions { list-style: none; display: flex; flex-direction: column; gap: 12px; counter-reset: q; }
.lt-q { display: flex; gap: 14px; padding: 14px; border-radius: var(--radius-sm); background: rgba(99, 102, 241, 0.07); border: 1px solid var(--border); counter-increment: q; }
.lt-q-num { width: 30px; height: 30px; flex-shrink: 0; border-radius: 9px; display: grid; place-items: center; font-family: var(--font-display); font-weight: 700; font-size: 13px; background: var(--grad); color: #fff; }
.lt-q-num::before { content: counter(q); }
.lt-q-body { display: flex; flex-direction: column; gap: 8px; min-width: 0; flex: 1; }
.lt-q-text { font-size: 15px; font-weight: 600; line-height: 1.55; overflow-wrap: anywhere; }
.lt-q-why { font-size: 13.5px; line-height: 1.6; color: var(--text-muted); overflow-wrap: anywhere; }
.lt-q-why strong { color: var(--text); font-weight: 600; }
.lt-q-foot { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }

@media (max-width: 720px) {
  .lt-grid { grid-template-columns: 1fr 1fr; }
  .lt-grid .lt-span { grid-column: 1 / -1; }
  .lt-actions .btn { width: 100%; }
  .lt-q { padding: 12px; gap: 10px; }
  .lt-cite-name { max-width: 150px; }
}
LEARNINGCSS_EOF

# ------------------------------------------------------------ components/learning/CourseTabs.jsx
write_file "$APP/src/components/learning/CourseTabs.jsx" <<'TABS_EOF'
import { AlignLeft, FileText, ListChecks } from "lucide-react";
import "./learning.css";

const TABS = [
  { id: "documents", label: "Documents", icon: FileText },
  { id: "summary", label: "Summary", icon: AlignLeft },
  { id: "questions", label: "Important questions", icon: ListChecks },
];

export default function CourseTabs({ tab, onChange }) {
  return (
    <div className="course-tabs" role="tablist" aria-label="Course sections">
      {TABS.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          type="button"
          role="tab"
          aria-selected={tab === id}
          className={`course-tab ${tab === id ? "active" : ""}`}
          onClick={() => onChange(id)}
        >
          <Icon size={16} /> {label}
        </button>
      ))}
    </div>
  );
}
TABS_EOF

# ------------------------------------------------------------ components/learning/ToolForm.jsx
write_file "$APP/src/components/learning/ToolForm.jsx" <<'TOOLFORM_EOF'
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
TOOLFORM_EOF

# ------------------------------------------------------------ components/learning/ResultParts.jsx
write_file "$APP/src/components/learning/ResultParts.jsx" <<'RESULTPARTS_EOF'
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
RESULTPARTS_EOF

# ------------------------------------------------------------ components/learning/SummaryTool.jsx
write_file "$APP/src/components/learning/SummaryTool.jsx" <<'SUMMARYTOOL_EOF'
import { useState } from "react";
import { AlignLeft, Sparkles } from "lucide-react";
import Card from "../ui/Card";
import ToolForm from "./ToolForm";
import { CitationChip, GroundedNote, ResultMeta, ResultNotice, ToolLoading } from "./ResultParts";
import { SUMMARY_LENGTHS, learningApi } from "../../services/learning";
import { getErrorMessage } from "../../services/api";
import "./learning.css";

export default function SummaryTool({ courseId, documents, docsLoading, onOpenDocuments }) {
  const [length, setLength] = useState("medium");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null); // { data, docName }

  const run = async (params) => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await learningApi.summarize(courseId, { ...params, length });
      const doc = documents.find((d) => String(d.id) === params.documentId);
      setResult({ data, docName: doc?.name ?? "" });
    } catch (err) {
      setError(getErrorMessage(err, "Could not generate the summary."));
    } finally {
      setLoading(false);
    }
  };

  const data = result?.data;

  return (
    <div className="lt-tool">
      <ToolForm
        documents={documents}
        docsLoading={docsLoading}
        onOpenDocuments={onOpenDocuments}
        onSubmit={run}
        loading={loading}
        error={error}
        submitLabel="Generate summary"
        submitIcon={Sparkles}
      >
        <div className="field">
          <label>Length</label>
          <div className="seg" role="group" aria-label="Summary length">
            {SUMMARY_LENGTHS.map((l) => (
              <button
                key={l}
                type="button"
                className={length === l ? "on" : ""}
                aria-pressed={length === l}
                onClick={() => setLength(l)}
                disabled={loading}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
      </ToolForm>

      {loading && <ToolLoading label="Generating summary… this can take a moment." />}

      {data && (
        <Card className="anim-fade-up">
          <div className="lt-result-head">
            <div className="lt-result-title">
              <h3><AlignLeft size={16} style={{ verticalAlign: "-2px", marginRight: 6 }} />Summary</h3>
              {result.docName && <span className="lt-result-doc">{result.docName}</span>}
            </div>
            <ResultMeta pageRange={data.pageRange} grounded={data.grounded} partial={data.partial} provider={data.provider} />
          </div>

          <ResultNotice
            partial={data.partial}
            message={data.message}
            partialFallback="Partial result: this summary may not cover the entire selected range."
          />
          <GroundedNote grounded={data.grounded} />

          {data.summary ? (
            <div className="lt-text">{data.summary}</div>
          ) : (
            <div className="lt-text lt-empty-text">The backend returned an empty summary.</div>
          )}

          {data.keyPoints.length > 0 && (
            <>
              <div className="lt-section-title">Key points</div>
              <ul className="lt-points">
                {data.keyPoints.map((p, i) => <li key={i}>{p}</li>)}
              </ul>
            </>
          )}

          {data.citations.length > 0 && (
            <>
              <div className="lt-section-title">Sources</div>
              <div className="lt-cites">
                {data.citations.map((c, i) => <CitationChip key={`${c.documentId}-${c.page}-${i}`} citation={c} />)}
              </div>
            </>
          )}
        </Card>
      )}
    </div>
  );
}
SUMMARYTOOL_EOF

# ------------------------------------------------------------ components/learning/QuestionsTool.jsx
write_file "$APP/src/components/learning/QuestionsTool.jsx" <<'QUESTIONSTOOL_EOF'
import { useState } from "react";
import { ListChecks, Sparkles } from "lucide-react";
import Card from "../ui/Card";
import ToolForm from "./ToolForm";
import { CitationChip, GroundedNote, ResultMeta, ResultNotice, ToolLoading } from "./ResultParts";
import { MAX_QUESTIONS, MIN_QUESTIONS, learningApi } from "../../services/learning";
import { getErrorMessage } from "../../services/api";
import "./learning.css";

const typeLabel = (t) => t.replace(/[_-]+/g, " ");

export default function QuestionsTool({ courseId, documents, docsLoading, onOpenDocuments }) {
  const [count, setCount] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null); // { data, docName }

  const run = async (params) => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await learningApi.importantQuestions(courseId, { ...params, count });
      const doc = documents.find((d) => String(d.id) === params.documentId);
      setResult({ data, docName: doc?.name ?? "" });
    } catch (err) {
      setError(getErrorMessage(err, "Could not generate important questions."));
    } finally {
      setLoading(false);
    }
  };

  const data = result?.data;

  return (
    <div className="lt-tool">
      <ToolForm
        documents={documents}
        docsLoading={docsLoading}
        onOpenDocuments={onOpenDocuments}
        onSubmit={run}
        loading={loading}
        error={error}
        submitLabel="Generate questions"
        submitIcon={Sparkles}
      >
        <div className="field">
          <label htmlFor="lt-count">Number of questions</label>
          <div className="lt-range">
            <input
              id="lt-count"
              type="range"
              min={MIN_QUESTIONS}
              max={MAX_QUESTIONS}
              step={1}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              disabled={loading}
            />
            <span className="lt-range-value">{count}</span>
          </div>
        </div>
      </ToolForm>

      {loading && <ToolLoading label="Finding the most important questions…" />}

      {data && (
        <Card className="anim-fade-up">
          <div className="lt-result-head">
            <div className="lt-result-title">
              <h3><ListChecks size={16} style={{ verticalAlign: "-2px", marginRight: 6 }} />Important questions</h3>
              {result.docName && <span className="lt-result-doc">{result.docName}</span>}
            </div>
            <ResultMeta pageRange={data.pageRange} grounded={data.grounded} partial={data.partial} provider={data.provider} />
          </div>

          <ResultNotice
            partial={data.partial}
            message={data.message}
            partialFallback="Partial result: fewer questions than requested may have been generated."
          />
          <GroundedNote grounded={data.grounded} />

          {data.questions.length === 0 ? (
            <div className="lt-text lt-empty-text">No questions were returned for this selection.</div>
          ) : (
            <ol className="lt-questions">
              {data.questions.map((q, i) => (
                <li key={i} className="lt-q">
                  <div className="lt-q-num" aria-hidden="true" />
                  <div className="lt-q-body">
                    <div className="lt-q-text">{q.question}</div>
                    {q.why && <div className="lt-q-why"><strong>Why it matters:</strong> {q.why}</div>}
                    {(q.type || q.citation) && (
                      <div className="lt-q-foot">
                        {q.type && <span className="badge" style={{ textTransform: "capitalize" }}>{typeLabel(q.type)}</span>}
                        {q.citation && <CitationChip citation={q.citation} />}
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>
      )}
    </div>
  );
}
QUESTIONSTOOL_EOF

# ------------------------------------------------------------ CourseDetail.jsx (targeted patch)
echo "==> Integrating tabs into $APP/src/pages/CourseDetail.jsx"
backup "$APP/src/pages/CourseDetail.jsx"
node - "$APP/src/pages/CourseDetail.jsx" <<'PATCH_EOF'
const fs = require("fs");
const file = process.argv[2];
let s = fs.readFileSync(file, "utf8");

if (s.includes("components/learning/")) {
  console.log("    CourseDetail.jsx already integrated; no change.");
  process.exit(0);
}

const importAnchor = 'import useDocuments from "../hooks/useDocuments";';
const stateAnchor = "const [toDelete, setToDelete] = useState(null);";
const openTag = '<section className="docs-section">';
const closeTag = "</section>";

const count = (str) => s.split(str).length - 1;
const problems = [];
if (count(importAnchor) !== 1) problems.push("useDocuments import");
if (count(stateAnchor) !== 1) problems.push("toDelete state");
if (count(openTag) !== 1) problems.push("docs-section opening tag");
if (count(closeTag) !== 1) problems.push("</section> closing tag");
if (problems.length) {
  console.error("Error: could not find expected anchors in CourseDetail.jsx: " + problems.join(", ") + ". File was NOT changed (backup kept).");
  process.exit(2);
}

const imports = [
  importAnchor,
  'import CourseTabs from "../components/learning/CourseTabs";',
  'import SummaryTool from "../components/learning/SummaryTool";',
  'import QuestionsTool from "../components/learning/QuestionsTool";',
].join("\n");

const toolProps = (extra) =>
  `courseId={courseId} documents={docs.documents} docsLoading={docs.loading} onOpenDocuments={() => setTab("documents")}${extra}`;

s = s
  .replace(importAnchor, imports)
  .replace(stateAnchor, stateAnchor + '\n  const [tab, setTab] = useState("documents");')
  .replace(
    openTag,
    '<CourseTabs tab={tab} onChange={setTab} />\n\n      <section className="docs-section" hidden={tab !== "documents"}>'
  )
  .replace(
    closeTag,
    closeTag +
      `\n\n      <div hidden={tab !== "summary"}>\n        <SummaryTool key={courseId} ${toolProps("")} />\n      </div>\n\n` +
      `      <div hidden={tab !== "questions"}>\n        <QuestionsTool key={courseId} ${toolProps("")} />\n      </div>`
  );

fs.writeFileSync(file, s);
console.log("    CourseDetail.jsx updated.");
PATCH_EOF

echo "==> Verifying with npm run build in $APP"
( cd "$APP" && npm run build )

echo "==> Done. Backups (if any): $BACKUP_DIR"
echo "    To verify manually: cd $APP && npm run build && npm run dev"
