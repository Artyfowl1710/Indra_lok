import type { ReactNode } from "react";

interface IndraPanelProps {
  children: ReactNode;
  className?: string;
  title?: string;
  description?: string;
  action?: ReactNode;
}

export function IndraPanel({ children, className = "", title, description, action }: IndraPanelProps) {
  return <section className={`indra-panel ${className}`}>
    {(title || action) && <header className="indra-panel-header">
      <div>{title && <h2>{title}</h2>}{description && <p>{description}</p>}</div>
      {action}
    </header>}
    {children}
  </section>;
}

interface IndraStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
  tone?: "neutral" | "error";
}

export function IndraState({ title, description, action, tone = "neutral" }: IndraStateProps) {
  return <div className={`indra-state indra-state--${tone}`} role={tone === "error" ? "alert" : "status"}>
    <strong>{title}</strong>
    {description && <p>{description}</p>}
    {action}
  </div>;
}

interface IndraMetricProps {
  label: string;
  value: ReactNode;
  hint?: string;
}

export function IndraMetric({ label, value, hint }: IndraMetricProps) {
  return <div className="indra-metric"><span>{label}</span><strong>{value}</strong>{hint && <small>{hint}</small>}</div>;
}
