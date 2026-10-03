import { classifyLine } from "@/lib/log-classify";

const STRUCTURED_LINE = /^\s*(\d{4}-\d{2}-\d{2}[ T][\d:,.]+)\s+(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|FATAL)\s+(.*)$/;

export function AuditEvent({ line }: { line: string }) {
  const match = STRUCTURED_LINE.exec(line);
  const level = classifyLine(line);
  const message = match?.[3] || line;
  return <details className={`indra-audit-event indra-audit-event--${level}`}>
    <summary>
      <span className="indra-audit-event__time">{match?.[1] || "—"}</span>
      <span className="indra-audit-event__level">{match?.[2] || level}</span>
      <span className="indra-audit-event__message" translate="no">{message}</span>
    </summary>
    <pre>{line}</pre>
  </details>;
}
