#!/usr/bin/env bash
# add-chat.sh — run from the project root.
# Works with ./frontend (frontend/src/...) or ./ (src/...).
# Existing files are backed up to <app>/.chat-backup-<timestamp>/ before being changed.
# No deletions are performed.
set -euo pipefail

if [ -d "frontend/src" ]; then
  APP="frontend"
elif [ -d "src" ] && [ -f "package.json" ]; then
  APP="."
else
  echo "Error: could not find frontend/src or ./src with package.json. Run from the project root." >&2
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$APP/.chat-backup-$STAMP"

for dep in "src/App.jsx" "src/services/api.js" "src/services/courses.js" "src/services/documents.js" \
           "src/hooks/useCourses.js" "src/hooks/useDocuments.js" \
           "src/components/ui/Button.jsx" "src/components/ui/Card.jsx" "src/components/ui/Badge.jsx" \
           "src/components/ui/ConfirmModal.jsx" "src/components/courses/CourseStates.jsx" \
           "src/pages/pages.css"; do
  [ -f "$APP/$dep" ] || { echo "Error: required existing file missing: $APP/$dep (run add-dashboard.sh and add-course-detail.sh first)" >&2; exit 1; }
done
echo "==> App directory: $APP"

backup() {
  local rel="${1#"$APP"/}"
  mkdir -p "$BACKUP_DIR/$(dirname "$rel")"
  cp -p "$1" "$BACKUP_DIR/$rel"
  echo "    backed up: $1"
}

write_file() {
  local f="$1"
  if [ -e "$f" ]; then backup "$f"; fi
  mkdir -p "$(dirname "$f")"
  cat > "$f"
  echo "    wrote: $f"
}

# ------------------------------------------------------------ services/chat.js
write_file "$APP/src/services/chat.js" <<'CHATAPI_EOF'
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
CHATAPI_EOF

# ------------------------------------------------------------ hooks/useChatHistory.js
write_file "$APP/src/hooks/useChatHistory.js" <<'HISTORY_EOF'
import { useEffect, useState } from "react";

const KEY = "coursemate_chat_";
const MAX_SAVED = 60;

