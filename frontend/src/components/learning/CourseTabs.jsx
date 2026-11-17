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
