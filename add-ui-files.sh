#!/usr/bin/env bash
# add-ui-files.sh — run from the project root.
# Works whether the app lives in ./frontend (frontend/src/...) or directly in ./ (src/...).
# Never overwrites: any file that already exists is skipped.
set -euo pipefail

if [ -d "frontend/src" ]; then
  APP="frontend"
elif [ -d "src" ] && [ -f "package.json" ]; then
  APP="."
else
  echo "Error: could not find frontend/src or ./src with package.json. Run from the project root." >&2
  exit 1
fi
echo "==> Using app directory: $APP"

write_file() {
  local f="$1"
  if [ -e "$f" ]; then
    echo "    skipped (already exists): $f"
    cat > /dev/null
  else
    mkdir -p "$(dirname "$f")"
    cat > "$f"
    echo "    created: $f"
  fi
}

# ---------------------------------------------------------------- Button
write_file "$APP/src/components/ui/Button.jsx" <<'BUTTON_EOF'
export default function Button({
  variant = "primary",
  size,
  block = false,
  loading = false,
  icon: Icon,
  children,
  className = "",
  ...props
}) {
  const cls = ["btn", `btn-${variant}`, size === "sm" && "btn-sm", block && "btn-block", className]
    .filter(Boolean)
    .join(" ");
  return (
    <button className={cls} disabled={loading || props.disabled} {...props}>
      {loading ? <span className="spinner" /> : Icon && <Icon size={16} />}
      {children}
    </button>
  );
}
BUTTON_EOF

# ---------------------------------------------------------------- Card
write_file "$APP/src/components/ui/Card.jsx" <<'CARD_EOF'
export default function Card({ hover = false, className = "", children, ...props }) {
  return (
    <div className={`card ${hover ? "card-hover" : ""} ${className}`} {...props}>
      {children}
    </div>
  );
}
CARD_EOF

# ---------------------------------------------------------------- Badge
write_file "$APP/src/components/ui/Badge.jsx" <<'BADGE_EOF'
export default function Badge({ tone = "default", children }) {
  const cls = tone === "default" ? "badge" : `badge badge-${tone}`;
  return <span className={cls}>{children}</span>;
}
BADGE_EOF

# ---------------------------------------------------------------- Input
write_file "$APP/src/components/ui/Input.jsx" <<'INPUT_EOF'
export default function Input({ label, error, id, className = "", ...props }) {
  const inputId = id || props.name;
  return (
    <div className="field">
      {label && <label htmlFor={inputId}>{label}</label>}
      <input id={inputId} className={`input ${className}`} {...props} />
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}
INPUT_EOF

# ---------------------------------------------------------------- layout.css
# Self-contained: also carries the theme tokens and primitive styles (identical to index.css),
# so the UI renders correctly even if index.css is missing. Duplicates are harmless.
write_file "$APP/src/components/layout/layout.css" <<'LAYOUTCSS_EOF'
/* ---------- Theme tokens (same values as index.css) ---------- */
:root {
  --bg: #0a0d1f;
  --bg-elev: #11152e;
  --bg-card: rgba(22, 27, 58, 0.72);
  --border: rgba(129, 140, 248, 0.16);
  --text: #e8eaff;
  --text-muted: #9aa0c7;
  --primary: #6366f1;
  --primary-2: #8b5cf6;
  --accent-blue: #38bdf8;
  --success: #34d399;
  --warning: #fbbf24;
  --danger: #f87171;
  --grad: linear-gradient(135deg, #6366f1 0%, #8b5cf6 55%, #38bdf8 120%);
  --radius: 14px;
  --radius-sm: 10px;
  --shadow: 0 10px 40px rgba(2, 4, 24, 0.55);
  --glow: 0 0 0 1px var(--border), 0 8px 30px rgba(99, 102, 241, 0.18);
  --font: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-display: "Space Grotesk", var(--font);
  --sidebar-w: 248px;
}

* { box-sizing: border-box; }
html, body, #root { height: 100%; }
body {
  margin: 0;
  font-family: var(--font);
  color: var(--text);
  background:
    radial-gradient(900px 500px at 85% -10%, rgba(139, 92, 246, 0.18), transparent 60%),
    radial-gradient(700px 500px at -5% 105%, rgba(56, 189, 248, 0.12), transparent 60%),
    var(--bg);
  background-attachment: fixed;
  -webkit-font-smoothing: antialiased;
}
h1, h2, h3 { font-family: var(--font-display); letter-spacing: -0.02em; margin: 0; }
p { margin: 0; }
a { color: inherit; text-decoration: none; }

@keyframes fadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
@keyframes spin { to { transform: rotate(360deg); } }
.anim-fade-up { animation: fadeUp 0.45s ease both; }

/* ---------- Button ---------- */
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  padding: 10px 18px; border-radius: var(--radius-sm); border: 1px solid transparent;
  font-family: inherit; font-size: 14px; font-weight: 600; cursor: pointer; color: #fff;
  transition: transform 0.15s ease, box-shadow 0.2s ease, background 0.2s ease, opacity 0.2s;
}
.btn:hover:not(:disabled) { transform: translateY(-1px); }
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
.btn-primary { background: var(--grad); box-shadow: 0 6px 22px rgba(99, 102, 241, 0.4); }
.btn-primary:hover:not(:disabled) { box-shadow: 0 8px 28px rgba(139, 92, 246, 0.55); }
.btn-secondary { background: rgba(99, 102, 241, 0.14); border-color: var(--border); color: var(--text); }
.btn-secondary:hover:not(:disabled) { background: rgba(99, 102, 241, 0.24); }
.btn-ghost { background: transparent; color: var(--text-muted); }
.btn-ghost:hover:not(:disabled) { color: var(--text); background: rgba(99, 102, 241, 0.1); }
.btn-danger { background: rgba(248, 113, 113, 0.14); border-color: rgba(248, 113, 113, 0.35); color: var(--danger); }
.btn-sm { padding: 6px 12px; font-size: 13px; }
.btn-block { width: 100%; }
.spinner { width: 15px; height: 15px; border: 2px solid rgba(255, 255, 255, 0.35); border-top-color: #fff; border-radius: 50%; animation: spin 0.7s linear infinite; }

/* ---------- Card ---------- */
.card {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 20px; backdrop-filter: blur(10px); box-shadow: var(--shadow);
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}
.card-hover { cursor: pointer; }
.card-hover:hover { transform: translateY(-3px); border-color: rgba(139, 92, 246, 0.5); box-shadow: var(--glow); }

/* ---------- Input ---------- */
.field { display: flex; flex-direction: column; gap: 6px; }
.field label { font-size: 13px; font-weight: 500; color: var(--text-muted); }
.input {
  width: 100%; padding: 11px 14px; border-radius: var(--radius-sm);
  background: rgba(10, 13, 31, 0.7); border: 1px solid var(--border); color: var(--text);
  font-family: inherit; font-size: 14px; outline: none; transition: border-color 0.2s, box-shadow 0.2s;
}
.input::placeholder { color: #626894; }
.input:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.25); }
.field-error { font-size: 12px; color: var(--danger); }

/* ---------- Badge ---------- */
.badge {
  display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px;
  border-radius: 999px; font-size: 12px; font-weight: 600;
  background: rgba(99, 102, 241, 0.16); color: #a5b4fc; border: 1px solid var(--border);
}
.badge-success { background: rgba(52, 211, 153, 0.12); color: var(--success); border-color: rgba(52, 211, 153, 0.3); }
.badge-warning { background: rgba(251, 191, 36, 0.12); color: var(--warning); border-color: rgba(251, 191, 36, 0.3); }
.badge-danger { background: rgba(248, 113, 113, 0.12); color: var(--danger); border-color: rgba(248, 113, 113, 0.3); }
.badge-info { background: rgba(56, 189, 248, 0.12); color: var(--accent-blue); border-color: rgba(56, 189, 248, 0.3); }

/* ---------- App shell ---------- */
.shell { display: flex; min-height: 100vh; }

.sidebar {
  width: var(--sidebar-w); flex-shrink: 0; position: fixed; inset: 0 auto 0 0; z-index: 40;
  display: flex; flex-direction: column; gap: 6px; padding: 20px 14px;
  background: rgba(13, 17, 40, 0.92); border-right: 1px solid var(--border);
  backdrop-filter: blur(14px); transition: transform 0.3s ease;
}
.brand { display: flex; align-items: center; gap: 10px; padding: 4px 10px 18px; font-family: var(--font-display); font-weight: 700; font-size: 18px; }
.brand-logo { width: 34px; height: 34px; border-radius: 10px; background: var(--grad); display: grid; place-items: center; box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5); }

