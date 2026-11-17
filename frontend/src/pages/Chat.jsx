import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { BookOpen } from "lucide-react";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import ChatPanel from "../components/chat/ChatPanel";
import { CourseGridSkeleton, ErrorState } from "../components/courses/CourseStates";
import useCourses from "../hooks/useCourses";
import "./pages.css";
import "./chat.css";

export default function Chat() {
  const { courses, loading, error, reload } = useCourses();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  if (loading) {
    return (
      <div className="page">
        <CourseGridSkeleton count={1} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <ErrorState message={error} onRetry={reload} />
      </div>
    );
  }

  if (courses.length === 0) {
    return (
      <div className="page">
        <Card className="state-card">
          <div className="state-icon"><BookOpen size={26} /></div>
          <h3>Create a course first</h3>
          <p>Chat works on the PDFs inside a course. Create one and upload your study material to get started.</p>
          <Button onClick={() => navigate("/courses")}>Go to courses</Button>
        </Card>
      </div>
    );
  }

  const requested = params.get("course");
  const selected = courses.find((c) => String(c.id) === requested) || courses[0];

  return (
    <div className="chat-page">
      <div className="chat-head">
        <div>
          <h2>AI Chat</h2>
          <p className="page-sub">Ask questions about the PDFs in a course.</p>
        </div>
        <select
          className="input chat-course-select"
          value={String(selected.id)}
          onChange={(e) => setParams({ course: e.target.value }, { replace: true })}
          disabled={busy}
          aria-label="Select course"
        >
          {courses.map((c) => (
            <option key={c.id} value={String(c.id)}>{c.title}</option>
          ))}
        </select>
      </div>

      <ChatPanel key={selected.id} course={selected} onBusyChange={setBusy} />
    </div>
  );
}
