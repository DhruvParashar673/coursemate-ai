import { BrowserRouter, Routes, Route, Navigate, Outlet, useLocation } from "react-router";
import AppLayout from "./components/layout/AppLayout";
import AuthPage from "./pages/AuthPage";
import Stub from "./pages/Stub";
import CourseDetail from "./pages/CourseDetail";
import Dashboard from "./pages/Dashboard";
import Courses from "./pages/Courses";
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
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/courses" element={<Courses />} />
            <Route path="/courses/:courseId" element={<CourseDetail />} />
            <Route path="/chat" element={<Stub title="AI Chat" hint="Ask questions with source citations." />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
