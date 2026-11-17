import api from "./api";

const enc = encodeURIComponent;

// Name of the multipart form field the backend expects for the uploaded file.
export const FILE_FIELD = "file";

const READY = ["ready", "completed", "complete", "processed", "done", "success", "indexed"];
const FAILED = ["failed", "failure", "error", "errored"];

export function normalizeStatus(raw) {
  const s = String(raw ?? "").toLowerCase();
  if (READY.includes(s)) return "ready";
  if (FAILED.includes(s)) return "failed";
  return "processing";
}

// Tolerates common field-name variants so the UI does not break on small schema differences.
export function normalizeDocument(d) {
  const message = d.error_message ?? d.error ?? d.status_message ?? null;
  return {
    id: d.id ?? d._id ?? d.document_id,
    name: d.filename ?? d.file_name ?? d.original_filename ?? d.name ?? d.title ?? "Untitled.pdf",
    status: normalizeStatus(d.status ?? d.processing_status),
    createdAt: d.created_at ?? d.uploaded_at ?? d.createdAt ?? null,
    message: typeof message === "string" ? message : null,
  };
}

function toList(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.documents)) return data.documents;
  if (Array.isArray(data?.items)) return data.items;
  return [];
}

export const documentsApi = {
  list: (courseId) =>
    api.get(`/courses/${enc(courseId)}/documents`).then((r) => toList(r.data).map(normalizeDocument)),

  get: (courseId, documentId) =>
    api.get(`/courses/${enc(courseId)}/documents/${enc(documentId)}`).then((r) => normalizeDocument(r.data)),

  upload: (courseId, file, onProgress) => {
    const body = new FormData();
    body.append(FILE_FIELD, file);
    return api
      .post(`/courses/${enc(courseId)}/documents`, body, {
        onUploadProgress: (e) => {
          if (onProgress && e.total) onProgress(Math.round((e.loaded * 100) / e.total));
        },
      })
      .then((r) => r.data);
  },

  remove: (courseId, documentId) =>
    api.delete(`/courses/${enc(courseId)}/documents/${enc(documentId)}`).then((r) => r.data),
};
