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
