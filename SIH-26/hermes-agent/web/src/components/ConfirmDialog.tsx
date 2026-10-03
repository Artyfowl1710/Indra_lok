import { Button } from "@nous-research/ui/ui/components/button";
import { AlertTriangle } from "lucide-react";
import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { cn, themedBody } from "@/lib/utils";

interface ConfirmDialogProps {
  cancelLabel?: string;
  confirmLabel?: string;
  description?: string;
  destructive?: boolean;
  loading?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  open: boolean;
  title: string;
}

export function ConfirmDialog({
  cancelLabel = "Cancel",
  confirmLabel = "Confirm",
  description,
  destructive = false,
  loading = false,
  onCancel,
  onConfirm,
  open,
  title,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const prevActive = document.activeElement as HTMLElement | null;
    dialogRef.current
      ?.querySelector<HTMLButtonElement>("[data-confirm]")
      ?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCancel();
      }
    };

    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      prevActive?.focus?.();
    };
  }, [open, onCancel]);

  if (!open) return null;

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      aria-describedby={description ? "confirm-dialog-desc" : undefined}
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
      className="indra-confirm-dialog fixed inset-0 z-[200] flex items-center justify-center bg-[#E0E5EC]/80 backdrop-blur-sm p-4"
    >
      <div
        ref={dialogRef}
        className={cn(
          themedBody,
          "relative w-full max-w-md rounded-[32px] bg-[#E0E5EC] neu-raised p-2",
        )}
      >
        <div className="flex items-start gap-3 p-4 border-b border-[rgb(163_177_198/0.3)]">
          {destructive && (
            <div aria-hidden className="mt-0.5 shrink-0 text-red-500">
              <AlertTriangle className="h-4 w-4" />
            </div>
          )}

          <div className="flex-1 min-w-0 flex flex-col gap-1">
            <h2
              id="confirm-dialog-title"
              className="font-display font-bold text-base text-[#3D4852] tracking-wide"
              style={{ fontFamily: "var(--theme-font-display)" }}
            >
              {title}
            </h2>

            {description && (
              <p
                id="confirm-dialog-desc"
                className="text-xs text-[#627D98] leading-relaxed whitespace-pre-line"
              >
                {description}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 p-4">
          <Button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="neu-raised neu-raised-hover rounded-2xl px-5 py-2 text-xs font-semibold text-[#3D4852] neu-transition"
          >
            {cancelLabel}
          </Button>
          <Button
            data-confirm
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className={cn(
              "rounded-2xl px-5 py-2 text-xs font-semibold neu-transition",
              destructive
                ? "bg-red-500 text-white shadow-[3px_3px_6px_rgba(220,38,38,0.3)] hover:bg-red-600"
                : "neu-accent-raised neu-accent-pressed text-[#05091A]",
            )}
          >
            {loading ? "…" : confirmLabel}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
