#!/usr/bin/env bash
# apply-auth.sh — run from the project root (the folder that contains frontend/).
set -euo pipefail

FRONTEND="frontend"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$FRONTEND/.auth-backup-$STAMP"
FILES=("src/services/api.js" "src/pages/AuthPage.jsx" "src/App.jsx")

[ -d "$FRONTEND/src" ] || { echo "Error: $FRONTEND/src not found. Run this from the project root." >&2; exit 1; }
[ -f "$FRONTEND/package.json" ] || { echo "Error: $FRONTEND/package.json not found." >&2; exit 1; }

echo "==> Backing up existing files to $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"
for f in "${FILES[@]}"; do
  if [ -f "$FRONTEND/$f" ]; then
    mkdir -p "$BACKUP_DIR/$(dirname "$f")"
    cp -p "$FRONTEND/$f" "$BACKUP_DIR/$f"
    echo "    backed up $f"
  else
    echo "    $f does not exist yet (nothing to back up)"
  fi
done

mkdir -p "$FRONTEND/src/services" "$FRONTEND/src/pages"

echo "==> Writing $FRONTEND/src/services/api.js"
cat > "$FRONTEND/src/services/api.js" <<'API_JS_EOF'
import axios from "axios";

// Single Axios instance. Endpoint functions will be added per feature
// once the real backend routes/schemas are confirmed.
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const TOKEN_KEY = "token";

// Turns FastAPI errors (string detail, validation array, or network failure) into one message.
export function getErrorMessage(err, fallback = "Something went wrong. Please try again.") {
  if (!err?.response) return "Cannot reach the server. Check that the backend is running.";
  const detail = err.response.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d) => d.msg).filter(Boolean).join(". ");
  }
  return fallback;
}

export const authApi = {
  signup: (data) => api.post("/auth/signup", data).then((r) => r.data),
  login: (data) => api.post("/auth/login", data).then((r) => r.data),
  me: () => api.get("/auth/me").then((r) => r.data),
};

export default api;
API_JS_EOF

echo "==> Writing $FRONTEND/src/pages/AuthPage.jsx"
cat > "$FRONTEND/src/pages/AuthPage.jsx" <<'AUTH_JSX_EOF'
import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router";
import { Sparkles } from "lucide-react";
import Card from "../components/ui/Card";
import Input from "../components/ui/Input";
import Button from "../components/ui/Button";
import { authApi, getErrorMessage, TOKEN_KEY } from "../services/api";
import "../components/layout/layout.css";

export default function AuthPage({ mode = "login" }) {
  const isLogin = mode === "login";
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (localStorage.getItem(TOKEN_KEY)) return <Navigate to="/dashboard" replace />;

  const onChange = (e) => {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
    if (error) setError("");
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const email = form.email.trim();
      if (!isLogin) {
        await authApi.signup({ name: form.name.trim(), email, password: form.password });
      }
      // Signup is followed by an automatic login.
      const data = await authApi.login({ email, password: form.password });
      localStorage.setItem(TOKEN_KEY, data.access_token);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(getErrorMessage(err, isLogin ? "Login failed." : "Signup failed."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-wrap">
      <Card className="auth-card anim-fade-up">
        <div className="brand" style={{ justifyContent: "center" }}>
          <div className="brand-logo"><Sparkles size={18} color="#fff" /></div>
          CourseMate AI
        </div>
        <h2 style={{ textAlign: "center", marginBottom: 4 }}>{isLogin ? "Welcome back" : "Create your account"}</h2>
        <p style={{ textAlign: "center", color: "var(--text-muted)", fontSize: 14, marginBottom: 20 }}>
          {isLogin ? "Log in to continue learning" : "Start studying smarter from your own PDFs"}
        </p>
        <form style={{ display: "grid", gap: 14 }} onSubmit={onSubmit}>
          {!isLogin && (
            <Input label="Name" name="name" placeholder="Your name" value={form.name} onChange={onChange} required />
          )}
          <Input label="Email" name="email" type="email" placeholder="you@college.edu" value={form.email} onChange={onChange} required />
          <Input label="Password" name="password" type="password" placeholder="••••••••" value={form.password} onChange={onChange} required />
          {error && (
            <div className="badge badge-danger" role="alert" style={{ borderRadius: 10, padding: "10px 12px", fontWeight: 500, whiteSpace: "normal" }}>
              {error}
            </div>
          )}
          <Button block loading={loading}>{isLogin ? "Log in" : "Sign up"}</Button>
        </form>
        <p style={{ textAlign: "center", marginTop: 16, fontSize: 13, color: "var(--text-muted)" }}>
          {isLogin ? "New here? " : "Already have an account? "}
          <Link to={isLogin ? "/signup" : "/login"} style={{ color: "#a5b4fc", fontWeight: 600 }}>
            {isLogin ? "Sign up" : "Log in"}
          </Link>
        </p>
      </Card>
    </div>
  );
}
AUTH_JSX_EOF

echo "==> Writing $FRONTEND/src/App.jsx"
cat > "$FRONTEND/src/App.jsx" <<'APP_JSX_EOF'
import { BrowserRouter, Routes, Route, Navigate, Outlet, useLocation } from "react-router";
import AppLayout from "./components/layout/AppLayout";
import AuthPage from "./pages/AuthPage";
import Stub from "./pages/Stub";
import { TOKEN_KEY } from "./services/api";

function ProtectedRoute() {
  const location = useLocation();
  if (!localStorage.getItem(TOKEN_KEY)) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <Outlet />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/signup" element={<AuthPage mode="signup" />} />

        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route path="/dashboard" element={<Stub title="Dashboard" hint="Overview of courses and recent activity." />} />
            <Route path="/courses" element={<Stub title="Courses" hint="Create and manage your courses." />} />
            <Route path="/courses/:courseId" element={<Stub title="Course Details" hint="PDFs, processing status and learning tools." />} />
            <Route path="/chat" element={<Stub title="AI Chat" hint="Ask questions with source citations." />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
APP_JSX_EOF

echo "==> Running npm run build in $FRONTEND"
( cd "$FRONTEND" && npm run build )

echo "==> Done. Backups are in $BACKUP_DIR"
