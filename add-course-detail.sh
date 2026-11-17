#!/usr/bin/env bash
# add-course-detail.sh — run from the project root.
# Works with ./frontend (frontend/src/...) or ./ (src/...).
# Existing files are backed up to <app>/.detail-backup-<timestamp>/ before being changed.
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
BACKUP_DIR="$APP/.detail-backup-$STAMP"

for dep in "src/App.jsx" "src/services/api.js" "src/services/courses.js" \
           "src/components/ui/Modal.jsx" "src/components/ui/Button.jsx" "src/components/ui/Card.jsx" \
           "src/components/ui/Badge.jsx" "src/components/ui/Input.jsx" "src/pages/pages.css"; do
  [ -f "$APP/$dep" ] || { echo "Error: required existing file missing: $APP/$dep (run add-dashboard.sh first)" >&2; exit 1; }
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

# ------------------------------------------------------------ utils/format.js
write_file "$APP/src/utils/format.js" <<'FORMAT_EOF'
export function formatDate(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
FORMAT_EOF

# ------------------------------------------------------------ services/courses.js (adds get + update)
write_file "$APP/src/services/courses.js" <<'COURSES_API_EOF'
import api from "./api";

const enc = encodeURIComponent;

export const coursesApi = {
  list: () => api.get("/courses").then((r) => r.data),
  create: ({ title, description, subject }) =>
    api.post("/courses", { title, description, subject }).then((r) => r.data),
  get: (courseId) => api.get(`/courses/${enc(courseId)}`).then((r) => r.data),
  update: (courseId, { title, description, subject }) =>
    api.put(`/courses/${enc(courseId)}`, { title, description, subject }).then((r) => r.data),
};
COURSES_API_EOF

# ------------------------------------------------------------ services/documents.js
write_file "$APP/src/services/documents.js" <<'DOCUMENTS_API_EOF'
import api from "./api";

const enc = encodeURIComponent;

// Name of the multipart form field the backend expects for the uploaded file.
export const FILE_FIELD = "file";

const READY = ["ready", "completed", "complete", "processed", "done", "success", "indexed"];
const FAILED = ["failed", "failure", "error", "errored"];

export function normalizeStatus(raw) {
  const s = String(raw ?? "").toLowerCase();
  if (READY.includes(s)) return "ready";
  if (FAILED.includes(s)) return "failed";
  return "processing";
}

// Tolerates common field-name variants so the UI does not break on small schema differences.
export function normalizeDocument(d) {
  const message = d.error_message ?? d.error ?? d.status_message ?? null;
  return {
    id: d.id ?? d._id ?? d.document_id,
    name: d.filename ?? d.file_name ?? d.original_filename ?? d.name ?? d.title ?? "Untitled.pdf",
    status: normalizeStatus(d.status ?? d.processing_status),
    createdAt: d.created_at ?? d.uploaded_at ?? d.createdAt ?? null,
    message: typeof message === "string" ? message : null,
  };
}

function toList(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.documents)) return data.documents;
  if (Array.isArray(data?.items)) return data.items;
  return [];
}

export const documentsApi = {
  list: (courseId) =>
    api.get(`/courses/${enc(courseId)}/documents`).then((r) => toList(r.data).map(normalizeDocument)),

  get: (courseId, documentId) =>
    api.get(`/courses/${enc(courseId)}/documents/${enc(documentId)}`).then((r) => normalizeDocument(r.data)),

  upload: (courseId, file, onProgress) => {
    const body = new FormData();
    body.append(FILE_FIELD, file);
    return api
      .post(`/courses/${enc(courseId)}/documents`, body, {
        onUploadProgress: (e) => {
          if (onProgress && e.total) onProgress(Math.round((e.loaded * 100) / e.total));
        },
      })
      .then((r) => r.data);
  },

  remove: (courseId, documentId) =>
    api.delete(`/courses/${enc(courseId)}/documents/${enc(documentId)}`).then((r) => r.data),
};
DOCUMENTS_API_EOF

