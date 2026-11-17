export default function Card({ hover = false, className = "", children, ...props }) {
  return (
    <div className={`card ${hover ? "card-hover" : ""} ${className}`} {...props}>
      {children}
    </div>
  );
}
