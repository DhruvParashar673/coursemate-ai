#!/usr/bin/env bash
# add-dashboard.sh — run from the project root.
# Works with ./frontend (frontend/src/...) or ./ (src/...).
# Existing files are backed up to <app>/.dashboard-backup-<timestamp>/ before being changed.
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
BACKUP_DIR="$APP/.dashboard-backup-$STAMP"

for dep in "src/App.jsx" "src/services/api.js" "src/components/layout/AppLayout.jsx" \
           "src/components/ui/Button.jsx" "src/components/ui/Card.jsx" "src/components/ui/Badge.jsx" "src/components/ui/Input.jsx"; do
  [ -f "$APP/$dep" ] || { echo "Error: required existing file missing: $APP/$dep" >&2; exit 1; }
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

# ------------------------------------------------------------ services/courses.js
write_file "$APP/src/services/courses.js" <<'COURSES_API_EOF'
import api from "./api";

export const coursesApi = {
  list: () => api.get("/courses").then((r) => r.data),
  create: ({ title, description, subject }) =>
    api.post("/courses", { title, description, subject }).then((r) => r.data),
};
COURSES_API_EOF

# ------------------------------------------------------------ hooks/useCourses.js
write_file "$APP/src/hooks/useCourses.js" <<'USECOURSES_EOF'
import { useCallback, useEffect, useState } from "react";
import { coursesApi } from "../services/courses";
import { getErrorMessage } from "../services/api";

export default function useCourses() {
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await coursesApi.list();
      setCourses(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load courses."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { courses, loading, error, reload: load };
}
USECOURSES_EOF

# ------------------------------------------------------------ ui/Modal
write_file "$APP/src/components/ui/Modal.jsx" <<'MODAL_EOF'
import { useEffect } from "react";
import { X } from "lucide-react";
import "./modal.css";

export default function Modal({ open = true, title, onClose, children }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal card" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
MODAL_EOF

write_file "$APP/src/components/ui/modal.css" <<'MODALCSS_EOF'
.modal-backdrop {
  position: fixed; inset: 0; z-index: 100; display: grid; place-items: center; padding: 16px;
  background: rgba(2, 4, 20, 0.7); backdrop-filter: blur(4px); animation: fadeUp 0.2s ease both;
}
.modal { width: 100%; max-width: 480px; max-height: calc(100vh - 32px); overflow-y: auto; }
.modal-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.modal-head h3 { font-size: 18px; }
.modal-close {
  display: grid; place-items: center; width: 32px; height: 32px; border-radius: 8px;
  background: transparent; border: none; color: var(--text-muted); cursor: pointer; transition: all 0.2s ease;
}
.modal-close:hover { color: var(--text); background: rgba(99, 102, 241, 0.14); }
MODALCSS_EOF

# ------------------------------------------------------------ courses/CourseCard
write_file "$APP/src/components/courses/CourseCard.jsx" <<'COURSECARD_EOF'
import { Link } from "react-router";
import { BookOpen, Calendar } from "lucide-react";
import Card from "../ui/Card";
import Badge from "../ui/Badge";
import "../../pages/pages.css";

function formatDate(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export default function CourseCard({ course }) {
  const date = formatDate(course.created_at);
  return (
    <Link to={`/courses/${course.id}`} className="course-link" aria-label={`Open ${course.title}`}>
      <Card hover className="course-card">
        <div className="course-card-top">
          <div className="course-icon"><BookOpen size={18} /></div>
          {course.subject && <Badge>{course.subject}</Badge>}
        </div>
        <h3 className="course-title">{course.title}</h3>
        <p className="course-desc">{course.description || "No description provided."}</p>
        {date && (
          <div className="course-meta"><Calendar size={13} /> Created {date}</div>
        )}
      </Card>
    </Link>
  );
}
COURSECARD_EOF

# ------------------------------------------------------------ courses/CourseStates
write_file "$APP/src/components/courses/CourseStates.jsx" <<'COURSESTATES_EOF'
import { AlertCircle, FolderPlus, Plus, RefreshCw } from "lucide-react";
import Card from "../ui/Card";
import Button from "../ui/Button";
import "../../pages/pages.css";

export function EmptyCourses({ onCreate }) {
  return (
    <Card className="state-card">
      <div className="state-icon"><FolderPlus size={26} /></div>
      <h3>No courses yet</h3>
      <p>Create your first course to start uploading PDFs and studying with AI.</p>
      <Button icon={Plus} onClick={onCreate}>Create course</Button>
    </Card>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <Card className="state-card state-error" role="alert">
      <div className="state-icon state-icon-danger"><AlertCircle size={26} /></div>
      <h3>Couldn't load courses</h3>
      <p>{message}</p>
      <Button variant="secondary" icon={RefreshCw} onClick={onRetry}>Try again</Button>
    </Card>
  );
}

export function CourseGridSkeleton({ count = 3 }) {
  return (
    <div className="course-grid" aria-busy="true">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="card skeleton-card">
          <div className="skeleton skeleton-icon" />
          <div className="skeleton skeleton-line" style={{ width: "70%" }} />
          <div className="skeleton skeleton-line" />
          <div className="skeleton skeleton-line" style={{ width: "50%" }} />
        </div>
      ))}
    </div>
  );
}
COURSESTATES_EOF