# ------------------------------------------------------------ hooks/useCourse.js
write_file "$APP/src/hooks/useCourse.js" <<'USECOURSE_EOF'
import { useCallback, useEffect, useState } from "react";
import { coursesApi } from "../services/courses";
import { getErrorMessage } from "../services/api";

export default function useCourse(courseId) {
  const [course, setCourse] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setCourse(await coursesApi.get(courseId));
    } catch (err) {
      setCourse(null);
      setError(getErrorMessage(err, "Failed to load course."));
    } finally {
      setLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    load();
  }, [load]);

  // Saves, then re-fetches so the page always shows what the server stored.
  const update = useCallback(
    async (data) => {
      await coursesApi.update(courseId, data);
      try {
        setCourse(await coursesApi.get(courseId));
      } catch {
        /* the save succeeded; keep showing the current data */
      }
    },
    [courseId]
  );

  return { course, loading, error, reload: load, update };
}
USECOURSE_EOF

# ------------------------------------------------------------ hooks/useDocuments.js
write_file "$APP/src/hooks/useDocuments.js" <<'USEDOCUMENTS_EOF'
import { useCallback, useEffect, useState } from "react";
import { documentsApi } from "../services/documents";
import { getErrorMessage } from "../services/api";

const POLL_MS = 3000;

export default function useDocuments(courseId) {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // silent = background refresh: no loading flash, errors ignored.
  const load = useCallback(
    async (silent = false) => {
      if (!silent) {
        setLoading(true);
        setError("");
      }
      try {
        setDocuments(await documentsApi.list(courseId));
      } catch (err) {
        if (!silent) setError(getErrorMessage(err, "Failed to load documents."));
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [courseId]
  );

  useEffect(() => {
    load();
  }, [load]);

  // Keep refreshing while any document is still processing; stops on its own when none are.
  const hasProcessing = documents.some((d) => d.status === "processing");
  useEffect(() => {
    if (!hasProcessing) return undefined;
    const timer = setInterval(() => load(true), POLL_MS);
    return () => clearInterval(timer);
  }, [hasProcessing, load]);

  const remove = useCallback(
    async (documentId) => {
      await documentsApi.remove(courseId, documentId);
      await load(true);
    },
    [courseId, load]
  );

  return { documents, loading, error, reload: load, remove, hasProcessing };
}
USEDOCUMENTS_EOF

# ------------------------------------------------------------ ui/ConfirmModal
write_file "$APP/src/components/ui/ConfirmModal.jsx" <<'CONFIRM_EOF'
import { useState } from "react";
import Modal from "./Modal";
import Button from "./Button";
import { getErrorMessage } from "../../services/api";

export default function ConfirmModal({ title, message, confirmLabel = "Delete", onConfirm, onClose }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const close = () => {
    if (!busy) onClose();
  };

  const run = async () => {
    setBusy(true);
    setError("");
    try {
      await onConfirm();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err, "Action failed. Please try again."));
      setBusy(false);
    }
  };

  return (
    <Modal title={title} onClose={close}>
      <p style={{ color: "var(--text-muted)", fontSize: 14, lineHeight: 1.6, marginBottom: 16 }}>{message}</p>
      {error && (
        <div className="badge badge-danger" role="alert" style={{ borderRadius: 10, padding: "10px 12px", fontWeight: 500, whiteSpace: "normal", marginBottom: 14 }}>
          {error}
        </div>
      )}
      <div className="modal-actions">
        <Button type="button" variant="ghost" onClick={close} disabled={busy}>Cancel</Button>
        <Button type="button" variant="danger" loading={busy} onClick={run}>{confirmLabel}</Button>
      </div>
    </Modal>
  );
}
CONFIRM_EOF

# ------------------------------------------------------------ courses/EditCourseModal
write_file "$APP/src/components/courses/EditCourseModal.jsx" <<'EDITMODAL_EOF'
import { useState } from "react";
import Modal from "../ui/Modal";
import Input from "../ui/Input";
import Button from "../ui/Button";
import { getErrorMessage } from "../../services/api";
import "../../pages/pages.css";

