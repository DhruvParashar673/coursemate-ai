import { useState } from "react";
import Modal from "../ui/Modal";
import Input from "../ui/Input";
import Button from "../ui/Button";
import { getErrorMessage } from "../../services/api";
import "../../pages/pages.css";

// Render conditionally ({editing && <EditCourseModal />}) so the form re-initialises each time it opens.
export default function EditCourseModal({ course, onClose, onSave }) {
  const [form, setForm] = useState({
    title: course.title ?? "",
    subject: course.subject ?? "",
    description: course.description ?? "",
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const close = () => {
    if (!saving) onClose();
  };

  const onChange = (e) => {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
    if (error) setError("");
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      await onSave({
        title: form.title.trim(),
        subject: form.subject.trim(),
        description: form.description.trim(),
      });
      onClose();
    } catch (err) {
      setError(getErrorMessage(err, "Could not save changes."));
      setSaving(false);
    }
  };

  return (
    <Modal title="Edit course" onClose={close}>
      <form style={{ display: "grid", gap: 14 }} onSubmit={onSubmit}>
        <Input label="Title" name="title" value={form.title} onChange={onChange} required autoFocus />
        <Input label="Subject" name="subject" value={form.subject} onChange={onChange} required />
        <div className="field">
          <label htmlFor="description">Description</label>
          <textarea id="description" name="description" className="input" rows={4} value={form.description} onChange={onChange} />
        </div>
        {error && (
          <div className="badge badge-danger" role="alert" style={{ borderRadius: 10, padding: "10px 12px", fontWeight: 500, whiteSpace: "normal" }}>
            {error}
          </div>
        )}
        <div className="modal-actions">
          <Button type="button" variant="ghost" onClick={close} disabled={saving}>Cancel</Button>
          <Button type="submit" loading={saving}>Save changes</Button>
        </div>
      </form>
    </Modal>
  );
}
