import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  Download,
  Edit3,
  ExternalLink,
  Eye,
  FileCode,
  FileIcon,
  FileImage,
  FileSpreadsheet,
  FileText,
  Maximize2,
  Minimize2,
  Presentation,
  Save,
  Sparkles,
  X,
} from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { useToast } from "@nous-research/ui/hooks/use-toast";
import { Markdown } from "@/components/Markdown";
import { api, type ManagedFileReadResponse } from "@/lib/api";
import { copyTextToClipboard } from "@/lib/clipboard";
import { cn } from "@/lib/utils";

interface ArtifactViewerModalProps {
  filePath: string | null;
  onClose: () => void;
  onSaved?: (path: string) => void;
}

interface PptxSlide {
  index: number;
  title: string;
  texts: string[];
  tables: string[][][];
}

interface PptxDeck {
  ok: boolean;
  name: string;
  slide_count: number;
  width_inches: number;
  height_inches: number;
  aspect_ratio: string;
  slides: PptxSlide[];
  error?: string;
}

function decodeDataUrl(dataUrl: string): string {
  const comma = dataUrl.indexOf(",");
  if (comma === -1) return "";
  const base64 = dataUrl.slice(comma + 1);
  try {
    const binary = atob(base64);
    const bytes = Uint8Array.from(binary, (m) => m.charCodeAt(0));
    return new TextDecoder("utf-8").decode(bytes);
  } catch {
    return atob(base64);
  }
}

