#!/usr/bin/env bash
# create-missing-files.sh — run from the project root (the folder that contains frontend/).
set -euo pipefail

FRONTEND="frontend"
LAYOUT="$FRONTEND/src/components/layout/AppLayout.jsx"
STUB="$FRONTEND/src/pages/Stub.jsx"

[ -d "$FRONTEND/src" ] || { echo "Error: $FRONTEND/src not found. Run this from the project root." >&2; exit 1; }

# AppLayout reuses these existing files; stop early if any are missing.
for dep in \
  "$FRONTEND/src/components/ui/Button.jsx" \
  "$FRONTEND/src/components/ui/Card.jsx" \
  "$FRONTEND/src/components/ui/Badge.jsx" \
  "$FRONTEND/src/components/layout/layout.css"; do
  [ -f "$dep" ] || { echo "Error: required file missing: $dep" >&2; exit 1; }
done

for f in "$LAYOUT" "$STUB"; do
  if [ -e "$f" ]; then
    cp -p "$f" "$f.bak.$(date +%Y%m%d-%H%M%S)"
    echo "    backed up existing $f"
  fi
done

mkdir -p "$FRONTEND/src/components/layout" "$FRONTEND/src/pages"

echo "==> Writing $LAYOUT"
cat > "$LAYOUT" <<'APPLAYOUT_EOF'
import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { LayoutDashboard, BookOpen, MessageSquare, Sparkles, LogOut, Menu } from "lucide-react";
import Button from "../ui/Button";
import "./layout.css";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/courses", label: "Courses", icon: BookOpen },
  { to: "/chat", label: "AI Chat", icon: MessageSquare },
];

const TITLES = { "/dashboard": "Dashboard", "/courses": "Courses", "/chat": "AI Chat" };

export default function AppLayout() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const navigate = useNavigate();

  const title =
    TITLES[pathname] || (pathname.startsWith("/courses/") ? "Course Details" : "CourseMate AI");

  const logout = () => {
    localStorage.removeItem("token");
    navigate("/login", { replace: true });
  };

  return (
    <div className="shell">
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-logo"><Sparkles size={18} color="#fff" /></div>
          CourseMate AI
        </div>
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
            onClick={() => setOpen(false)}
          >
            <Icon size={18} /> {label}
          </NavLink>
        ))}
        <div className="sidebar-footer">
          <Button variant="ghost" block icon={LogOut} onClick={logout}>Log out</Button>
        </div>
      </aside>
      <div className={`scrim ${open ? "open" : ""}`} onClick={() => setOpen(false)} />

      <div className="main">
        <header className="topbar">
          <Button variant="ghost" size="sm" className="menu-btn" icon={Menu} onClick={() => setOpen(true)} aria-label="Open menu" />
          <h1 className="topbar-title">{title}</h1>
          <div className="topbar-spacer" />
          <div className="avatar">U</div>
        </header>
        <main className="content"><Outlet /></main>
      </div>
    </div>
  );
}
APPLAYOUT_EOF

echo "==> Writing $STUB"
cat > "$STUB" <<'STUB_EOF'
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
STUB_EOF

echo "==> Running npm run build in $FRONTEND"
( cd "$FRONTEND" && npm run build )

echo "==> Done."

