import api from "./api";

const enc = encodeURIComponent;

export const coursesApi = {
  list: () => api.get("/courses").then((r) => r.data),
  create: ({ title, description, subject }) =>
    api.post("/courses", { title, description, subject }).then((r) => r.data),
  get: (courseId) => api.get(`/courses/${enc(courseId)}`).then((r) => r.data),
  update: (courseId, { title, description, subject }) =>
    api.put(`/courses/${enc(courseId)}`, { title, description, subject }).then((r) => r.data),
};
