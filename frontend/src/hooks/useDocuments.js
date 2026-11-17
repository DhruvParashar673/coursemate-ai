import { useCallback, useEffect, useState } from "react";
import { documentsApi } from "../services/documents";
import { getErrorMessage } from "../services/api";

const POLL_MS = 3000;

export default function useDocuments(courseId) {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // silent = background refresh: no loading flash, errors ignored.
  const load = useCallback(
    async (silent = false) => {
      if (!silent) {
        setLoading(true);
        setError("");
      }
      try {
        setDocuments(await documentsApi.list(courseId));
      } catch (err) {
        if (!silent) setError(getErrorMessage(err, "Failed to load documents."));
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [courseId]
  );

  useEffect(() => {
    load();
  }, [load]);

  // Keep refreshing while any document is still processing; stops on its own when none are.
  const hasProcessing = documents.some((d) => d.status === "processing");
  useEffect(() => {
    if (!hasProcessing) return undefined;
    const timer = setInterval(() => load(true), POLL_MS);
    return () => clearInterval(timer);
  }, [hasProcessing, load]);

  const remove = useCallback(
    async (documentId) => {
      await documentsApi.remove(courseId, documentId);
      await load(true);
    },
    [courseId, load]
  );

  return { documents, loading, error, reload: load, remove, hasProcessing };
}
