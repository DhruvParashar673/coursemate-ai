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
