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
