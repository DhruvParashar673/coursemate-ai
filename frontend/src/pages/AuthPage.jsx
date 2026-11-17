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
