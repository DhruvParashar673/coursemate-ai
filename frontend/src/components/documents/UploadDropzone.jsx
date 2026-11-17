import { useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import { getErrorMessage } from "../../services/api";
import "../../pages/courseDetail.css";

const isPdf = (f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");

// onUpload(file, onProgress) must return a promise and reject on failure.
export default function UploadDropzone({ onUpload }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [current, setCurrent] = useState(null); // { name, percent, index, total }
  const [errors, setErrors] = useState([]);
  const busy = current !== null;

  const handleFiles = async (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;

    const problems = [];
    const valid = [];
    files.forEach((f) => {
      if (isPdf(f)) valid.push(f);
      else problems.push(`${f.name}: only PDF files are allowed.`);
    });
    setErrors([...problems]);

    for (let i = 0; i < valid.length; i += 1) {
      const file = valid[i];
      setCurrent({ name: file.name, percent: 0, index: i + 1, total: valid.length });
      try {
        await onUpload(file, (percent) => setCurrent((c) => (c ? { ...c, percent } : c)));
      } catch (err) {
        problems.push(`${file.name}: ${getErrorMessage(err, "Upload failed.")}`);
        setErrors([...problems]);
      }
    }

    setCurrent(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  const openPicker = () => {
    if (!busy) inputRef.current?.click();
  };

  return (
    <div>
      <div
        className={`dropzone ${dragging ? "dragging" : ""} ${busy ? "busy" : ""}`}
        role="button"
        tabIndex={0}
        aria-disabled={busy}
        onClick={openPicker}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            openPicker();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!busy) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (!busy) handleFiles(e.dataTransfer.files);
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          hidden
          onChange={(e) => handleFiles(e.target.files)}
        />
        <div className="dropzone-icon"><UploadCloud size={24} /></div>
        {busy ? (
          <div className="upload-progress">
            <div className="upload-name">
              {current.name}
              {current.total > 1 && <span> · {current.index} of {current.total}</span>}
            </div>
            <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={current.percent}>
              <div className="progress-bar" style={{ width: `${current.percent}%` }} />
            </div>
            <div className="upload-sub">
              {current.percent < 100 ? `Uploading… ${current.percent}%` : "Finishing upload…"}
            </div>
          </div>
        ) : (
          <>
            <div className="dropzone-title">Drop PDFs here or click to browse</div>
            <div className="dropzone-sub">PDF files only</div>
          </>
        )}
      </div>

      {errors.length > 0 && (
        <div className="badge badge-danger upload-errors" role="alert">
          {errors.map((msg, i) => <div key={i}>{msg}</div>)}
        </div>
      )}
    </div>
  );
}
