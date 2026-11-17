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