function dataUrlToBlob(dataUrl: string): Blob | null {
  try {
    const comma = dataUrl.indexOf(",");
    if (comma === -1) return null;
    const mimeMatch = dataUrl.slice(0, comma).match(/:(.*?);/);
    const mime = mimeMatch ? mimeMatch[1] : "application/pdf";
    const base64 = dataUrl.slice(comma + 1);
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return new Blob([bytes], { type: mime });
  } catch {
    return null;
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileCategory(path: string): {
  type: "markdown" | "code" | "csv" | "pdf" | "pptx" | "image" | "binary";
  label: string;
  isEditable: boolean;
  color: string;
} {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  if (["md", "markdown"].includes(ext)) {
    return { type: "markdown", label: "MARKDOWN", isEditable: true, color: "text-sky-700 bg-sky-50 border-sky-200" };
  }
  if (["py", "js", "ts", "jsx", "tsx", "json", "yaml", "yml", "html", "css", "sh", "sql", "txt"].includes(ext)) {
    return { type: "code", label: ext.toUpperCase(), isEditable: true, color: "text-emerald-700 bg-emerald-50 border-emerald-200" };
  }
  if (["csv", "tsv"].includes(ext)) {
    return { type: "csv", label: "CSV TABLE", isEditable: true, color: "text-amber-700 bg-amber-50 border-amber-200" };
  }
  if (ext === "pdf") {
    return { type: "pdf", label: "PDF DOCUMENT", isEditable: false, color: "text-rose-700 bg-rose-50 border-rose-200" };
  }
  if (["pptx", "ppt"].includes(ext)) {
    return { type: "pptx", label: "POWERPOINT DECK", isEditable: false, color: "text-orange-700 bg-orange-50 border-orange-200" };
  }
  if (["png", "jpg", "jpeg", "svg", "webp", "gif"].includes(ext)) {
    return { type: "image", label: ext.toUpperCase(), isEditable: false, color: "text-purple-700 bg-purple-50 border-purple-200" };
  }
  return { type: "binary", label: ext.toUpperCase() || "FILE", isEditable: false, color: "text-slate-700 bg-slate-100 border-slate-200" };
}

export function ArtifactViewerModal({ filePath, onClose, onSaved }: ArtifactViewerModalProps) {
  const { showToast } = useToast();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [fileData, setFileData] = useState<ManagedFileReadResponse | null>(null);
  const [content, setContent] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [mode, setMode] = useState<"preview" | "edit">("preview");
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [pptxDeck, setPptxDeck] = useState<PptxDeck | null>(null);
  const [activeSlideIdx, setActiveSlideIdx] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const category = useMemo(() => (filePath ? getFileCategory(filePath) : null), [filePath]);
  const isDirty = content !== savedContent;

  const loadFile = useCallback(async () => {
    if (!filePath) return;
    setLoading(true);
    try {
      const data = await api.readFile(filePath);
      setFileData(data);

      if (category?.isEditable) {
        const text = decodeDataUrl(data.data_url);
        setContent(text);
        setSavedContent(text);
      } else if (category?.type === "pdf") {
        const blob = dataUrlToBlob(data.data_url);
        if (blob) {
          const url = URL.createObjectURL(blob);
          setPdfBlobUrl(url);
        }
      } else if (category?.type === "pptx") {
        try {
          const deck = await api.getPptxOutline(filePath);
          if (deck && deck.ok) {
            setPptxDeck(deck);
            setActiveSlideIdx(0);
          }
        } catch {
          // best effort
        }
      }
    } catch (err) {
      showToast(`Failed to open file: ${err}`, "error");
    } finally {
      setLoading(false);
    }
  }, [filePath, category, showToast]);

  useEffect(() => {
    if (filePath) {
      loadFile();
      setMode("preview");
    } else {
      setFileData(null);
      setContent("");
      setSavedContent("");
      setPptxDeck(null);
      if (pdfBlobUrl) {
        URL.revokeObjectURL(pdfBlobUrl);
        setPdfBlobUrl(null);
      }
    }
    return () => {
      if (pdfBlobUrl) {
        URL.revokeObjectURL(pdfBlobUrl);
      }
    };
  }, [filePath]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keyboard shortcuts: Escape closes, Ctrl+S saves, Arrow keys navigate slides in PPTX
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!filePath) return;
      if (e.key === "Escape") {
        onClose();
      } else if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        if (category?.isEditable && isDirty) {
          handleSave();
        }
      } else if (category?.type === "pptx" && pptxDeck && pptxDeck.slides.length > 0) {
        if (e.key === "ArrowLeft") {
          setActiveSlideIdx((curr) => Math.max(0, curr - 1));
        } else if (e.key === "ArrowRight") {
          setActiveSlideIdx((curr) => Math.min(pptxDeck.slides.length - 1, curr + 1));
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  const handleSave = async () => {
    if (!filePath || !category?.isEditable) return;
    setSaving(true);
    try {
      await api.saveFileText(filePath, content);
      setSavedContent(content);
      showToast("File saved to disk ✓", "success");
      onSaved?.(filePath);
    } catch (err) {
      showToast(`Failed to save: ${err}`, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleCopy = async () => {
    if (!content) return;
    await copyTextToClipboard(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    showToast("Content copied to clipboard ✓", "success");
  };

  const handleDownload = () => {
    if (!filePath) return;
    const name = filePath.split(/[/\\]/).pop() || "download";
    if (fileData?.data_url) {
      const link = document.createElement("a");
      link.href = fileData.data_url;
      link.download = name;
      document.body.appendChild(link);
      link.click();
      link.remove();
      return;
    }
    const token = typeof window !== "undefined" ? window.__HERMES_SESSION_TOKEN__ : undefined;
    const a = document.createElement("a");
    a.href = `/api/files/download?path=${encodeURIComponent(filePath)}${token ? `&token=${encodeURIComponent(token)}` : ""}`;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  if (!filePath) return null;

  const fileName = filePath.split(/[/\\]/).pop() || filePath;
  const fileSize = fileData ? formatBytes(fileData.size) : "—";
  const directViewUrl = api.getFileViewUrl(filePath);

  return createPortal(
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 backdrop-blur-sm p-2 sm:p-4 animate-in fade-in duration-150"
      onClick={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
    >
      <div
        className={cn(
          "relative flex flex-col border border-border bg-background text-foreground shadow-2xl transition-all duration-200 overflow-hidden",
          expanded
            ? "h-[98dvh] w-[99vw] rounded-lg"
            : "h-[min(92dvh,880px)] w-full max-w-5xl rounded-2xl",
        )}
      >
        {/* Top Header Bar */}
        <header className="flex min-h-14 items-center justify-between gap-3 border-b border-border bg-card px-4 py-2.5">
          {/* Left: Icon, Filename, Path & Badges */}
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-background shadow-xs">
              {category?.type === "markdown" && <FileText className="h-5 w-5 text-sky-600" />}
              {category?.type === "code" && <FileCode className="h-5 w-5 text-emerald-600" />}
              {category?.type === "csv" && <FileSpreadsheet className="h-5 w-5 text-amber-600" />}
              {category?.type === "pdf" && <FileText className="h-5 w-5 text-rose-600" />}
              {category?.type === "pptx" && <Presentation className="h-5 w-5 text-orange-600" />}
              {category?.type === "image" && <FileImage className="h-5 w-5 text-purple-600" />}
              {category?.type === "binary" && <FileIcon className="h-5 w-5 text-muted-foreground" />}
            </div>

            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="truncate font-mono text-sm font-semibold text-foreground tracking-wide">
                  {fileName}
                </span>
                {category && (
                  <span className={cn("text-[10px] font-bold tracking-wider px-1.5 py-0.5 rounded border", category.color)}>
                    {category.label}
                  </span>
                )}
                {isDirty && (
                  <span className="inline-flex items-center gap-1 rounded bg-amber-50 border border-amber-300 px-1.5 py-0.5 text-[10px] font-semibold text-amber-900">
                    Unsaved Changes
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="truncate max-w-[280px] font-mono text-[11px] opacity-80">{filePath}</span>
                <span>•</span>
                <span>{fileSize}</span>
              </div>
            </div>
          </div>

          {/* Right Toolbar Actions */}
          <div className="flex items-center gap-1.5 shrink-0">
            {/* Mode Switcher for Editable Files */}
            {category?.isEditable && (
              <div className="flex items-center rounded-lg border border-border bg-muted/60 p-0.5">
                <button
                  type="button"
                  onClick={() => setMode("preview")}
                  className={cn(
                    "flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md transition-colors",
                    mode === "preview"
                      ? "bg-background text-foreground shadow-xs font-semibold"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <Eye className="h-3.5 w-3.5" />
                  Preview
                </button>
                <button
                  type="button"
                  onClick={() => setMode("edit")}
                  className={cn(
                    "flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md transition-colors",
                    mode === "edit"
                      ? "bg-background text-foreground shadow-xs font-semibold"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <Edit3 className="h-3.5 w-3.5" />
                  Edit
                </button>
              </div>
            )}

            {/* Save Button for Editable Files */}
            {category?.isEditable && (
              <Button
                size="sm"
                onClick={handleSave}
                disabled={saving || !isDirty}
                className={cn(
                  "gap-1.5 transition-all text-xs font-semibold",
                  isDirty
                    ? "bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm"
                    : "opacity-60",
                )}
                title="Save changes to disk (Ctrl+S)"
              >
                {saving ? <Spinner className="h-3.5 w-3.5" /> : <Save className="h-3.5 w-3.5" />}
                <span>{saving ? "Saving..." : isDirty ? "Save Changes" : "Saved"}</span>
              </Button>
            )}

            {/* Copy Button */}
            {category?.isEditable && (
              <Button
                ghost
                size="icon"
                onClick={handleCopy}
                title="Copy content"
                aria-label="Copy content"
                className="h-8 w-8 text-muted-foreground hover:text-foreground"
              >
                {copied ? <Check className="h-4 w-4 text-emerald-600" /> : <Copy className="h-4 w-4" />}
              </Button>
            )}

            {/* Open in New Tab for PDF/Images */}
            {(category?.type === "pdf" || category?.type === "image") && (
              <a
                href={directViewUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground transition-colors"
                title="Open in new browser tab"
              >
                <ExternalLink className="h-4 w-4" />
              </a>
            )}

            {/* Download Button */}
            <Button
              ghost
              size="icon"
              onClick={handleDownload}
              title="Download file to device"
              aria-label="Download file"
              className="h-8 w-8 text-muted-foreground hover:text-foreground"
            >
              <Download className="h-4 w-4" />
            </Button>

            {/* Maximize Toggle */}
            <Button
              ghost
              size="icon"
              onClick={() => setExpanded((v) => !v)}
              title={expanded ? "Restore view" : "Maximize view"}
              aria-label="Toggle full size"
              className="h-8 w-8 text-muted-foreground hover:text-foreground"
            >
              {expanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </Button>

            {/* Close Button */}
            <Button
              ghost
              size="icon"
              onClick={onClose}
              title="Close viewer (Esc)"
              aria-label="Close viewer"
              className="h-8 w-8 text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </header>

        {/* Content Body Area */}
        <div className="relative flex-1 min-h-0 overflow-hidden bg-muted/40">
          {loading ? (
            <div className="flex h-full items-center justify-center gap-3 text-muted-foreground">
              <Spinner className="h-6 w-6 text-foreground" />
              <span className="text-sm font-medium">Loading artifact...</span>
            </div>
          ) : (
            <>
              {/* Markdown View */}
              {category?.type === "markdown" && (
                <div className="h-full w-full overflow-hidden">
                  {mode === "preview" ? (
                    <div className="h-full overflow-y-auto px-6 py-6 sm:px-10">
                      <div className="mx-auto max-w-4xl rounded-xl border border-border bg-card p-6 sm:p-8 shadow-xs text-foreground">
                        <div className="text-foreground leading-relaxed [&_*]:text-foreground [&_h1]:font-black [&_h2]:font-bold [&_h3]:font-semibold [&_h4]:font-semibold [&_strong]:font-bold [&_strong]:text-foreground [&_p]:text-foreground [&_li]:text-foreground [&_code]:text-foreground [&_code]:bg-muted/70 [&_code]:border [&_code]:border-border/60 [&_hr]:border-border">
                          <Markdown content={content} />
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="h-full w-full p-3">
                      <textarea
                        ref={textareaRef}
                        value={content}
                        onChange={(e) => setContent(e.target.value)}
                        placeholder="Write markdown or document content..."
                        spellCheck={false}
                        className="h-full w-full resize-none rounded-xl border border-border bg-card p-4 font-mono text-sm leading-relaxed text-black placeholder-muted-foreground outline-none focus:border-foreground focus:ring-1 focus:ring-foreground shadow-xs selection:bg-slate-200"
                      />
                    </div>
                  )}
                </div>
              )}

              {/* Code & Text View */}
              {category?.type === "code" && (
                <div className="h-full w-full overflow-hidden p-3">
                  {mode === "preview" ? (
                    <div className="h-full overflow-y-auto rounded-xl border border-border bg-card p-4 shadow-xs">
                      <pre className="font-mono text-xs leading-relaxed text-foreground">
                        <code>{content}</code>
                      </pre>
                    </div>
                  ) : (
                    <textarea
                      ref={textareaRef}
                      value={content}
                      onChange={(e) => setContent(e.target.value)}
                      placeholder="Edit code or data..."
                      spellCheck={false}
                      className="h-full w-full resize-none rounded-xl border border-border bg-card p-4 font-mono text-xs leading-relaxed text-black placeholder-muted-foreground outline-none focus:border-foreground focus:ring-1 focus:ring-foreground shadow-xs selection:bg-slate-200"
                    />
                  )}
                </div>
              )}

              {/* CSV View */}
              {category?.type === "csv" && (
                <div className="h-full w-full overflow-hidden p-3">
                  {mode === "preview" ? (
                    <CsvTablePreview rawCsv={content} />
                  ) : (
                    <textarea
                      value={content}
                      onChange={(e) => setContent(e.target.value)}
                      className="h-full w-full resize-none rounded-xl border border-border bg-card p-4 font-mono text-xs text-black placeholder-muted-foreground outline-none focus:border-foreground shadow-xs selection:bg-slate-200"
                    />
                  )}
                </div>
              )}

              {/* PDF Viewer */}
              {category?.type === "pdf" && (
                <div className="h-full w-full flex flex-col p-2">
                  <div className="relative flex-1 min-h-0 bg-muted/60 rounded-xl overflow-hidden border border-border shadow-xs">
                    <iframe
                      src={pdfBlobUrl || directViewUrl}
                      className="h-full w-full bg-white"
                      title={fileName}
                    />
                  </div>
                </div>
              )}

              {/* PowerPoint Interactive Viewer Card */}
              {category?.type === "pptx" && (
                <div className="h-full w-full flex flex-col p-3 overflow-hidden">
                  {pptxDeck && pptxDeck.slides && pptxDeck.slides.length > 0 ? (
                    <div className="flex h-full w-full flex-col gap-3 min-h-0">
                      {/* Deck Header Bar with Controls */}
                      <div className="flex items-center justify-between rounded-xl border border-border bg-card px-4 py-2 text-xs shadow-xs">
                        <div className="flex items-center gap-3">
                          <div className="flex items-center gap-1.5 text-orange-600 font-semibold">
                            <Sparkles className="h-4 w-4" />
                            <span>Slide {activeSlideIdx + 1} of {pptxDeck.slide_count}</span>
                          </div>
                          <span className="text-muted-foreground/40">|</span>
                          <span className="text-muted-foreground font-mono text-[11px]">{pptxDeck.aspect_ratio} Widescreen</span>
                          <span className="text-muted-foreground/40">|</span>
                          <span className="text-muted-foreground text-[11px]">{fileSize}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="flex items-center rounded-lg border border-border bg-muted/60 p-0.5">
                            <button
                              type="button"
                              disabled={activeSlideIdx <= 0}
                              onClick={() => setActiveSlideIdx((i) => Math.max(0, i - 1))}
                              className="p-1 rounded text-muted-foreground hover:text-foreground disabled:opacity-30 transition-colors"
                              title="Previous slide (Left Arrow)"
                            >
                              <ChevronLeft className="h-4 w-4" />
                            </button>
                            <button
                              type="button"
                              disabled={activeSlideIdx >= pptxDeck.slide_count - 1}
                              onClick={() => setActiveSlideIdx((i) => Math.min(pptxDeck.slide_count - 1, i + 1))}
                              className="p-1 rounded text-muted-foreground hover:text-foreground disabled:opacity-30 transition-colors"
                              title="Next slide (Right Arrow)"
                            >
                              <ChevronRight className="h-4 w-4" />
                            </button>
                          </div>
                          <Button
                            size="sm"
                            onClick={handleDownload}
                            prefix={<Download className="h-3.5 w-3.5" />}
                            className="bg-orange-600 hover:bg-orange-700 text-white text-xs font-semibold gap-1.5"
                          >
                            Download .pptx
                          </Button>
                        </div>
                      </div>

                      {/* Main Slides Content: Sidebar Thumbnails + Big Slide Card */}
                      <div className="flex flex-1 min-h-0 gap-3">
                        {/* Slide Thumbnails List */}
                        <div className="hidden sm:flex w-52 shrink-0 flex-col gap-2 overflow-y-auto pr-1">
                          {pptxDeck.slides.map((s, idx) => (
                            <button
                              key={idx}
                              type="button"
                              onClick={() => setActiveSlideIdx(idx)}
                              className={cn(
                                "flex flex-col gap-1 rounded-xl border p-2.5 text-left transition-all",
                                idx === activeSlideIdx
                                  ? "border-orange-500 bg-orange-50/80 text-foreground shadow-xs font-medium"
                                  : "border-border bg-card hover:border-border/80 hover:bg-muted/40",
                              )}
                            >
                              <div className="flex items-center justify-between text-[11px] font-bold">
                                <span className={idx === activeSlideIdx ? "text-orange-600" : "text-muted-foreground"}>
                                  Slide {idx + 1}
                                </span>
                              </div>
                              <span className="truncate text-xs font-medium text-foreground">
                                {s.title || `Slide ${idx + 1}`}
                              </span>
                            </button>
                          ))}
                        </div>

                        {/* Active Slide Canvas Preview */}
                        <div className="flex-1 min-h-0 overflow-y-auto rounded-2xl border border-border bg-card p-6 shadow-xs">
                          {(() => {
                            const slide = pptxDeck.slides[activeSlideIdx];
                            if (!slide) return null;
                            return (
                              <div className="flex flex-col gap-5 max-w-3xl mx-auto">
                                <div className="border-b border-border pb-3">
                                  <div className="text-[11px] font-mono uppercase tracking-widest text-orange-600 mb-1 font-semibold">
                                    INDRA Presentation Deck • Slide {activeSlideIdx + 1}
                                  </div>
                                  <h2 className="text-xl sm:text-2xl font-bold text-foreground tracking-tight">
                                    {slide.title}
                                  </h2>
                                </div>

                                {/* Slide Texts */}
                                {slide.texts.length > 1 && (
                                  <div className="space-y-3 text-foreground text-sm leading-relaxed">
                                    {slide.texts.slice(1).map((t, tIdx) => (
                                      <div
                                        key={tIdx}
                                        className="rounded-xl border border-border bg-muted/30 p-3.5 whitespace-pre-wrap font-sans text-xs sm:text-sm text-foreground"
                                      >
                                        {t}
                                      </div>
                                    ))}
                                  </div>
                                )}

                                {/* Slide Tables */}
                                {slide.tables && slide.tables.length > 0 && (
                                  <div className="space-y-3">
                                    {slide.tables.map((table, tblIdx) => (
                                      <div
                                        key={tblIdx}
                                        className="overflow-x-auto rounded-xl border border-border bg-card"
                                      >
                                        <table className="w-full border-collapse text-xs">
                                          <tbody>
                                            {table.map((row, rIdx) => (
                                              <tr
                                                key={rIdx}
                                                className={cn(
                                                  "border-b border-border transition-colors",
                                                  rIdx === 0
                                                    ? "bg-muted/70 font-bold text-foreground"
                                                    : "hover:bg-muted/30 text-foreground",
                                                )}
                                              >
                                                {row.map((cell, cIdx) => (
                                                  <td key={cIdx} className="p-2.5">
                                                    {cell}
                                                  </td>
                                                ))}
                                              </tr>
                                            ))}
                                          </tbody>
                                        </table>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            );
                          })()}
                        </div>
                      </div>
                    </div>
                  ) : (
                    /* Fallback PowerPoint Card when outline is loading or unavailable */
                    <div className="flex h-full w-full items-center justify-center p-6 overflow-y-auto">
                      <div className="w-full max-w-2xl rounded-2xl border border-border bg-card p-8 text-center shadow-xs">
                        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-orange-50 text-orange-600 border border-orange-200 mb-4">
                          <Presentation className="h-8 w-8" />
                        </div>
                        <h3 className="text-xl font-bold text-foreground mb-2">{fileName}</h3>
                        <p className="text-sm text-muted-foreground max-w-md mx-auto mb-6">
                          Claude-Grade 16:9 PowerPoint Presentation generated by INDRA 100% offline tools suite.
                        </p>

                        <div className="grid grid-cols-2 gap-3 max-w-sm mx-auto mb-6 text-left">
                          <div className="rounded-lg border border-border bg-muted/30 p-3">
                            <div className="text-[11px] text-muted-foreground uppercase font-bold">Slide Format</div>
                            <div className="text-sm font-semibold text-foreground">16:9 Widescreen</div>
                          </div>
                          <div className="rounded-lg border border-border bg-muted/30 p-3">
                            <div className="text-[11px] text-muted-foreground uppercase font-bold">File Size</div>
                            <div className="text-sm font-semibold text-foreground">{fileSize}</div>
                          </div>
                        </div>

                        <div className="flex items-center justify-center gap-3">
                          <Button
                            onClick={handleDownload}
                            prefix={<Download className="h-4 w-4" />}
                            className="bg-orange-600 hover:bg-orange-700 text-white font-semibold"
                          >
                            Download Presentation (.pptx)
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Image Viewer */}
              {category?.type === "image" && (
                <div className="flex h-full w-full items-center justify-center p-6 overflow-auto bg-muted/20">
                  <img
                    src={fileData?.data_url || directViewUrl}
                    alt={fileName}
                    className="max-h-full max-w-full rounded-xl border border-border object-contain shadow-md bg-card"
                  />
                </div>
              )}

              {/* Binary / Other View */}
              {category?.type === "binary" && (
                <div className="flex h-full w-full items-center justify-center p-6">
                  <div className="text-center">
                    <FileIcon className="mx-auto h-12 w-12 text-muted-foreground mb-3" />
                    <h3 className="text-lg font-semibold text-foreground mb-1">{fileName}</h3>
                    <p className="text-xs text-muted-foreground mb-4">{fileSize} • Binary artifact</p>
                    <Button onClick={handleDownload} prefix={<Download className="h-4 w-4" />}>
                      Download File
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer Status Bar */}
        <footer className="flex min-h-8 items-center justify-between border-t border-border bg-card px-4 py-1.5 text-xs text-muted-foreground font-mono">
          <div className="flex items-center gap-3">
            <span>INDRA Artifact Subsystem</span>
            <span>•</span>
            <span>UTF-8</span>
            {category?.isEditable && (
              <>
                <span>•</span>
                <span>{content.split("\n").length} lines</span>
                <span>•</span>
                <span>{content.length} chars</span>
              </>
            )}
            {category?.type === "pptx" && pptxDeck && (
              <>
                <span>•</span>
                <span>{pptxDeck.slide_count} slides</span>
                <span>•</span>
                <span>{pptxDeck.aspect_ratio}</span>
              </>
            )}
          </div>
          <div className="flex items-center gap-2">
            {category?.isEditable ? (
              isDirty ? (
                <span className="text-amber-600 font-semibold">Ctrl+S to save</span>
              ) : (
                <span className="text-emerald-600 font-semibold flex items-center gap-1">
                  <Check className="h-3 w-3" /> Synced to disk
                </span>
              )
            ) : (
              <span>Ready</span>
            )}
          </div>
        </footer>
      </div>
    </div>,
    document.body,
  );
}

function CsvTablePreview({ rawCsv }: { rawCsv: string }) {
  const rows = useMemo(() => {
    return rawCsv
      .split("\n")
      .map((r) => r.trim())
      .filter(Boolean)
      .map((r) => r.split(",").map((c) => c.trim().replace(/^["']|["']$/g, "")));
  }, [rawCsv]);

  if (!rows.length) {
    return <div className="p-4 text-xs text-muted-foreground">Empty CSV file</div>;
  }

  const header = rows[0];
  const body = rows.slice(1);

  return (
    <div className="h-full w-full overflow-auto rounded-xl border border-border bg-card shadow-xs">
      <table className="w-full text-left border-collapse text-xs font-mono">
        <thead>
          <tr className="border-b border-border bg-muted/70 sticky top-0">
            {header.map((col, idx) => (
              <th key={idx} className="p-2.5 font-bold text-foreground uppercase tracking-wider">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {body.map((row, rIdx) => (
            <tr key={rIdx} className="hover:bg-muted/40 transition-colors">
              {row.map((cell, cIdx) => (
                <td key={cIdx} className="p-2.5 text-foreground">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
