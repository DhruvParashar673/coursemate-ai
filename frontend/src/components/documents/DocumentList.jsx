import { AlertCircle, CheckCircle2, FileText, Loader2, Trash2 } from "lucide-react";
import Card from "../ui/Card";
import { formatDate } from "../../utils/format";
import "../../pages/courseDetail.css";

const STATUS = {
  processing: { label: "Processing", tone: "warning", Icon: Loader2, spin: true },
  ready: { label: "Ready", tone: "success", Icon: CheckCircle2 },
  failed: { label: "Failed", tone: "danger", Icon: AlertCircle },
};

export function DocumentStatus({ status }) {
  const { label, tone, Icon, spin } = STATUS[status] || STATUS.processing;
  return (
    <span className={`badge badge-${tone}`}>
      <Icon size={13} className={spin ? "spin" : undefined} /> {label}
    </span>
  );
}

export default function DocumentList({ documents, onDelete }) {
  return (
    <Card className="doc-list">
      {documents.map((doc) => (
        <div key={doc.id} className="doc-row">
          <div className="doc-icon"><FileText size={18} /></div>
          <div className="doc-info">
            <div className="doc-name" title={doc.name}>{doc.name}</div>
            <div className="doc-meta">
              {formatDate(doc.createdAt) && <span>Uploaded {formatDate(doc.createdAt)}</span>}
              {doc.status === "failed" && doc.message && <span className="doc-error">{doc.message}</span>}
            </div>
          </div>
          <DocumentStatus status={doc.status} />
          <button type="button" className="icon-btn" onClick={() => onDelete(doc)} aria-label={`Delete ${doc.name}`}>
            <Trash2 size={16} />
          </button>
        </div>
      ))}
    </Card>
  );
}
