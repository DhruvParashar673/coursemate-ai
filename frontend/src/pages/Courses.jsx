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