# ------------------------------------------------------------ courses/CreateCourseModal
write_file "$APP/src/components/courses/CreateCourseModal.jsx" <<'CREATEMODAL_EOF'
import { useState } from "react";
import Modal from "../ui/Modal";
import Input from "../ui/Input";
import Button from "../ui/Button";
import { coursesApi } from "../../services/courses";
import { getErrorMessage } from "../../services/api";
import "../../pages/pages.css";

// Render conditionally ({show && <CreateCourseModal />}) so the form resets each time it opens.
export default function CreateCourseModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ title: "", subject: "", description: "" });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const close = () => {
    if (!submitting) onClose();
  };

  const onChange = (e) => {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
    if (error) setError("");
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await coursesApi.create({
        title: form.title.trim(),
        subject: form.subject.trim(),
        description: form.description.trim(),
      });
      await onCreated();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err, "Could not create the course."));
      setSubmitting(false);
    }
  };

  return (
    <Modal title="Create course" onClose={close}>
      <form style={{ display: "grid", gap: 14 }} onSubmit={onSubmit}>
        <Input label="Title" name="title" placeholder="e.g. Operating Systems" value={form.title} onChange={onChange} required autoFocus />
        <Input label="Subject" name="subject" placeholder="e.g. Computer Science" value={form.subject} onChange={onChange} required />
        <div className="field">
          <label htmlFor="description">Description</label>
          <textarea
            id="description"
            name="description"
            className="input"
            rows={4}
            placeholder="What is this course about?"
            value={form.description}
            onChange={onChange}
          />
        </div>
        {error && (
          <div className="badge badge-danger" role="alert" style={{ borderRadius: 10, padding: "10px 12px", fontWeight: 500, whiteSpace: "normal" }}>
            {error}
          </div>
        )}
        <div className="modal-actions">
          <Button type="button" variant="ghost" onClick={close} disabled={submitting}>Cancel</Button>
          <Button type="submit" loading={submitting}>Create course</Button>
        </div>
      </form>
    </Modal>
  );
}
CREATEMODAL_EOF

# ------------------------------------------------------------ pages/Dashboard
write_file "$APP/src/pages/Dashboard.jsx" <<'DASHBOARD_EOF'
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { BookOpen, Layers, Plus } from "lucide-react";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import CourseCard from "../components/courses/CourseCard";
import CreateCourseModal from "../components/courses/CreateCourseModal";
import { CourseGridSkeleton, EmptyCourses, ErrorState } from "../components/courses/CourseStates";
import useCourses from "../hooks/useCourses";
import { authApi } from "../services/api";
import "./pages.css";

