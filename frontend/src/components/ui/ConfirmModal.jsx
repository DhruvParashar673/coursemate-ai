import { useState } from "react";
import Modal from "./Modal";
import Button from "./Button";
import { getErrorMessage } from "../../services/api";

export default function ConfirmModal({ title, message, confirmLabel = "Delete", onConfirm, onClose }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const close = () => {
    if (!busy) onClose();
  };

  const run = async () => {
    setBusy(true);
    setError("");
    try {
      await onConfirm();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err, "Action failed. Please try again."));
      setBusy(false);
    }
  };

  return (
    <Modal title={title} onClose={close}>
      <p style={{ color: "var(--text-muted)", fontSize: 14, lineHeight: 1.6, marginBottom: 16 }}>{message}</p>
      {error && (
        <div className="badge badge-danger" role="alert" style={{ borderRadius: 10, padding: "10px 12px", fontWeight: 500, whiteSpace: "normal", marginBottom: 14 }}>
          {error}
        </div>
      )}
      <div className="modal-actions">
        <Button type="button" variant="ghost" onClick={close} disabled={busy}>Cancel</Button>
        <Button type="button" variant="danger" loading={busy} onClick={run}>{confirmLabel}</Button>
      </div>
    </Modal>
  );
}