function read(courseId) {
  try {
    const raw = localStorage.getItem(KEY + courseId);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

// Conversation history per course, kept in this browser only. Error bubbles are never saved.
// Use with key={courseId} on the parent so state resets when the course changes.
export default function useChatHistory(courseId) {
  const [messages, setMessages] = useState(() => read(courseId));

  useEffect(() => {
    try {
      const saved = messages.filter((m) => m.role !== "error").slice(-MAX_SAVED);
      localStorage.setItem(KEY + courseId, JSON.stringify(saved));
    } catch {
      /* storage unavailable: history just won't persist */
    }
  }, [messages, courseId]);

  return [messages, setMessages];
}
HISTORY_EOF

# ------------------------------------------------------------ components/chat/ChatMessage.jsx
write_file "$APP/src/components/chat/ChatMessage.jsx" <<'MESSAGE_EOF'
import { AlertCircle, FileText, RefreshCw, ShieldAlert, ShieldCheck, Sparkles } from "lucide-react";
import Button from "../ui/Button";
import "../../pages/chat.css";

export function TypingIndicator() {
  return (
    <div className="msg" aria-live="polite" aria-label="AI is thinking">
      <div className="ai-avatar"><Sparkles size={16} /></div>
      <div className="bubble bubble-ai typing"><span /><span /><span /></div>
    </div>
  );
}

export default function ChatMessage({ message, onRetry }) {
  if (message.role === "user") {
    return (
      <div className="msg msg-user">
        <div className="bubble bubble-user">{message.text}</div>
      </div>
    );
  }

  if (message.role === "error") {
    return (
      <div className="msg">
        <div className="ai-avatar ai-avatar-error"><AlertCircle size={16} /></div>
        <div className="bubble bubble-error" role="alert">
          <div>{message.text}</div>
          <Button size="sm" variant="secondary" icon={RefreshCw} onClick={() => onRetry(message)}>Retry</Button>
        </div>
      </div>
    );
  }

  const { text, grounded, provider, citations = [] } = message;
  return (
    <div className="msg">
      <div className="ai-avatar"><Sparkles size={16} /></div>
      <div className="bubble bubble-ai">
        {text ? (
          <div className="answer-text">{text}</div>
        ) : (
          <div className="answer-text answer-empty">The model returned an empty answer.</div>
        )}

        {(grounded !== null && grounded !== undefined) || provider ? (
          <div className="answer-meta">
            {grounded === true && (
              <span className="badge badge-success"><ShieldCheck size={13} /> Grounded in your PDFs</span>
            )}
            {grounded === false && (
              <span className="badge badge-warning"><ShieldAlert size={13} /> Not grounded in your PDFs</span>
            )}
            {provider && <span className="provider">via {provider}</span>}
          </div>
        ) : null}

        {grounded === false && (
          <div className="grounded-note">
            This answer isn't backed by your uploaded documents. Verify it before relying on it.
          </div>
        )}

        {citations.length > 0 && (
          <div className="citations">
            <div className="citations-title">Sources</div>
            <div className="citations-list">
              {citations.map((c, i) => (
                <span key={`${c.documentId}-${c.page}-${i}`} className="cite-chip" title={c.filename}>
                  <FileText size={13} />
                  <span className="cite-name">{c.filename}</span>
                  {c.page !== null && <span className="cite-page">p. {c.page}</span>}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
MESSAGE_EOF

# ------------------------------------------------------------ components/chat/ChatComposer.jsx
write_file "$APP/src/components/chat/ChatComposer.jsx" <<'COMPOSER_EOF'
import { useEffect, useRef } from "react";
import { Send } from "lucide-react";
import Button from "../ui/Button";
import "../../pages/chat.css";

export default function ChatComposer({ value, onChange, onSubmit, disabled }) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [value]);

  const submit = (e) => {
    e.preventDefault();
    if (!disabled && value.trim()) onSubmit(value);
  };

  return (
    <form className="composer" onSubmit={submit}>
      <textarea
        ref={ref}
        className="input composer-input"
        rows={1}
        placeholder="Ask a question about your PDFs…"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) submit(e);
        }}
        aria-label="Your question"
      />
      <Button type="submit" icon={Send} disabled={disabled || !value.trim()} aria-label="Send question">
        <span className="composer-label">Send</span>
      </Button>
    </form>
  );
}
COMPOSER_EOF

# ------------------------------------------------------------ components/chat/ChatPanel.jsx
write_file "$APP/src/components/chat/ChatPanel.jsx" <<'PANEL_EOF'
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { FileText, Info, MessageSquare, Trash2 } from "lucide-react";
import Card from "../ui/Card";
import Button from "../ui/Button";
import ConfirmModal from "../ui/ConfirmModal";
import ChatMessage, { TypingIndicator } from "./ChatMessage";
import ChatComposer from "./ChatComposer";
import useChatHistory from "../../hooks/useChatHistory";
import useDocuments from "../../hooks/useDocuments";
import { chatApi } from "../../services/chat";
import { getErrorMessage } from "../../services/api";
import "../../pages/chat.css";

const SUGGESTIONS = [
  "Summarize the main topics covered in my PDFs.",
  "What are the key definitions I should know?",
  "What are the most important concepts to revise?",
];

const uid = () => `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

// Render with key={course.id} so state resets per course.
export default function ChatPanel({ course, onBusyChange }) {
  const courseId = course.id;
  const docs = useDocuments(courseId);
  const [messages, setMessages] = useChatHistory(courseId);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [documentId, setDocumentId] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    onBusyChange?.(sending);
  }, [sending, onBusyChange]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  const readyDocs = docs.documents.filter((d) => d.status === "ready");
  const anyProcessing = docs.documents.some((d) => d.status === "processing");
  const showNotice = !docs.loading && !docs.error && readyDocs.length === 0;

  const send = async (question, retryOf = null) => {
    const text = question.trim();
    if (!text || sending) return;

    setMessages((m) => {
      const withoutErrors = m.filter((x) => x.role !== "error");
      return retryOf ? withoutErrors : [...withoutErrors, { id: uid(), role: "user", text, ts: Date.now() }];
    });
    if (!retryOf) setInput("");
    setSending(true);

    try {
      const res = await chatApi.ask(courseId, { question: text, documentId: documentId || null });
      setMessages((m) => [
        ...m,
        {
          id: uid(),
          role: "assistant",
          text: res.answer,
          grounded: res.grounded,
          provider: res.provider,
          citations: res.citations,
          ts: Date.now(),
        },
      ]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        { id: uid(), role: "error", text: getErrorMessage(err, "Could not get an answer."), question: text },
      ]);
    } finally {
      setSending(false);
    }
  };

  return (
    <Card className="chat-panel">
      <div className="chat-toolbar">
        <label className="chat-scope">
          <FileText size={15} />
          <select
            className="input chat-select"
            value={documentId}
            onChange={(e) => setDocumentId(e.target.value)}
            disabled={sending}
            aria-label="Limit answers to a document"
          >
            <option value="">All documents</option>
            {readyDocs.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        </label>
        <Button
          variant="ghost"
          size="sm"
          icon={Trash2}
          disabled={sending || messages.length === 0}
          onClick={() => setConfirmClear(true)}
        >
          Clear chat
        </Button>
      </div>

      {showNotice && (
        <div className="chat-notice">
          <Info size={15} />
          <span>
            {anyProcessing
              ? "Your PDFs are still processing. Answers will be based on them once they're ready."
              : "No PDFs are ready in this course yet."}{" "}
            <Link to={`/courses/${courseId}`}>Open course</Link>
          </span>
        </div>
      )}

      <div className="chat-messages">
        {messages.length === 0 && !sending ? (
          <div className="chat-empty">
            <div className="state-icon"><MessageSquare size={26} /></div>
            <h3>Ask about {course.title}</h3>
            <p>Answers come from the PDFs you uploaded to this course, with the source pages listed.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" className="suggestion" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((m) => (
              <ChatMessage key={m.id} message={m} onRetry={(msg) => send(msg.question, msg)} />
            ))}
            {sending && <TypingIndicator />}
          </>
        )}
        <div ref={endRef} />
      </div>

      <ChatComposer value={input} onChange={setInput} onSubmit={(q) => send(q)} disabled={sending} />

      {confirmClear && (
        <ConfirmModal
          title="Clear conversation"
          message="This removes the saved conversation for this course from this browser."
          confirmLabel="Clear"
          onConfirm={async () => setMessages([])}
          onClose={() => setConfirmClear(false)}
        />
      )}
    </Card>
  );
}
PANEL_EOF

# ------------------------------------------------------------ pages/Chat.jsx
write_file "$APP/src/pages/Chat.jsx" <<'CHATPAGE_EOF'
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { BookOpen } from "lucide-react";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import ChatPanel from "../components/chat/ChatPanel";
import { CourseGridSkeleton, ErrorState } from "../components/courses/CourseStates";
import useCourses from "../hooks/useCourses";
import "./pages.css";
import "./chat.css";

export default function Chat() {
  const { courses, loading, error, reload } = useCourses();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  if (loading) {
    return (
      <div className="page">
        <CourseGridSkeleton count={1} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <ErrorState message={error} onRetry={reload} />
      </div>
    );
  }

  if (courses.length === 0) {
    return (
      <div className="page">
        <Card className="state-card">
          <div className="state-icon"><BookOpen size={26} /></div>
          <h3>Create a course first</h3>
          <p>Chat works on the PDFs inside a course. Create one and upload your study material to get started.</p>
          <Button onClick={() => navigate("/courses")}>Go to courses</Button>
        </Card>
      </div>
    );
  }

  const requested = params.get("course");
  const selected = courses.find((c) => String(c.id) === requested) || courses[0];

  return (
    <div className="chat-page">
      <div className="chat-head">
        <div>
          <h2>AI Chat</h2>
          <p className="page-sub">Ask questions about the PDFs in a course.</p>
        </div>
        <select
          className="input chat-course-select"
          value={String(selected.id)}
          onChange={(e) => setParams({ course: e.target.value }, { replace: true })}
          disabled={busy}
          aria-label="Select course"
        >
          {courses.map((c) => (
            <option key={c.id} value={String(c.id)}>{c.title}</option>
          ))}
        </select>
      </div>

      <ChatPanel key={selected.id} course={selected} onBusyChange={setBusy} />
    </div>
  );
}
CHATPAGE_EOF

# ------------------------------------------------------------ pages/chat.css
write_file "$APP/src/pages/chat.css" <<'CHATCSS_EOF'
.chat-page { display: flex; flex-direction: column; height: calc(100vh - 140px); height: calc(100dvh - 140px); min-height: 460px; }
.chat-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
.chat-head h2 { font-size: 26px; }
.chat-course-select { width: auto; min-width: 220px; max-width: 100%; }
select.input { color-scheme: dark; cursor: pointer; }

.card.chat-panel { flex: 1; min-height: 0; display: flex; flex-direction: column; padding: 0; overflow: hidden; }

.chat-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--border); }
.chat-scope { display: flex; align-items: center; gap: 8px; color: var(--text-muted); min-width: 0; flex: 1; max-width: 340px; }
.chat-select { padding: 7px 12px; font-size: 13px; }

.chat-notice { display: flex; align-items: flex-start; gap: 8px; padding: 10px 16px; font-size: 13px; color: var(--warning); background: rgba(251, 191, 36, 0.08); border-bottom: 1px solid rgba(251, 191, 36, 0.2); }
.chat-notice svg { flex-shrink: 0; margin-top: 2px; }
.chat-notice a { color: #fff; font-weight: 600; text-decoration: underline; }

.chat-messages { flex: 1; min-height: 0; overflow-y: auto; padding: 20px 16px; display: flex; flex-direction: column; gap: 16px; }

.chat-empty { margin: auto; max-width: 460px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 20px 0; }
.chat-empty h3 { font-size: 18px; overflow-wrap: anywhere; }
.chat-empty p { color: var(--text-muted); font-size: 14px; }
.suggestions { display: flex; flex-direction: column; gap: 8px; width: 100%; margin-top: 8px; }
.suggestion {
  font-family: inherit; font-size: 13.5px; text-align: left; padding: 10px 14px; border-radius: var(--radius-sm);
  background: rgba(99, 102, 241, 0.1); border: 1px solid var(--border); color: var(--text); cursor: pointer; transition: all 0.2s ease;
}
.suggestion:hover { background: rgba(99, 102, 241, 0.2); border-color: rgba(139, 92, 246, 0.5); }

.msg { display: flex; align-items: flex-start; gap: 10px; animation: fadeUp 0.3s ease both; }
.msg-user { justify-content: flex-end; }
.ai-avatar { width: 32px; height: 32px; border-radius: 10px; flex-shrink: 0; display: grid; place-items: center; background: var(--grad); color: #fff; box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4); }
.ai-avatar-error { background: rgba(248, 113, 113, 0.16); color: var(--danger); box-shadow: none; }

.bubble { border-radius: 14px; padding: 11px 15px; font-size: 14.5px; line-height: 1.65; min-width: 0; overflow-wrap: anywhere; }
.bubble-user { max-width: min(78%, 560px); background: var(--grad); color: #fff; border-bottom-right-radius: 4px; white-space: pre-wrap; }
.bubble-ai { max-width: min(86%, 700px); background: rgba(99, 102, 241, 0.1); border: 1px solid var(--border); border-top-left-radius: 4px; }
.bubble-error { max-width: min(86%, 700px); display: flex; flex-direction: column; align-items: flex-start; gap: 10px; background: rgba(248, 113, 113, 0.1); border: 1px solid rgba(248, 113, 113, 0.3); color: var(--danger); border-top-left-radius: 4px; font-size: 14px; }

.answer-text { white-space: pre-wrap; }
.answer-empty { color: var(--text-muted); font-style: italic; }
.answer-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 10px; margin-top: 12px; }
.provider { font-size: 12px; color: var(--text-muted); }
.grounded-note { margin-top: 8px; font-size: 12.5px; color: var(--warning); line-height: 1.5; }

.citations { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border); }
.citations-title { font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px; }
.citations-list { display: flex; flex-wrap: wrap; gap: 8px; }
.cite-chip { display: inline-flex; align-items: center; gap: 6px; max-width: 100%; padding: 4px 10px; border-radius: 999px; font-size: 12px; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.28); color: var(--accent-blue); }
.cite-chip svg { flex-shrink: 0; }
.cite-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 220px; }
.cite-page { font-weight: 700; color: #fff; }

.typing { display: flex; align-items: center; gap: 5px; padding: 15px 16px; }
.typing span { width: 7px; height: 7px; border-radius: 50%; background: #a5b4fc; animation: bounce 1.2s ease-in-out infinite; }
.typing span:nth-child(2) { animation-delay: 0.15s; }
.typing span:nth-child(3) { animation-delay: 0.3s; }
@keyframes bounce { 0%, 60%, 100% { transform: translateY(0); opacity: 0.5; } 30% { transform: translateY(-5px); opacity: 1; } }

.composer { display: flex; align-items: flex-end; gap: 10px; padding: 12px 16px; border-top: 1px solid var(--border); background: rgba(10, 13, 31, 0.5); }
.composer-input { resize: none; min-height: 42px; max-height: 140px; line-height: 1.5; font-family: inherit; }
.composer .btn { height: 42px; flex-shrink: 0; }

@media (max-width: 640px) {
  .chat-page { height: calc(100vh - 120px); height: calc(100dvh - 120px); }
  .chat-head h2 { font-size: 22px; }
  .chat-course-select { width: 100%; }
  .bubble-user, .bubble-ai, .bubble-error { max-width: 92%; }
  .composer-label { display: none; }
  .cite-name { max-width: 150px; }
}
CHATCSS_EOF

# ------------------------------------------------------------ App.jsx (targeted patch)
echo "==> Wiring route in $APP/src/App.jsx"
backup "$APP/src/App.jsx"
node - "$APP/src/App.jsx" <<'PATCH_EOF'
const fs = require("fs");
const file = process.argv[2];
let s = fs.readFileSync(file, "utf8");

if (s.includes("./pages/Chat")) {
  console.log("    App.jsx already wired; no change.");
  process.exit(0);
}

const route = /<Route path="\/chat" element=\{<Stub[^>]*\/>\} \/>/;
const imp = 'import Stub from "./pages/Stub";';

if (!route.test(s) || !s.includes(imp)) {
  console.error("Error: expected Stub /chat route/import not found in App.jsx. App.jsx was NOT changed (backup kept).");
  process.exit(2);
}

s = s
  .replace(route, '<Route path="/chat" element={<Chat />} />')
  .replace(imp, imp + '\nimport Chat from "./pages/Chat";');

fs.writeFileSync(file, s);
console.log("    App.jsx updated.");
PATCH_EOF

echo "==> Verifying with npm run build in $APP"
( cd "$APP" && npm run build )

echo "==> Done. Backups (if any): $BACKUP_DIR"
echo "    To verify manually: cd $APP && npm run build && npm run dev"

