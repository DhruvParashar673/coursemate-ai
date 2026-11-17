import api from "./api";

const enc = encodeURIComponent;

export const SUMMARY_LENGTHS = ["short", "medium", "detailed"];
export const MIN_QUESTIONS = 1;
export const MAX_QUESTIONS = 15;

// "Pages 3–7" / "Page 4". Accepts [a, b], {start_page, end_page} or a string; returns null if unknown.
export function formatPageRange(range) {
  if (range == null) return null;
  if (typeof range === "string") {
    const s = range.trim();
    if (!s) return null;
    return /^\d/.test(s) ? `Pages ${s}` : s;
  }
  let a;
  let b;
  if (Array.isArray(range)) [a, b] = range;
  else if (typeof range === "object") {
    a = range.start_page ?? range.start ?? range.from;
    b = range.end_page ?? range.end ?? range.to;
  }
  if (a == null && b == null) return null;
  if (a == null || b == null || a === b) return `Page ${a ?? b}`;
  return `Pages ${a}–${b}`;
}

export function normalizeCitation(c) {
  if (!c || typeof c !== "object") return null;
  const page = Number.isFinite(c.page_number) ? c.page_number : Number.isFinite(c.page) ? c.page : null;
  return { documentId: c.document_id ?? null, filename: c.filename || "Document", page };
}

function uniqueCitations(list) {
  const seen = new Set();
  const out = [];
  (Array.isArray(list) ? list : []).forEach((raw) => {
    const c = normalizeCitation(raw);
    if (!c) return;
    const key = `${c.documentId}|${c.filename}|${c.page}`;
    if (!seen.has(key)) {
      seen.add(key);
      out.push(c);
    }
  });
  return out;
}

function toTextList(list) {
  if (!Array.isArray(list)) return [];
  return list
    .map((item) => (typeof item === "string" ? item : item?.text ?? item?.point ?? item?.content ?? ""))
    .map((s) => String(s).trim())
    .filter(Boolean);
}

const common = (d) => ({
  pageRange: formatPageRange(d?.page_range),
  partial: d?.partial === true,
  provider: d?.provider ?? null,
  grounded: typeof d?.grounded === "boolean" ? d.grounded : null,
  message: typeof d?.message === "string" && d.message.trim() ? d.message.trim() : null,
});

// Only maps what the backend returned; nothing is invented.
export function normalizeSummary(d) {
  return {
    ...common(d),
    summary: typeof d?.summary === "string" ? d.summary : "",
    keyPoints: toTextList(d?.key_points),
    citations: uniqueCitations(d?.citations),
  };
}

export function normalizeQuestions(d) {
  const raw = Array.isArray(d?.questions) ? d.questions : [];
  return {
    ...common(d),
    questions: raw
      .map((q) => ({
        question: typeof q?.question === "string" ? q.question.trim() : "",
        type: typeof q?.type === "string" && q.type ? q.type : null,
        why: typeof q?.why_important === "string" && q.why_important.trim() ? q.why_important.trim() : null,
        citation: normalizeCitation(q?.citation),
      }))
      .filter((q) => q.question),
  };
}

export const learningApi = {
  summarize: (courseId, { documentId, startPage = null, endPage = null, length = "medium" }) =>
    api
      .post(`/courses/${enc(courseId)}/summaries`, {
        document_id: documentId,
        start_page: startPage,
        end_page: endPage,
        length,
      })
      .then((r) => normalizeSummary(r.data)),

  importantQuestions: (courseId, { documentId, startPage = null, endPage = null, count = 10 }) =>
    api
      .post(`/courses/${enc(courseId)}/important-questions`, {
        document_id: documentId,
        start_page: startPage,
        end_page: endPage,
        count,
      })
      .then((r) => normalizeQuestions(r.data)),
};
