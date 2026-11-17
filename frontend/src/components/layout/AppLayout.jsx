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
