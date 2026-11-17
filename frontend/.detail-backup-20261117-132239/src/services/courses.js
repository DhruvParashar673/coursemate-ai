import api from "./api";

export const coursesApi = {
  list: () => api.get("/courses").then((r) => r.data),
  create: ({ title, description, subject }) =>
    api.post("/courses", { title, description, subject }).then((r) => r.data),
};
