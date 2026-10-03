import { useCallback, useEffect, useState } from "react";
import {
  FileCode,
  FileIcon,
  FileSpreadsheet,
  FileText,
  FolderOpen,
  Presentation,
  RefreshCw,
  Sparkles,
  FileImage,
} from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card } from "@nous-research/ui/ui/components/card";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { api, type ManagedFileEntry } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ArtifactsListCardProps {
  onSelectArtifact: (path: string) => void;
  className?: string;
}

function formatBytes(bytes: number | null): string {
  if (bytes === null) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getArtifactIcon(name: string) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (["md", "markdown", "txt"].includes(ext)) {
    return <FileText className="h-3.5 w-3.5 text-sky-400" />;
  }
  if (["py", "json", "yaml", "yml", "js", "ts", "html", "css", "sh"].includes(ext)) {
    return <FileCode className="h-3.5 w-3.5 text-emerald-400" />;
  }
  if (["csv", "tsv", "xlsx", "xls"].includes(ext)) {
    return <FileSpreadsheet className="h-3.5 w-3.5 text-amber-400" />;
  }
  if (["pdf"].includes(ext)) {
    return <FileText className="h-3.5 w-3.5 text-rose-400" />;
  }
  if (["pptx", "ppt"].includes(ext)) {
    return <Presentation className="h-3.5 w-3.5 text-orange-400" />;
  }
  if (["png", "jpg", "jpeg", "svg", "webp"].includes(ext)) {
    return <FileImage className="h-3.5 w-3.5 text-purple-400" />;
  }
  return <FileIcon className="h-3.5 w-3.5 text-slate-400" />;
}

export function ArtifactsListCard({ onSelectArtifact, className }: ArtifactsListCardProps) {
  const [artifacts, setArtifacts] = useState<ManagedFileEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchArtifacts = useCallback(async () => {
    try {
      // Check outputs folder first
      const res = await api.listFiles("outputs");
      const files: ManagedFileEntry[] = [];

      for (const entry of res.entries) {
        if (!entry.is_directory) {
          files.push(entry);
        } else {
          // One level subfolder scan e.g. outputs/test_docs
          try {
            const sub = await api.listFiles(entry.path);
            for (const subEntry of sub.entries) {
              if (!subEntry.is_directory) {
                files.push(subEntry);
              }
            }
          } catch {
            // best-effort
          }
        }
      }

      // Sort by modified time descending (newest first)
      files.sort((a, b) => {
        return (b.mtime || 0) - (a.mtime || 0);
      });

      setArtifacts(files);
    } catch {
      // outputs folder might be empty
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchArtifacts();
    // Poll every 8 seconds for newly created deliverables
    const timer = setInterval(() => {
      fetchArtifacts();
    }, 8000);
    return () => clearInterval(timer);
  }, [fetchArtifacts]);

  return (
    <Card className={cn("flex flex-col gap-2 p-3 text-xs border-border/80 bg-card/60", className)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 font-semibold text-text-primary tracking-wide">
          <Sparkles className="h-3.5 w-3.5 text-sky-400" />
          <span>Artifacts & Deliverables</span>
          {artifacts.length > 0 && (
            <Badge tone="secondary" className="px-1 py-0 text-[10px] font-mono">
              {artifacts.length}
            </Badge>
          )}
        </div>
        <Button
          ghost
          size="icon"
          onClick={() => {
            setLoading(true);
            fetchArtifacts();
          }}
          disabled={loading}
          title="Refresh generated files"
          aria-label="Refresh generated files"
          className="h-6 w-6 text-text-secondary hover:text-text-primary"
        >
          {loading ? <Spinner className="h-3 w-3" /> : <RefreshCw className="h-3 w-3" />}
        </Button>
      </div>

      {artifacts.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border/50 py-3 text-center text-text-tertiary">
          <FolderOpen className="mx-auto h-5 w-5 mb-1 opacity-40" />
          <span>No outputs generated yet</span>
        </div>
      ) : (
        <div className="flex flex-col gap-1 max-h-48 overflow-y-auto pr-0.5">
          {artifacts.map((a) => (
            <button
              key={a.path}
              type="button"
              onClick={() => onSelectArtifact(a.path)}
              className="flex items-center justify-between gap-2 rounded-md border border-transparent p-1.5 text-left transition-all hover:border-sky-500/40 hover:bg-sky-500/10 group"
            >
              <div className="flex min-w-0 items-center gap-2">
                <span className="shrink-0">{getArtifactIcon(a.name)}</span>
                <span className="truncate font-mono text-xs text-text-primary group-hover:text-sky-300">
                  {a.name}
                </span>
              </div>
              <span className="shrink-0 font-mono text-[10px] text-text-tertiary">
                {formatBytes(a.size)}
              </span>
            </button>
          ))}
        </div>
      )}
    </Card>
  );
}