.nav-link {
  display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: var(--radius-sm);
  color: var(--text-muted); font-size: 14px; font-weight: 500; transition: all 0.2s ease;
}
.nav-link:hover { color: var(--text); background: rgba(99, 102, 241, 0.1); }
.nav-link.active { color: #fff; background: linear-gradient(90deg, rgba(99, 102, 241, 0.35), rgba(139, 92, 246, 0.12)); box-shadow: inset 2px 0 0 var(--primary-2); }
.sidebar-footer { margin-top: auto; }

.main { flex: 1; margin-left: var(--sidebar-w); min-width: 0; display: flex; flex-direction: column; }
.topbar {
  position: sticky; top: 0; z-index: 30; display: flex; align-items: center; gap: 14px;
  padding: 14px 28px; background: rgba(10, 13, 31, 0.7); backdrop-filter: blur(12px); border-bottom: 1px solid var(--border);
}
.topbar-title { font-family: var(--font-display); font-size: 18px; font-weight: 600; }
.topbar-spacer { flex: 1; }
.menu-btn { display: none; }
.avatar { width: 34px; height: 34px; border-radius: 50%; background: var(--grad); display: grid; place-items: center; font-weight: 700; font-size: 13px; }
.content { padding: 28px; max-width: 1200px; width: 100%; margin: 0 auto; animation: fadeUp 0.4s ease both; }
.scrim { display: none; }

/* ---------- Auth pages ---------- */
.auth-wrap { min-height: 100vh; display: grid; place-items: center; padding: 24px; }
.auth-card { width: 100%; max-width: 420px; }

/* ---------- Responsive: sidebar becomes a slide-in drawer ---------- */
@media (max-width: 860px) {
  .sidebar { transform: translateX(-100%); }
  .sidebar.open { transform: none; }
  .main { margin-left: 0; }
  .menu-btn { display: inline-flex; }
  .topbar, .content { padding-left: 16px; padding-right: 16px; }
  .scrim.open { display: block; position: fixed; inset: 0; background: rgba(2, 4, 20, 0.6); z-index: 35; }
}
LAYOUTCSS_EOF

# ---------------------------------------------------------------- AppLayout
write_file "$APP/src/components/layout/AppLayout.jsx" <<'APPLAYOUT_EOF'
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

# ---------------------------------------------------------------- Stub
write_file "$APP/src/pages/Stub.jsx" <<'STUB_EOF'
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

echo "==> Running npm run build in $APP"
( cd "$APP" && npm run build )

echo "==> Done."
