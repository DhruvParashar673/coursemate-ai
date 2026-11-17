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
