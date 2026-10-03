import type { StatusResponse } from "@/lib/api";
import { cn } from "@/lib/utils";
import { BRAND } from "@/config/brand";

export function SidebarFooter({ status }: SidebarFooterProps) {
  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-between gap-2",
        "px-5 py-2.5",
        // Neumorphic separator: a subtle inset strip instead of a hard border
      )}
    >
      {/* Thin inset divider — replaces border-t */}
      <div
        aria-hidden
        className="absolute left-4 right-4 h-px"
        style={{
          background: "rgb(163 177 198 / 0.45)",
          top: 0,
        }}
      />

      {/* Version badge — inset pill */}
      <span
        className={cn(
          "inline-flex items-center",
          "px-2.5 py-0.5 rounded-full",
          "font-mono-ui text-xs tabular-nums tracking-[0.06em] text-[#6B7280]",
          "neu-inset-xs",
        )}
      >
        {status?.version != null ? `v${status.version}` : "—"}
      </span>

      {/* Product owner — plain text until an official public URL is configured. */}
      <span
        className={cn(
          "font-sans text-xs font-medium tracking-[0.1em] text-[#CC2600]",
        )}
      >
        {BRAND.organisation}
      </span>
    </div>
  );
}

interface SidebarFooterProps {
  status: StatusResponse | null;
}
