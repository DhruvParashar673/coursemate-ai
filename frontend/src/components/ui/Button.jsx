export default function Button({
  variant = "primary",
  size,
  block = false,
  loading = false,
  icon: Icon,
  children,
  className = "",
  ...props
}) {
  const cls = ["btn", `btn-${variant}`, size === "sm" && "btn-sm", block && "btn-block", className]
    .filter(Boolean)
    .join(" ");
  return (
    <button className={cls} disabled={loading || props.disabled} {...props}>
      {loading ? <span className="spinner" /> : Icon && <Icon size={16} />}
      {children}
    </button>
  );
}
