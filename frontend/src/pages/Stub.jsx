import { Link } from "react-router";
import Card from "../components/ui/Card";
import Badge from "../components/ui/Badge";

// Placeholder used for every page not built yet.
export default function Stub({ title, hint }) {
  return (
    <Card>
      <Badge tone="info">Coming next</Badge>
      <h2 style={{ margin: "12px 0 6px" }}>{title}</h2>
      <p style={{ color: "var(--text-muted)", fontSize: 14 }}>{hint}</p>
      {title !== "Courses" && (
        <p style={{ marginTop: 14, fontSize: 13 }}>
          <Link to="/courses" style={{ color: "#a5b4fc" }}>← Back to courses</Link>
        </p>
      )}
    </Card>
  );
}
