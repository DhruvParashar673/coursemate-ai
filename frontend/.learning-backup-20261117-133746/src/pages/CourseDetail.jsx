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
