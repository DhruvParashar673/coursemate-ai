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
