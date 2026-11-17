import api from "./api";

const enc = encodeURIComponent;

export const DEFAULT_TOP_K = 5;

// Only maps what the backend returned; nothing is invented.
export function normalizeAnswer(data) {
  const raw = Array.isArray(data?.citations) ? data.citations : [];
  const seen = new Set();
  const citations = [];
  raw.forEach((c) => {
    const item = {
      documentId: c?.document_id ?? null,
      filename: c?.filename || "Unknown document",
      page: Number.isFinite(c?.page_number) ? c.page_number : null,
    };
    const key = `${item.documentId}|${item.filename}|${item.page}`;
    if (!seen.has(key)) {
      seen.add(key);
      citations.push(item);
    }
  });

  return {
    answer: typeof data?.answer === "string" ? data.answer : "",
    provider: data?.provider ?? null,
    grounded: typeof data?.grounded === "boolean" ? data.grounded : null,
    citations,
  };
}

export const chatApi = {
  ask: (courseId, { question, documentId = null, topK = DEFAULT_TOP_K }) =>
    api
      .post(`/courses/${enc(courseId)}/ask`, {
        question,
        document_id: documentId,
        top_k: topK,
      })
      .then((r) => normalizeAnswer(r.data)),
};
