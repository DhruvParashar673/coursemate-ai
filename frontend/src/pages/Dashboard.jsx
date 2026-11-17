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
