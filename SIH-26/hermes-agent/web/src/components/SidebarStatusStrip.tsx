import { Link } from "react-router";
import type { StatusResponse } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useI18n } from "@/i18n";

/** Gateway + session summary for the System sidebar block. */
export function SidebarStatusStrip({ status }: SidebarStatusStripProps) {
  const { t } = useI18n();

  if (status === null) {
    return (
      <div className="mx-3 my-1.5 px-3 py-2 rounded-2xl neu-inset-sm" aria-hidden>
        <div className="h-2 w-[80%] max-w-full animate-pulse rounded-full bg-[rgb(163_177_198/0.5)]" />
      </div>
    );
  }

  const gw = gatewayLine(status, t);
  const { activeSessionsLabel, gatewayStatusLabel } = t.app;

  return (
    <Link
      to="/sessions"
      title={t.app.statusOverview}
      className={cn(
        "block mx-3 my-1.5 px-3 py-2 rounded-2xl",
        "neu-inset-sm neu-transition",
        "text-[#6B7280]",
        "hover:text-[#3D4852] hover:neu-inset",
        "focus-visible:outline-none focus-visible:ring-2",
        "focus-visible:ring-[#00E0C6] focus-visible:ring-offset-2 focus-visible:ring-offset-[#E0E5EC]",
      )}
    >
      <div className="flex flex-col gap-1 font-sans text-xs leading-snug tracking-[0.07em]">
        <p className="break-words">
          <span className="text-[#8B95A5]">{gatewayStatusLabel}</span>{" "}
          <span className={cn("font-semibold", toneToNeu[gw.tone] ?? "text-[#6B7280]")}>
            {gw.label}
          </span>
        </p>

        <p className="break-words">
          <span className="text-[#8B95A5]">{activeSessionsLabel}</span>{" "}
          <span className="tabular-nums font-medium text-[#3D4852]">
            {status.active_sessions}
          </span>
        </p>
      </div>
    </Link>
  );
}

/**
 * Maps semantic Nous DS tone class → neumorphic text colour.
 * Kept as a lookup so SidebarStatusStrip doesn't need to import Tailwind
 * classes that reference dark-mode variables (text-success etc.)
 */
const toneToNeu: Record<string, string> = {
  "text-success":         "text-[#00C49A]",  // accessible teal-green on #E0E5EC
  "text-warning":         "text-[#D97706]",  // amber
  "text-destructive":     "text-[#DC2626]",  // red
  "text-muted-foreground":"text-[#6B7280]",  // muted grey
};

export function gatewayLine(
  status: StatusResponse,
  t: ReturnType<typeof useI18n>["t"],
): { label: string; tone: string } {
  const g = t.app.gatewayStrip;
  const byState: Record<string, { label: string; tone: string }> = {
    running:        { label: g.running, tone: "text-success" },
    starting:       { label: g.starting, tone: "text-warning" },
    startup_failed: { label: g.failed,   tone: "text-destructive" },
    stopped:        { label: g.stopped,  tone: "text-muted-foreground" },
  };
  if (status.gateway_state && byState[status.gateway_state]) {
    return byState[status.gateway_state];
  }
  return status.gateway_running
    ? { label: g.running, tone: "text-success" }
    : { label: g.off,     tone: "text-muted-foreground" };
}

interface SidebarStatusStripProps {
  status: StatusResponse | null;
}
