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
