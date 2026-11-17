export default function Input({ label, error, id, className = "", ...props }) {
  const inputId = id || props.name;
  return (
    <div className="field">
      {label && <label htmlFor={inputId}>{label}</label>}
      <input id={inputId} className={`input ${className}`} {...props} />
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}
