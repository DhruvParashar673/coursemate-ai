import { useState } from "react";
import Modal from "../ui/Modal";
import Input from "../ui/Input";
import Button from "../ui/Button";
import { coursesApi } from "../../services/courses";
import { getErrorMessage } from "../../services/api";
import "../../pages/pages.css";

// Render conditionally ({show && <CreateCourseModal />}) so the form resets each time it opens.
export default function CreateCourseModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ title: "", subject: "", description: "" });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const close = () => {
    if (!submitting) onClose();
  };

  const onChange = (e) => {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
    if (error) setError("");
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await coursesApi.create({
        title: form.title.trim(),
        subject: form.subject.trim(),
        description: form.description.trim(),
      });
      await onCreated();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err, "Could not create the course."));
      setSubmitting(false);
    }
  };

  return (
    <Modal title="Create course" onClose={close}>
      <form style={{ display: "grid", gap: 14 }} onSubmit={onSubmit}>
        <Input label="Title" name="title" placeholder="e.g. Operating Systems" value={form.title} onChange={onChange} required autoFocus />
        <Input label="Subject" name="subject" placeholder="e.g. Computer Science" value={form.subject} onChange={onChange} required />
        <div className="field">
          <label htmlFor="description">Description</label>
          <textarea
            id="description"
            name="description"
            className="input"
            rows={4}
            placeholder="What is this course about?"
            value={form.description}
            onChange={onChange}
          />
        </div>
        {error && (
          <div className="badge badge-danger" role="alert" style={{ borderRadius: 10, padding: "10px 12px", fontWeight: 500, whiteSpace: "normal" }}>
            {error}
          </div>
        )}
        <div className="modal-actions">
          <Button type="button" variant="ghost" onClick={close} disabled={submitting}>Cancel</Button>
          <Button type="submit" loading={submitting}>Create course</Button>
        </div>
      </form>
    </Modal>
  );
}
