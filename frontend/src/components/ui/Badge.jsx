export default function Badge({ tone = "default", children }) {
  const cls = tone === "default" ? "badge" : `badge badge-${tone}`;
  return <span className={cls}>{children}</span>;
}
