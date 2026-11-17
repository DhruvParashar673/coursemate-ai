import { useCallback, useEffect, useState } from "react";
import { coursesApi } from "../services/courses";
import { getErrorMessage } from "../services/api";

export default function useCourse(courseId) {
  const [course, setCourse] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setCourse(await coursesApi.get(courseId));
    } catch (err) {
      setCourse(null);
      setError(getErrorMessage(err, "Failed to load course."));
    } finally {
      setLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    load();
  }, [load]);

  // Saves, then re-fetches so the page always shows what the server stored.
  const update = useCallback(
    async (data) => {
      await coursesApi.update(courseId, data);
      try {
        setCourse(await coursesApi.get(courseId));
      } catch {
        /* the save succeeded; keep showing the current data */
      }
    },
    [courseId]
  );

  return { course, loading, error, reload: load, update };
}