// Render conditionally ({editing && <EditCourseModal />}) so the form re-initialises each time it opens.
export default function EditCourseModal({ course, onClose, onSave }) {
  const [form, setForm] = useState({
    title: course.title ?? "",
    subject: course.subject ?? "",
    description: course.description ?? "",
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const close = () => {
    if (!saving) onClose();
  };

  const onChange = (e) => {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
    if (error) setError("");
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      await onSave({
        title: form.title.trim(),
        subject: form.subject.trim(),
        description: form.description.trim(),
      });
      onClose();
    } catch (err) {
      setError(getErrorMessage(err, "Could not save changes."));
      setSaving(false);
    }
  };

  return (
    <Modal title="Edit course" onClose={close}>
      <form style={{ display: "grid", gap: 14 }} onSubmit={onSubmit}>
        <Input label="Title" name="title" value={form.title} onChange={onChange} required autoFocus />
        <Input label="Subject" name="subject" value={form.subject} onChange={onChange} required />
        <div className="field">
          <label htmlFor="description">Description</label>
          <textarea id="description" name="description" className="input" rows={4} value={form.description} onChange={onChange} />
        </div>
        {error && (
          <div className="badge badge-danger" role="alert" style={{ borderRadius: 10, padding: "10px 12px", fontWeight: 500, whiteSpace: "normal" }}>
            {error}
          </div>
        )}
        <div className="modal-actions">
          <Button type="button" variant="ghost" onClick={close} disabled={saving}>Cancel</Button>
          <Button type="submit" loading={saving}>Save changes</Button>
        </div>
      </form>
    </Modal>
  );
}
EDITMODAL_EOF

# ------------------------------------------------------------ documents/UploadDropzone
write_file "$APP/src/components/documents/UploadDropzone.jsx" <<'DROPZONE_EOF'
import { useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import { getErrorMessage } from "../../services/api";
import "../../pages/courseDetail.css";

const isPdf = (f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");

// onUpload(file, onProgress) must return a promise and reject on failure.
export default function UploadDropzone({ onUpload }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [current, setCurrent] = useState(null); // { name, percent, index, total }
  const [errors, setErrors] = useState([]);
  const busy = current !== null;

  const handleFiles = async (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;

    const problems = [];
    const valid = [];
    files.forEach((f) => {
      if (isPdf(f)) valid.push(f);
      else problems.push(`${f.name}: only PDF files are allowed.`);
    });
    setErrors([...problems]);

    for (let i = 0; i < valid.length; i += 1) {
      const file = valid[i];
      setCurrent({ name: file.name, percent: 0, index: i + 1, total: valid.length });
      try {
        await onUpload(file, (percent) => setCurrent((c) => (c ? { ...c, percent } : c)));
      } catch (err) {
        problems.push(`${file.name}: ${getErrorMessage(err, "Upload failed.")}`);
        setErrors([...problems]);
      }
    }

    setCurrent(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  const openPicker = () => {
    if (!busy) inputRef.current?.click();
  };

  return (
    <div>
      <div
        className={`dropzone ${dragging ? "dragging" : ""} ${busy ? "busy" : ""}`}
        role="button"
        tabIndex={0}
        aria-disabled={busy}
        onClick={openPicker}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            openPicker();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!busy) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (!busy) handleFiles(e.dataTransfer.files);
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          hidden
          onChange={(e) => handleFiles(e.target.files)}
        />
        <div className="dropzone-icon"><UploadCloud size={24} /></div>
        {busy ? (
          <div className="upload-progress">
            <div className="upload-name">
              {current.name}
              {current.total > 1 && <span> · {current.index} of {current.total}</span>}
            </div>
            <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={current.percent}>
              <div className="progress-bar" style={{ width: `${current.percent}%` }} />
            </div>
            <div className="upload-sub">
              {current.percent < 100 ? `Uploading… ${current.percent}%` : "Finishing upload…"}
            </div>
          </div>
        ) : (
          <>
            <div className="dropzone-title">Drop PDFs here or click to browse</div>
            <div className="dropzone-sub">PDF files only</div>
          </>
        )}
      </div>

      {errors.length > 0 && (
        <div className="badge badge-danger upload-errors" role="alert">
          {errors.map((msg, i) => <div key={i}>{msg}</div>)}
        </div>
      )}
    </div>
  );
}
DROPZONE_EOF

# ------------------------------------------------------------ documents/DocumentList
write_file "$APP/src/components/documents/DocumentList.jsx" <<'DOCLIST_EOF'
import { AlertCircle, CheckCircle2, FileText, Loader2, Trash2 } from "lucide-react";
import Card from "../ui/Card";
import { formatDate } from "../../utils/format";
import "../../pages/courseDetail.css";

const STATUS = {
  processing: { label: "Processing", tone: "warning", Icon: Loader2, spin: true },
  ready: { label: "Ready", tone: "success", Icon: CheckCircle2 },
  failed: { label: "Failed", tone: "danger", Icon: AlertCircle },
};

export function DocumentStatus({ status }) {
  const { label, tone, Icon, spin } = STATUS[status] || STATUS.processing;
  return (
    <span className={`badge badge-${tone}`}>
      <Icon size={13} className={spin ? "spin" : undefined} /> {label}
    </span>
  );
}

export default function DocumentList({ documents, onDelete }) {
  return (
    <Card className="doc-list">
      {documents.map((doc) => (
        <div key={doc.id} className="doc-row">
          <div className="doc-icon"><FileText size={18} /></div>
          <div className="doc-info">
            <div className="doc-name" title={doc.name}>{doc.name}</div>
            <div className="doc-meta">
              {formatDate(doc.createdAt) && <span>Uploaded {formatDate(doc.createdAt)}</span>}
              {doc.status === "failed" && doc.message && <span className="doc-error">{doc.message}</span>}
            </div>
          </div>
          <DocumentStatus status={doc.status} />
          <button type="button" className="icon-btn" onClick={() => onDelete(doc)} aria-label={`Delete ${doc.name}`}>
            <Trash2 size={16} />
          </button>
        </div>
      ))}
    </Card>
  );
}
DOCLIST_EOF

# ------------------------------------------------------------ pages/courseDetail.css
write_file "$APP/src/pages/courseDetail.css" <<'DETAILCSS_EOF'
.back-link { display: inline-flex; align-items: center; gap: 6px; color: var(--text-muted); font-size: 13px; font-weight: 500; margin-bottom: 16px; transition: color 0.2s; }
.back-link:hover { color: var(--text); }

.detail-card { display: flex; flex-direction: column; gap: 14px; margin-bottom: 28px; }
.detail-top { display: flex; align-items: flex-start; gap: 14px; }
.detail-top .course-icon { width: 46px; height: 46px; flex-shrink: 0; }
.detail-heading { flex: 1; min-width: 0; }
.detail-title { font-size: 24px; overflow-wrap: anywhere; }
.detail-badges { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 8px; }
.detail-desc { color: var(--text-muted); font-size: 14.5px; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }
.detail-meta { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted); }

.dropzone {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; text-align: center;
  padding: 30px 20px; border: 1.5px dashed rgba(129, 140, 248, 0.4); border-radius: var(--radius);
  background: rgba(99, 102, 241, 0.06); cursor: pointer; transition: all 0.2s ease; outline: none;
}
.dropzone:hover, .dropzone:focus-visible, .dropzone.dragging { border-color: var(--primary-2); background: rgba(99, 102, 241, 0.14); }
.dropzone.dragging { transform: scale(1.01); }
.dropzone.busy { cursor: progress; }
.dropzone-icon { width: 48px; height: 48px; border-radius: 14px; display: grid; place-items: center; background: var(--grad); color: #fff; box-shadow: 0 6px 20px rgba(99, 102, 241, 0.45); margin-bottom: 4px; }
.dropzone-title { font-weight: 600; font-size: 15px; }
.dropzone-sub { color: var(--text-muted); font-size: 13px; }

.upload-progress { width: 100%; max-width: 420px; display: flex; flex-direction: column; gap: 8px; }
.upload-name { font-size: 14px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.upload-name span { color: var(--text-muted); font-weight: 500; }
.upload-sub { font-size: 12px; color: var(--text-muted); }
.progress { height: 8px; border-radius: 999px; background: rgba(129, 140, 248, 0.16); overflow: hidden; }
.progress-bar { height: 100%; border-radius: 999px; background: var(--grad); transition: width 0.2s ease; }
.upload-errors { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; margin-top: 12px; border-radius: 10px; padding: 10px 12px; font-weight: 500; white-space: normal; }

.docs-section { display: flex; flex-direction: column; gap: 14px; }
.doc-list { padding: 6px 16px; }
.doc-row { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--border); }
.doc-row:last-child { border-bottom: none; }
.doc-icon { width: 38px; height: 38px; border-radius: 10px; flex-shrink: 0; display: grid; place-items: center; background: rgba(99, 102, 241, 0.16); color: #a5b4fc; }
.doc-info { flex: 1; min-width: 0; }
.doc-name { font-size: 14px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.doc-meta { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 12px; color: var(--text-muted); margin-top: 2px; }
.doc-error { color: var(--danger); }
.icon-btn { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 8px; border: none; background: transparent; color: var(--text-muted); cursor: pointer; transition: all 0.2s ease; flex-shrink: 0; }
.icon-btn:hover { color: var(--danger); background: rgba(248, 113, 113, 0.12); }
.spin { animation: spin 1s linear infinite; }
.docs-empty { text-align: center; color: var(--text-muted); font-size: 14px; padding: 8px 0; }

@media (max-width: 520px) {
  .detail-title { font-size: 20px; }
  .detail-top { flex-wrap: wrap; }
  .doc-row { flex-wrap: wrap; }
  .doc-info { flex-basis: calc(100% - 100px); }
}
DETAILCSS_EOF

# ------------------------------------------------------------ pages/CourseDetail
write_file "$APP/src/pages/CourseDetail.jsx" <<'DETAILPAGE_EOF'
import { useState } from "react";
import { Link, useParams } from "react-router";
import { AlertCircle, ArrowLeft, BookOpen, Calendar, Pencil, RefreshCw } from "lucide-react";
import Card from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import ConfirmModal from "../components/ui/ConfirmModal";
import EditCourseModal from "../components/courses/EditCourseModal";
import UploadDropzone from "../components/documents/UploadDropzone";
import DocumentList from "../components/documents/DocumentList";
import useCourse from "../hooks/useCourse";
import useDocuments from "../hooks/useDocuments";
import { documentsApi } from "../services/documents";
import { formatDate } from "../utils/format";
import "./pages.css";
import "./courseDetail.css";

export default function CourseDetail() {
  const { courseId } = useParams();
  const { course, loading, error, reload, update } = useCourse(courseId);
  const docs = useDocuments(courseId);
  const [editing, setEditing] = useState(false);
  const [toDelete, setToDelete] = useState(null);

  const handleUpload = async (file, onProgress) => {
    await documentsApi.upload(courseId, file, onProgress);
    await docs.reload(true);
  };

  if (loading) {
    return (
      <div className="page">
        <Link to="/courses" className="back-link"><ArrowLeft size={16} /> Back to courses</Link>
        <div className="card skeleton-card" aria-busy="true">
          <div className="skeleton skeleton-icon" />
          <div className="skeleton skeleton-line" style={{ width: "45%", height: 20 }} />
          <div className="skeleton skeleton-line" />
          <div className="skeleton skeleton-line" style={{ width: "60%" }} />
        </div>
      </div>
    );
  }

  if (error || !course) {
    return (
      <div className="page">
        <Link to="/courses" className="back-link"><ArrowLeft size={16} /> Back to courses</Link>
        <Card className="state-card" role="alert">
          <div className="state-icon state-icon-danger"><AlertCircle size={26} /></div>
          <h3>Couldn't load this course</h3>
          <p>{error || "Course not found."}</p>
          <Button variant="secondary" icon={RefreshCw} onClick={reload}>Try again</Button>
        </Card>
      </div>
    );
  }

  const created = formatDate(course.created_at);
  const updated = formatDate(course.updated_at);

  return (
    <div className="page">
      <Link to="/courses" className="back-link"><ArrowLeft size={16} /> Back to courses</Link>

      <Card className="detail-card">
        <div className="detail-top">
          <div className="course-icon"><BookOpen size={20} /></div>
          <div className="detail-heading">
            <h2 className="detail-title">{course.title}</h2>
            <div className="detail-badges">
              {course.subject && <Badge>{course.subject}</Badge>}
              {created && <span className="detail-meta"><Calendar size={13} /> Created {created}</span>}
              {updated && updated !== created && <span className="detail-meta">Updated {updated}</span>}
            </div>
          </div>
          <Button variant="secondary" size="sm" icon={Pencil} onClick={() => setEditing(true)}>Edit</Button>
        </div>
        <p className="detail-desc">{course.description || "No description provided."}</p>
      </Card>

      <section className="docs-section">
        <div className="section-head" style={{ marginBottom: 0 }}>
          <h3>Documents{!docs.loading && !docs.error ? ` (${docs.documents.length})` : ""}</h3>
        </div>

        <UploadDropzone onUpload={handleUpload} />

        {docs.loading ? (
          <div className="card skeleton-card" aria-busy="true">
            <div className="skeleton skeleton-line" style={{ width: "60%" }} />
            <div className="skeleton skeleton-line" style={{ width: "40%" }} />
          </div>
        ) : docs.error ? (
          <Card className="state-card state-error" role="alert">
            <div className="state-icon state-icon-danger"><AlertCircle size={26} /></div>
            <h3>Couldn't load documents</h3>
            <p>{docs.error}</p>
            <Button variant="secondary" icon={RefreshCw} onClick={() => docs.reload()}>Try again</Button>
          </Card>
        ) : docs.documents.length === 0 ? (
          <Card><p className="docs-empty">No PDFs uploaded yet. Upload your first one above.</p></Card>
        ) : (
          <DocumentList documents={docs.documents} onDelete={setToDelete} />
        )}
      </section>

      {editing && (
        <EditCourseModal course={course} onClose={() => setEditing(false)} onSave={update} />
      )}

      {toDelete && (
        <ConfirmModal
          title="Delete document"
          message={`Delete "${toDelete.name}"? This removes the PDF from this course and cannot be undone.`}
          onConfirm={() => docs.remove(toDelete.id)}
          onClose={() => setToDelete(null)}
        />
      )}
    </div>
  );
}
DETAILPAGE_EOF

# ------------------------------------------------------------ App.jsx (targeted patch)
echo "==> Wiring route in $APP/src/App.jsx"
backup "$APP/src/App.jsx"
node - "$APP/src/App.jsx" <<'PATCH_EOF'
const fs = require("fs");
const file = process.argv[2];
let s = fs.readFileSync(file, "utf8");

if (s.includes("./pages/CourseDetail")) {
  console.log("    App.jsx already wired; no change.");
  process.exit(0);
}

const route = /<Route path="\/courses\/:courseId" element=\{<Stub[^>]*\/>\} \/>/;
const imp = 'import Stub from "./pages/Stub";';

if (!route.test(s) || !s.includes(imp)) {
  console.error("Error: expected Stub route/import not found in App.jsx. App.jsx was NOT changed (backup kept).");
  process.exit(2);
}

s = s
  .replace(route, '<Route path="/courses/:courseId" element={<CourseDetail />} />')
  .replace(imp, imp + '\nimport CourseDetail from "./pages/CourseDetail";');

fs.writeFileSync(file, s);
console.log("    App.jsx updated.");
PATCH_EOF

echo "==> Verifying with npm run build in $APP"
( cd "$APP" && npm run build )

echo "==> Done. Backups (if any): $BACKUP_DIR"
echo "    To verify manually: cd $APP && npm run build && npm run dev"