export default function Dashboard() {
  const { courses, loading, error, reload } = useCourses();
  const [showCreate, setShowCreate] = useState(false);
  const [firstName, setFirstName] = useState("");

  useEffect(() => {
    let active = true;
    authApi
      .me()
      .then((u) => {
        if (active && u?.name) setFirstName(u.name.trim().split(" ")[0]);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  const recent = useMemo(
    () =>
      [...courses]
        .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
        .slice(0, 6),
    [courses]
  );
  const subjectCount = useMemo(
    () => new Set(courses.map((c) => c.subject).filter(Boolean)).size,
    [courses]
  );

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Welcome back{firstName ? `, ${firstName}` : ""} 👋</h2>
          <p className="page-sub">Pick up where you left off or start a new course.</p>
        </div>
        <Button icon={Plus} onClick={() => setShowCreate(true)}>New course</Button>
      </div>

      {error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : (
        <>
          <div className="stats-grid">
            <Card className="stat-card">
              <div className="stat-icon"><BookOpen size={20} /></div>
              <div>
                <div className="stat-value">{loading ? "–" : courses.length}</div>
                <div className="stat-label">Total courses</div>
              </div>
            </Card>
            <Card className="stat-card">
              <div className="stat-icon stat-icon-blue"><Layers size={20} /></div>
              <div>
                <div className="stat-value">{loading ? "–" : subjectCount}</div>
                <div className="stat-label">Subjects</div>
              </div>
            </Card>
          </div>

          <div className="section-head">
            <h3>Recent courses</h3>
            {courses.length > 0 && <Link to="/courses" className="link-accent">View all →</Link>}
          </div>

          {loading ? (
            <CourseGridSkeleton />
          ) : courses.length === 0 ? (
            <EmptyCourses onCreate={() => setShowCreate(true)} />
          ) : (
            <div className="course-grid">
              {recent.map((c) => <CourseCard key={c.id} course={c} />)}
            </div>
          )}
        </>
      )}

      {showCreate && (
        <CreateCourseModal onClose={() => setShowCreate(false)} onCreated={reload} />
      )}
    </div>
  );
}
DASHBOARD_EOF

# ------------------------------------------------------------ pages/Courses
write_file "$APP/src/pages/Courses.jsx" <<'COURSES_PAGE_EOF'
import { useState } from "react";
import { Plus } from "lucide-react";
import Button from "../components/ui/Button";
import CourseCard from "../components/courses/CourseCard";
import CreateCourseModal from "../components/courses/CreateCourseModal";
import { CourseGridSkeleton, EmptyCourses, ErrorState } from "../components/courses/CourseStates";
import useCourses from "../hooks/useCourses";
import "./pages.css";

export default function Courses() {
  const { courses, loading, error, reload } = useCourses();
  const [showCreate, setShowCreate] = useState(false);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Your courses</h2>
          <p className="page-sub">
            {loading || error
              ? "Manage the courses you study from."
              : `${courses.length} ${courses.length === 1 ? "course" : "courses"}`}
          </p>
        </div>
        <Button icon={Plus} onClick={() => setShowCreate(true)}>New course</Button>
      </div>

      {error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : loading ? (
        <CourseGridSkeleton count={6} />
      ) : courses.length === 0 ? (
        <EmptyCourses onCreate={() => setShowCreate(true)} />
      ) : (
        <div className="course-grid">
          {courses.map((c) => <CourseCard key={c.id} course={c} />)}
        </div>
      )}

      {showCreate && (
        <CreateCourseModal onClose={() => setShowCreate(false)} onCreated={reload} />
      )}
    </div>
  );
}
COURSES_PAGE_EOF

# ------------------------------------------------------------ pages/pages.css
write_file "$APP/src/pages/pages.css" <<'PAGESCSS_EOF'
.page-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }
.page-head h2 { font-size: 26px; }
.page-sub { color: var(--text-muted); font-size: 14px; margin-top: 4px; }

.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 16px; margin-bottom: 28px; }
.stat-card { display: flex; align-items: center; gap: 14px; }
.stat-icon { width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center; background: rgba(99, 102, 241, 0.16); color: #a5b4fc; }
.stat-icon-blue { background: rgba(56, 189, 248, 0.14); color: var(--accent-blue); }
.stat-value { font-family: var(--font-display); font-size: 28px; font-weight: 700; line-height: 1; }
.stat-label { font-size: 13px; color: var(--text-muted); margin-top: 4px; }

.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.section-head h3 { font-size: 18px; }
.link-accent { color: #a5b4fc; font-size: 13px; font-weight: 600; }
.link-accent:hover { color: #fff; }

.course-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.course-link { display: block; color: inherit; border-radius: var(--radius); }
.course-link:focus-visible { outline: 2px solid var(--primary); outline-offset: 3px; }
.course-card { height: 100%; display: flex; flex-direction: column; gap: 10px; }
.course-card-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.course-icon { width: 38px; height: 38px; border-radius: 10px; display: grid; place-items: center; background: var(--grad); color: #fff; box-shadow: 0 6px 18px rgba(99, 102, 241, 0.4); }
.course-title { font-size: 17px; font-weight: 600; overflow-wrap: anywhere; }
.course-desc {
  color: var(--text-muted); font-size: 13.5px; line-height: 1.5; overflow: hidden;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
}
.course-meta { margin-top: auto; padding-top: 4px; display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted); }

.state-card { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 10px; padding: 44px 20px; }
.state-card h3 { font-size: 18px; }
.state-card p { color: var(--text-muted); font-size: 14px; max-width: 380px; margin-bottom: 6px; }
.state-icon { width: 56px; height: 56px; border-radius: 16px; display: grid; place-items: center; background: rgba(99, 102, 241, 0.16); color: #a5b4fc; }
.state-icon-danger { background: rgba(248, 113, 113, 0.12); color: var(--danger); }

.skeleton-card { display: flex; flex-direction: column; gap: 12px; }
.skeleton {
  border-radius: 8px; background: linear-gradient(90deg, rgba(129, 140, 248, 0.08), rgba(129, 140, 248, 0.2), rgba(129, 140, 248, 0.08));
  background-size: 200% 100%; animation: shimmer 1.4s ease-in-out infinite;
}
.skeleton-icon { width: 38px; height: 38px; border-radius: 10px; }
.skeleton-line { height: 12px; }
@keyframes shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }

textarea.input { resize: vertical; min-height: 96px; line-height: 1.5; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 4px; }

@media (max-width: 520px) {
  .page-head h2 { font-size: 22px; }
  .page-head > .btn { width: 100%; }
  .modal-actions { flex-direction: column-reverse; }
  .modal-actions .btn { width: 100%; }
}
PAGESCSS_EOF

# ------------------------------------------------------------ App.jsx (targeted patch)
echo "==> Wiring routes in $APP/src/App.jsx"
backup "$APP/src/App.jsx"
node - "$APP/src/App.jsx" <<'PATCH_EOF'
const fs = require("fs");
const file = process.argv[2];
let s = fs.readFileSync(file, "utf8");

if (s.includes("./pages/Dashboard")) {
  console.log("    App.jsx already wired; no change.");
  process.exit(0);
}

const dash = /<Route path="\/dashboard" element=\{<Stub[^>]*\/>\} \/>/;
const crs = /<Route path="\/courses" element=\{<Stub[^>]*\/>\} \/>/;
const imp = 'import Stub from "./pages/Stub";';

if (!dash.test(s) || !crs.test(s) || !s.includes(imp)) {
  console.error("Error: expected Stub routes/import not found in App.jsx. App.jsx was NOT changed (backup kept).");
  process.exit(2);
}

s = s
  .replace(dash, '<Route path="/dashboard" element={<Dashboard />} />')
  .replace(crs, '<Route path="/courses" element={<Courses />} />')
  .replace(imp, imp + '\nimport Dashboard from "./pages/Dashboard";\nimport Courses from "./pages/Courses";');

fs.writeFileSync(file, s);
console.log("    App.jsx updated.");
PATCH_EOF

echo "==> Verifying with npm run build in $APP"
( cd "$APP" && npm run build )

echo "==> Done. Backups (if any): $BACKUP_DIR"
echo "    To verify manually: cd $APP && npm run build && npm run dev"
