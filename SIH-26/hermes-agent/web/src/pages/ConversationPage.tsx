import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { ArrowUp, Brain, Check, ChevronDown, ChevronLeft, ChevronRight, CircleCheck, Code2, Eye, FileCode, FileSpreadsheet, FileText, Headphones, HelpCircle, Lightbulb, Mic, MicOff, MessageSquarePlus, Paperclip, Presentation, Send, Settings, ShieldAlert, Sparkles, Square, Terminal, Wrench, X } from "lucide-react";
import { GatewayClient, type GatewayEvent } from "@/lib/gatewayClient";
import { api } from "@/lib/api";
import { ChatSessionList } from "@/components/ChatSessionList";
import { ModelPickerDialog } from "@/components/ModelPickerDialog";
import { ModelReloadConfirm } from "@/components/ModelReloadConfirm";
import { useProfileScope } from "@/contexts/useProfileScope";
import { Markdown } from "@/components/Markdown";
import { ArtifactViewerModal } from "@/components/ArtifactViewerModal";
import { ArtifactsListCard } from "@/components/ArtifactsListCard";
import { ConversationModeModal } from "@/components/ConversationModeModal";
import { ServerSettingsModal } from "@/components/ServerSettingsModal";

type Activity = { kind: "thought" | "tool"; text: string; startedAt?: number; duration?: number; id?: string; detail?: string; status?: "running" | "complete" };
type Message = { role: "user" | "assistant"; text: string; reasoning?: string; activity?: Activity[] };
type TextPayload = { text?: string; status?: string };
type PendingApproval = {
  requestId: string;
  command?: string;
  tool?: string;
  description?: string;
  reason?: string;
  choices?: string[];
};
type PendingClarify = {
  requestId: string;
  question?: string;
  choices?: string[];
  multiSelect?: boolean;
  questions?: Array<{ qid: string; question: string; choices?: string[]; multi_select?: boolean }>;
};
type SpeechResult = { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }>> };
interface BrowserSpeechRecognition {
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: SpeechResult) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

function fileDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error(`Could not read ${file.name}.`));
    reader.readAsDataURL(file);
  });
}

function isImageAttachment(file: File): boolean {
  return file.type.startsWith("image/") || /\.(png|jpe?g|gif|webp|bmp|tiff?|heic)$/i.test(file.name);
}

function historyMessages(value: unknown): Message[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item): Message[] => {
    if (!item || typeof item !== "object") return [];
    const row = item as Record<string, unknown>;
    const role = row.role === "user" || row.role === "assistant" ? row.role : null;
    const text = typeof row.text === "string" ? row.text : typeof row.content === "string" ? row.content : "";
    const reasoning = typeof row.reasoning === "string" ? row.reasoning : typeof row.reasoning_content === "string" ? row.reasoning_content : "";
    return role && (text || reasoning) ? [{ role, text, ...(reasoning ? { reasoning, activity: [{ kind: "thought", text }] } : {}) }] : [];
  });
}

function ResponseActivity({ activity, active }: { activity?: Activity[]; active: boolean }) {
  if (!activity?.length) return null;
  return <details className="indra-reasoning mb-4">
    <summary><Brain size={17} aria-hidden="true" /><span>{active ? "Working…" : "How INDRA worked"}</span><span className="indra-reasoning-count">{activity.length} {activity.length === 1 ? "step" : "steps"}</span><ChevronDown className="indra-reasoning-chevron" size={16} aria-hidden="true" /></summary>
    <div className="indra-reasoning-content">
      {activity.map((item, index) => <div key={item.id ?? index} className="indra-reasoning-step">
        <div className="indra-reasoning-rail">{item.kind === "thought" ? <Brain size={16} aria-hidden="true" /> : <Wrench size={16} aria-hidden="true" />}</div>
        <div className="indra-reasoning-body">
          {item.kind === "thought" ? <><span className="indra-reasoning-label">{item.status === "running" && active ? "Thinking…" : `Thought${item.duration !== undefined ? ` for ${Math.max(1, Math.round(item.duration))}s` : ""}`}</span><div className="indra-reasoning-text"><Markdown content={item.text} /></div></> :
            <><strong>{item.text}</strong>{item.detail && <div className="indra-reasoning-tool-detail"><Terminal size={14} aria-hidden="true" /><span>{item.detail}</span></div>}{item.duration !== undefined && <span className="indra-reasoning-duration">{item.duration.toFixed(1)}s</span>}</>}
        </div>
        {item.kind === "tool" && item.status === "complete" && <CircleCheck className="indra-reasoning-done" size={15} aria-label="Complete" />}
      </div>)}
    </div>
  </details>;
}

function extractArtifactPaths(text: string): string[] {
  if (!text) return [];
  const regex = /(?:[a-zA-Z0-9_\.\-\/\\]+[\/\\])?([a-zA-Z0-9_\.\-]+\.(?:md|markdown|pdf|pptx|ppt|xlsx|xls|docx|doc|csv|json|py|js|ts|html|css|txt|png|jpg|jpeg|svg|webp))\b/gi;
  const matches: string[] = [];
  let m;
  while ((m = regex.exec(text)) !== null) {
    const full = m[0];
    if (full.startsWith("http://") || full.startsWith("https://")) continue;
    if (full.startsWith("127.0.0.1") || full.startsWith("localhost")) continue;
    if (full.includes("/") || full.includes("\\") || full.endsWith(".pptx") || full.endsWith(".pdf") || full.endsWith(".docx") || full.endsWith(".xlsx")) {
      matches.push(full.replace(/^[(`"']+|[)`"',;:]+$/g, ""));
    }
  }
  return Array.from(new Set(matches));
}

function getArtifactBadge(filename: string): { label: string; icon: React.ReactNode; color: string } {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  if (["pptx", "ppt"].includes(ext)) {
    return { label: "POWERPOINT", icon: <Presentation size={14} className="text-orange-500" />, color: "border-orange-500/30 bg-orange-500/10 text-orange-700" };
  }
  if (["pdf"].includes(ext)) {
    return { label: "PDF DOCUMENT", icon: <FileText size={14} className="text-rose-500" />, color: "border-rose-500/30 bg-rose-500/10 text-rose-700" };
  }
  if (["md", "markdown"].includes(ext)) {
    return { label: "MARKDOWN", icon: <FileText size={14} className="text-sky-500" />, color: "border-sky-500/30 bg-sky-500/10 text-sky-700" };
  }
  if (["py", "js", "ts", "json", "html"].includes(ext)) {
    return { label: ext.toUpperCase(), icon: <FileCode size={14} className="text-emerald-500" />, color: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700" };
  }
  if (["csv", "xlsx", "xls"].includes(ext)) {
    return { label: "SPREADSHEET", icon: <FileSpreadsheet size={14} className="text-amber-500" />, color: "border-amber-500/30 bg-amber-500/10 text-amber-700" };
  }
  return { label: "DELIVERABLE", icon: <FileText size={14} className="text-slate-500" />, color: "border-slate-500/30 bg-slate-500/10 text-slate-700" };
}

function MessageArtifactCards({ text, onOpenArtifact }: { text: string; onOpenArtifact: (path: string) => void }) {
  const paths = extractArtifactPaths(text);
  if (!paths.length) return null;

  return (
    <div className="mt-3 flex flex-wrap gap-2 pt-2 border-t border-slate-200/60">
      {paths.map((p) => {
        const name = p.split(/[/\\]/).pop() || p;
        const badge = getArtifactBadge(name);
        return (
          <div
            key={p}
            className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white/95 px-3 py-2 shadow-sm transition-all hover:border-sky-400 hover:shadow-md"
          >
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-100">
              {badge.icon}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="truncate font-mono text-xs font-semibold text-slate-800">{name}</span>
                <span className={`rounded px-1 text-[9px] font-bold ${badge.color}`}>{badge.label}</span>
              </div>
              <div className="text-[10px] text-slate-400 font-mono truncate max-w-[180px]">{p}</div>
            </div>
            <button
              type="button"
              onClick={() => onOpenArtifact(p)}
              className="ml-1 flex items-center gap-1 rounded-lg bg-sky-50 px-2 py-1 text-xs font-medium text-sky-700 hover:bg-sky-100 transition-colors"
            >
              <Eye size={12} />
              <span>Preview</span>
            </button>
          </div>
        );
      })}
    </div>
  );
}

export default function ConversationPage({ isActive = true }: { isActive?: boolean }) {
  const [params, setParams] = useSearchParams();
  const resume = params.get("resume");
  const { profile: scopedProfile } = useProfileScope();
  const [revision, setRevision] = useState(0);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [attachment, setAttachment] = useState<File | null>(null);
  const [modelOpen, setModelOpen] = useState(false);
  const [currentModel, setCurrentModel] = useState("");
  const [pendingReloadModel, setPendingReloadModel] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [recording, setRecording] = useState(false);
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null);
  const [pendingClarify, setPendingClarify] = useState<PendingClarify | null>(null);
  const [clarifyAnswer, setClarifyAnswer] = useState("");
  const [selectedArtifactPath, setSelectedArtifactPath] = useState<string | null>(null);
  const [conversationModeOpen, setConversationModeOpen] = useState(false);
  const [serverSettingsOpen, setServerSettingsOpen] = useState(false);
  const [serverStatus, setServerStatus] = useState<{
    connected: boolean;
    server_url: string;
    latency_ms: number | null;
    active_model: string;
    context_length: number;
    vault_docs_count: number;
  } | null>(null);

  const fetchServerStatus = useCallback(() => {
    fetch("/api/indra/server-status")
      .then((res) => res.json())
      .then((data) => setServerStatus(data))
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetchServerStatus();
    const interval = setInterval(fetchServerStatus, 15000);
    return () => clearInterval(interval);
  }, [fetchServerStatus]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const speechRef = useRef<BrowserSpeechRecognition | null>(null);
  const clientRef = useRef<GatewayClient | null>(null);
  const sessionRef = useRef("");
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const [hasActivated, setHasActivated] = useState(isActive);
  const latestMessage = messages[messages.length - 1];
  const latestAssistantIsBusy = busy && latestMessage?.role === "assistant";
  const responseHasText = latestAssistantIsBusy && Boolean(latestMessage?.text.trim());
  const workingStepsVisible = latestAssistantIsBusy && !responseHasText && Boolean(latestMessage?.activity?.length);

  useEffect(() => {
    if (isActive) setHasActivated(true);
  }, [isActive]);

  useEffect(() => {
    if (!hasActivated) return;
    let live = true;
    const client = new GatewayClient();
    clientRef.current = client;
    sessionRef.current = "";
    const belongs = (event: GatewayEvent) => event.session_id === sessionRef.current;
    const offDelta = client.on<TextPayload>("message.delta", (event) => {
      if (!belongs(event) || !event.payload?.text) return;
      setMessages((current) => {
        const next = [...current];
        const last = next[next.length - 1];
        if (last?.role === "assistant") next[next.length - 1] = { ...last, text: last.text + event.payload!.text! };
        else next.push({ role: "assistant", text: event.payload!.text! });
        return next;
      });
    });
    const offReasoning = client.on<TextPayload>("reasoning.delta", (event) => {
      if (!belongs(event) || !event.payload?.text) return;
      setMessages((current) => {
        const next = [...current];
        const last = next[next.length - 1];
        const message: Message = last?.role === "assistant" ? last : { role: "assistant", text: "" };
        const activity = [...(message.activity ?? [])];
        const previous = activity[activity.length - 1];
        if (previous?.kind === "thought" && previous.status === "running") activity[activity.length - 1] = { ...previous, text: previous.text + event.payload!.text! };
        else activity.push({ kind: "thought", text: event.payload!.text!, startedAt: Date.now(), status: "running" });
        const updated = { ...message, reasoning: (message.reasoning ?? "") + event.payload!.text!, activity };
        if (last?.role === "assistant") next[next.length - 1] = updated;
        else next.push(updated);
        return next;
      });
    });
    const offToolStart = client.on<{ name?: string; tool_id?: string; context?: string }>("tool.start", (event) => {
      if (!belongs(event) || !event.payload?.name) return;
      setMessages((current) => {
        const next = [...current];
        const last = next[next.length - 1];
        const message: Message = last?.role === "assistant" ? last : { role: "assistant", text: "" };
        const activity = [...(message.activity ?? [])];
        const previous = activity[activity.length - 1];
        if (previous?.kind === "thought" && previous.status === "running") activity[activity.length - 1] = { ...previous, duration: previous.startedAt ? (Date.now() - previous.startedAt) / 1000 : undefined, status: "complete" };
        activity.push({ kind: "tool", id: event.payload!.tool_id, text: event.payload!.name!, detail: event.payload!.context, startedAt: Date.now(), status: "running" });
        const updated = { ...message, activity };
        if (last?.role === "assistant") next[next.length - 1] = updated;
        else next.push(updated);
        return next;
      });
    });
    const offToolComplete = client.on<{ tool_id?: string; summary?: string; duration_s?: number }>("tool.complete", (event) => {
      if (!belongs(event)) return;
      setMessages((current) => {
        const next = [...current];
        const last = next[next.length - 1];
        if (last?.role !== "assistant") return current;
        const activity = [...(last.activity ?? [])];
        const index = activity.findLastIndex((item) => item.kind === "tool" && item.status === "running" && (!event.payload?.tool_id || item.id === event.payload.tool_id));
        if (index < 0) return current;
        const item = activity[index];
        activity[index] = { ...item, detail: event.payload?.summary || item.detail, duration: event.payload?.duration_s ?? (item.startedAt ? (Date.now() - item.startedAt) / 1000 : undefined), status: "complete" };
        next[next.length - 1] = { ...last, activity };
        return next;
      });
    });
    const offComplete = client.on<TextPayload>("message.complete", (event) => {
      if (!belongs(event)) return;
      setBusy(false);
      setMessages((current) => {
        const next = [...current];
        const last = next[next.length - 1];
        if (last?.role === "assistant") next[next.length - 1] = { ...last, text: event.payload?.text || last.text, activity: last.activity?.map((item) => item.status === "running" ? { ...item, duration: item.startedAt ? (Date.now() - item.startedAt) / 1000 : undefined, status: "complete" as const } : item) };
        else if (event.payload?.text) next.push({ role: "assistant", text: event.payload.text });
        return next;
      });
    });
    const offError = client.on<TextPayload>("error", (event) => {
      if (belongs(event)) {
        setBusy(false);
        setError(event.payload?.text || "The response failed. Please try again.");
      }
    });
    const offInfo = client.on<{ model?: string }>("session.info", (event) => {
      if (belongs(event) && event.payload?.model) setCurrentModel(event.payload.model);
    });
    const offApprovalReq = client.on<{
      request_id?: string;
      command?: string;
      tool?: string;
      description?: string;
      reason?: string;
      choices?: string[];
    }>("approval.request", (event) => {
      if (!belongs(event) || !event.payload?.request_id) return;
      setPendingApproval({
        requestId: event.payload.request_id,
        command: event.payload.command,
        tool: event.payload.tool,
        description: event.payload.description,
        reason: event.payload.reason,
        choices: event.payload.choices || ["once", "session", "deny"],
      });
    });
    const offApprovalExpire = client.on<{ request_id?: string }>("approval.expire", (event) => {
      if (!belongs(event)) return;
      setPendingApproval((current) => current?.requestId === event.payload?.request_id ? null : current);
    });
    const offClarifyReq = client.on<{
      request_id?: string;
      question?: string;
      choices?: string[];
      multi_select?: boolean;
      questions?: Array<{ qid: string; question: string; choices?: string[]; multi_select?: boolean }>;
    }>("clarify.request", (event) => {
      if (!belongs(event) || !event.payload?.request_id) return;
      setPendingClarify({
        requestId: event.payload.request_id,
        question: event.payload.question,
        choices: event.payload.choices,
        multiSelect: event.payload.multi_select,
        questions: event.payload.questions,
      });
    });
    const offClarifyExpire = client.on<{ request_id?: string }>("clarify.expire", (event) => {
      if (!belongs(event)) return;
      setPendingClarify((current) => current?.requestId === event.payload?.request_id ? null : current);
    });
    void (async () => {
      try {
        await client.connect();
        const result = await client.request<{ session_id: string; messages?: unknown; info?: { model?: string } }>(
          resume ? "session.resume" : "session.create",
          resume
            ? { session_id: resume, source: "dashboard", ...(scopedProfile ? { profile: scopedProfile } : {}) }
            : { source: "dashboard", ...(scopedProfile ? { profile: scopedProfile } : {}) },
        );
        if (!live) return;
        sessionRef.current = result.session_id;
        setCurrentModel(result.info?.model ?? "");
        setMessages(historyMessages(result.messages));
        setReady(true);
        // Hydrate pending approvals on connect/resume
        client.request<{ approvals?: Array<Record<string, unknown>> }>("approval.pending", { session_id: result.session_id })
          .then((appRes) => {
            if (!live) return;
            if (appRes?.approvals && appRes.approvals.length > 0) {
              const top = appRes.approvals[0];
              setPendingApproval({
                requestId: String(top.request_id || ""),
                command: top.command ? String(top.command) : undefined,
                tool: top.tool ? String(top.tool) : undefined,
                description: top.description ? String(top.description) : undefined,
                reason: top.reason ? String(top.reason) : undefined,
                choices: Array.isArray(top.choices) ? (top.choices as string[]) : ["once", "session", "deny"],
              });
            }
          }).catch(() => {});
      } catch (cause) {
        if (live) setError(cause instanceof Error ? cause.message : "Could not connect to chat.");
      }
    })();
    return () => {
      live = false;
      offDelta(); offReasoning(); offToolStart(); offToolComplete(); offComplete(); offError(); offInfo();
      offApprovalReq(); offApprovalExpire(); offClarifyReq(); offClarifyExpire();
      client.close();
      if (clientRef.current === client) clientRef.current = null;
    };
  }, [resume, revision, scopedProfile, hasActivated]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ block: "end" }); }, [messages, busy, pendingApproval, pendingClarify]);

  const newChat = useCallback(() => {
    setParams({});
    setMessages([]);
    setError("");
    setPendingApproval(null);
    setPendingClarify(null);
    setClarifyAnswer("");
    setReady(false);
    setBusy(false);
    setAttachment(null);
    setRevision((value) => value + 1);
  }, [setParams]);

  const handleRespondApproval = useCallback(async (choice: string) => {
    if (!pendingApproval || !clientRef.current || !sessionRef.current) return;
    const rid = pendingApproval.requestId;
    setPendingApproval(null);
    try {
      await clientRef.current.request("approval.respond", {
        session_id: sessionRef.current,
        request_id: rid,
        choice,
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to send approval response.");
    }
  }, [pendingApproval]);

  const handleRespondClarify = useCallback(async (answer: string) => {
    if (!pendingClarify || !clientRef.current || !sessionRef.current) return;
    const rid = pendingClarify.requestId;
    setPendingClarify(null);
    setClarifyAnswer("");
    try {
      await clientRef.current.request("clarify.respond", {
        session_id: sessionRef.current,
        request_id: rid,
        answer,
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to answer question.");
    }
  }, [pendingClarify]);

  const applyModel = useCallback(async ({ provider, model, confirmExpensiveModel }: { provider: string; model: string; confirmExpensiveModel?: boolean }) => {
    const result = await api.setModelAssignment({ scope: "main", provider, model, confirm_expensive_model: confirmExpensiveModel }, scopedProfile);
    if (!result.confirm_required) setPendingReloadModel(model);
    return result;
  }, [scopedProfile]);

  const send = useCallback(async () => {
    const text = draft.trim();
    if ((!text && !attachment) || busy || !ready || !clientRef.current || !sessionRef.current) return;
    let prompt = text;
    try {
      if (attachment) {
        const dataUrl = await fileDataUrl(attachment);
        if (isImageAttachment(attachment)) {
          await clientRef.current.request("image.attach_bytes", {
            session_id: sessionRef.current, filename: attachment.name,
            content_base64: dataUrl.slice(dataUrl.indexOf(",") + 1),
          });
          prompt = text || "What is in this image? Read any visible text.";
        } else {
          const result = await clientRef.current.request<{ ref_text: string }>("file.attach", {
            session_id: sessionRef.current, name: attachment.name, data_url: dataUrl,
          });
          prompt = [text, result.ref_text].filter(Boolean).join("\n");
        }
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "File could not be attached.");
      return;
    }
    setDraft("");
    setAttachment(null);
    setError("");
    setBusy(true);
    setMessages((current) => [...current, { role: "user", text: [text, attachment?.name && `📎 ${attachment.name}`].filter(Boolean).join("\n") }]);
    try {
      await clientRef.current.request("prompt.submit", { session_id: sessionRef.current, text: prompt });
    } catch (cause) {
      setBusy(false);
      setError(cause instanceof Error ? cause.message : "Message could not be sent.");
    }
  }, [draft, attachment, busy, ready]);

  const handleConversationMessage = useCallback(async (text: string) => {
    if (!text.trim() || !clientRef.current || !sessionRef.current) return;
    setError("");
    setBusy(true);
    setMessages((current) => [...current, { role: "user", text }]);
    try {
      await clientRef.current.request("prompt.submit", { session_id: sessionRef.current, text });
    } catch (cause) {
      setBusy(false);
      setError(cause instanceof Error ? cause.message : "Message could not be sent.");
    }
  }, []);

  const toggleVoice = useCallback(() => {
    if (speechRef.current) { speechRef.current.stop(); return; }
    const browser = window as Window & { SpeechRecognition?: new () => BrowserSpeechRecognition; webkitSpeechRecognition?: new () => BrowserSpeechRecognition };
    const Recognition = browser.SpeechRecognition ?? browser.webkitSpeechRecognition;
    if (!Recognition) { setError("Voice input is unavailable in this browser. Try Chrome or Edge."); return; }
    const speech = new Recognition();
    speech.continuous = true;
    speech.interimResults = false;
    speech.onresult = (event) => {
      const transcript = Array.from(event.results).slice(event.resultIndex).map((result) => result[0]?.transcript ?? "").join(" ").trim();
      if (transcript) setDraft((current) => [current.trim(), transcript].filter(Boolean).join(" "));
    };
    speech.onerror = () => setError("Microphone input failed. Check browser permission and try again.");
    speech.onend = () => { speechRef.current = null; setRecording(false); };
    speechRef.current = speech;
    setRecording(true);
    speech.start();
  }, []);

  const isEmpty = messages.length === 0;
  return <div className="indra-conversation indra-conversation--welcome flex min-h-0 flex-1 gap-5 font-sans text-[#20242a]">
    <aside className={`hidden shrink-0 flex-col rounded-2xl border border-[#e7e8e9] bg-white p-3 lg:flex ${sidebarOpen ? "" : "indra-sidebar-collapsed"}`}>
      <div className="indra-sidebar-header">
        {sidebarOpen && <button onClick={newChat} className="flex items-center gap-2 rounded-xl px-3 py-3 text-left font-semibold hover:bg-[#f3f4f4]"><MessageSquarePlus size={18} /> New chat</button>}
        <button type="button" aria-label={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"} aria-expanded={sidebarOpen} onClick={() => setSidebarOpen((value) => !value)} className="indra-sidebar-toggle">{sidebarOpen ? <ChevronLeft size={18} /> : <ChevronRight size={18} />}</button>
      </div>
      {sidebarOpen && <>
      <div className="mt-3 min-h-0 flex-1 overflow-auto">
        <ArtifactsListCard onSelectArtifact={(p) => setSelectedArtifactPath(p)} className="mb-3" />
        <ChatSessionList activeSessionId={resume} profile={scopedProfile} onNewChat={newChat} />
      </div>
      </>}
    </aside>
    <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-[#e7e8e9] bg-white">
      <header className="flex items-center justify-between border-b border-[#eceeef] px-5 py-4">
        <div>
          <h1 className="text-lg font-semibold">Chat with INDRA</h1>
          <p className="text-sm text-[#747a80]">Ask anything in your own words</p>
        </div>
        <div className="flex items-center gap-2">
          {/* 1-Click Server Status & Context Pill */}
          <button
            type="button"
            onClick={() => setServerSettingsOpen(true)}
            className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold shadow-sm transition-all ${
              serverStatus?.connected
                ? "border-emerald-200 bg-emerald-50 text-emerald-800 hover:bg-emerald-100"
                : "border-rose-200 bg-rose-50 text-rose-800 hover:bg-rose-100"
            }`}
            title="Configure GPU Server & Context Window (1-Click)"
          >
            <span
              className={`h-2 w-2 rounded-full ${
                serverStatus?.connected ? "bg-emerald-500 animate-pulse" : "bg-rose-500"
              }`}
            />
            <span>{serverStatus?.connected ? `GPU (${serverStatus.latency_ms ?? 0}ms)` : "Server Offline"}</span>
            <span className="rounded bg-black/5 px-1 py-0.2 font-mono text-[10px] font-bold">
              {serverStatus?.context_length ? `${Math.round(serverStatus.context_length / 1024)}K` : "16K"}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setServerSettingsOpen(true)}
            className="flex items-center gap-1.5 rounded-lg border border-[#e4e6e8] bg-white px-2.5 py-1.5 text-xs font-semibold text-[#181C22] shadow-sm hover:bg-slate-50 transition-all"
            title="Open Server & AI Settings"
          >
            <Settings size={14} className="text-slate-600" />
            <span>Settings</span>
          </button>

          <button
            type="button"
            onClick={() => setSelectedArtifactPath("outputs/test_docs/rich_test_deck.pptx")}
            className="flex items-center gap-1.5 rounded-lg border border-[#e4e6e8] bg-white px-3 py-1.5 text-xs font-semibold text-[#181C22] shadow-sm hover:border-sky-500/50 hover:bg-sky-50 transition-all"
            title="Inspect latest artifact"
          >
            <Sparkles size={14} className="text-sky-500" />
            <span>Artifacts</span>
          </button>
          <button onClick={newChat} className="rounded-lg border border-[#e4e6e8] px-3 py-1.5 text-sm hover:bg-slate-50 transition-all">
            New chat
          </button>
        </div>
      </header>
      {/* Friendly Offline Notice for Non-Technical Users */}
      {serverStatus && !serverStatus.connected && (
        <div className="flex items-center justify-between border-b border-amber-200 bg-amber-50/90 px-5 py-2 text-xs text-amber-950">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-amber-500 shrink-0" />
            <span>
              <strong>Workstation Offline:</strong> GPU server not detected at{" "}
              <code className="rounded bg-amber-100 px-1 font-mono text-[11px]">{serverStatus.server_url}</code>.
            </span>
          </div>
          <button
            type="button"
            onClick={() => setServerSettingsOpen(true)}
            className="rounded-lg bg-amber-200 px-2.5 py-1 font-bold text-amber-950 shadow-sm hover:bg-amber-300 transition-colors"
          >
            Configure Server in 1 Click →
          </button>
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-7 sm:px-8" aria-live="polite">
        <div className="mx-auto flex max-w-3xl flex-col gap-6">
          {isEmpty && <div className="indra-welcome">
            <div className="indra-welcome-mark"><img src="/logo.png" alt="INDRA logo" /></div>
            <h2>Chat with INDRA</h2>
            <p>Your local AI workbench. Ask a question, explore an idea, or work with a file.</p>
            <div className="indra-welcome-cards">
              <button type="button" onClick={() => setDraft("Help me write and explain code for ")}><span className="indra-welcome-card-icon indra-welcome-card-icon--code"><Code2 size={19} /></span><strong>Write code</strong><span>Build, explain, or debug something.</span><ArrowUp size={16} className="indra-welcome-card-arrow" /></button>
              <button type="button" onClick={() => fileInputRef.current?.click()}><span className="indra-welcome-card-icon indra-welcome-card-icon--files"><FileText size={19} /></span><strong>Analyze a file</strong><span>Upload an image, PDF, or document.</span><ArrowUp size={16} className="indra-welcome-card-arrow" /></button>
              <button type="button" onClick={() => setDraft("Explain this step by step: ")}><span className="indra-welcome-card-icon indra-welcome-card-icon--idea"><Lightbulb size={19} /></span><strong>Get an explanation</strong><span>Make a complex topic clear.</span><ArrowUp size={16} className="indra-welcome-card-arrow" /></button>
            </div>
            <div className="indra-welcome-prompts"><span>Try asking</span>{["Explain this code", "Analyze an image", "Summarize a document", "Help me plan"].map((prompt) => <button key={prompt} type="button" onClick={() => setDraft(prompt)}>{prompt}</button>)}</div>
          </div>}
          {messages.map((message, index) => <div key={index} translate="no" className={message.role === "user" ? "ml-auto max-w-[85%] whitespace-pre-wrap rounded-2xl bg-[#eff1f1] px-4 py-3" : "indra-assistant-message max-w-full leading-relaxed"}>
            {message.role === "assistant" && <ResponseActivity activity={message.activity} active={busy && index === messages.length - 1 && !message.text.trim()} />}
            {message.role === "assistant" ? message.text && (
              <div className={`indra-response-stream ${busy && index === messages.length - 1 ? "indra-response-stream--active" : ""}`}>
                <Markdown content={message.text} />
                <MessageArtifactCards text={message.text} onOpenArtifact={(p) => setSelectedArtifactPath(p)} />
              </div>
            ) : message.text}
          </div>)}
          {busy && !workingStepsVisible && <div className="indra-working-indicator" role="status" aria-live="polite"><span className="indra-working-spinner" aria-hidden="true" /><span>{responseHasText ? "Writing your response…" : "Working on your request…"}</span><span className="indra-working-dots" aria-hidden="true"><i /><i /><i /></span></div>}
          <div ref={bottomRef} />
        </div>
      </div>
      <div className="indra-chat-composer mx-auto w-full max-w-3xl px-4 pb-5 sm:px-8">
        {/* Interactive Action Approval Card */}
        {pendingApproval && (
          <div className="indra-action-card indra-action-card--approval" role="alert" aria-live="assertive">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-500/20 text-amber-700">
                <ShieldAlert size={20} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-sm font-bold text-amber-950">Action Requires Approval</h3>
                  <span className="rounded-full bg-amber-200/80 px-2 py-0.5 text-[11px] font-bold text-amber-900">
                    Security Guard
                  </span>
                </div>
                <p className="mt-1 text-xs text-amber-900">
                  {pendingApproval.description || (pendingApproval.tool ? `Agent requested to run ${pendingApproval.tool}.` : "The agent requires user authorization before proceeding:")}
                </p>
                {pendingApproval.command && (
                  <div className="indra-action-command-box">
                    <div className="flex items-center gap-1.5 text-[11px] font-semibold text-amber-800 mb-1">
                      <Terminal size={13} />
                      <span>Command to execute:</span>
                    </div>
                    <code>{pendingApproval.command}</code>
                  </div>
                )}
                {pendingApproval.reason && (
                  <p className="mt-2 text-xs text-amber-950 font-medium">
                    Note: {pendingApproval.reason}
                  </p>
                )}
                <div className="mt-3.5 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void handleRespondApproval("once")}
                    className="indra-action-btn-approve"
                  >
                    <Check size={14} /> Approve (Once)
                  </button>
                  {pendingApproval.choices?.includes("session") && (
                    <button
                      type="button"
                      onClick={() => void handleRespondApproval("session")}
                      className="indra-action-btn-session"
                    >
                      Always Allow for Session
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void handleRespondApproval("deny")}
                    className="indra-action-btn-deny"
                  >
                    <X size={14} /> Deny / Reject
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Interactive Clarification / Question Card */}
        {pendingClarify && (
          <div className="indra-action-card indra-action-card--clarify" role="region" aria-label="Agent question">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-sky-500/20 text-sky-700">
                <HelpCircle size={20} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-sm font-bold text-sky-950">Clarification Needed</h3>
                  <span className="rounded-full bg-sky-200/80 px-2 py-0.5 text-[11px] font-bold text-sky-900">
                    Input Required
                  </span>
                </div>
                <p className="mt-1 text-sm font-semibold text-sky-950">
                  {pendingClarify.question || "The agent is asking for your input to continue:"}
                </p>
                {pendingClarify.choices && pendingClarify.choices.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {pendingClarify.choices.map((choice) => (
                      <button
                        key={choice}
                        type="button"
                        onClick={() => void handleRespondClarify(choice)}
                        className="indra-action-choice-btn"
                      >
                        {choice}
                      </button>
                    ))}
                  </div>
                )}
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (clarifyAnswer.trim()) {
                      void handleRespondClarify(clarifyAnswer.trim());
                    }
                  }}
                  className="mt-3 flex items-center gap-2"
                >
                  <input
                    type="text"
                    placeholder="Type custom answer or instructions…"
                    value={clarifyAnswer}
                    onChange={(e) => setClarifyAnswer(e.target.value)}
                    className="flex-1 rounded-xl border border-sky-300 bg-white px-3 py-2 text-xs text-slate-800 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none shadow-sm"
                  />
                  <button
                    type="submit"
                    disabled={!clarifyAnswer.trim()}
                    className="flex items-center gap-1.5 rounded-xl bg-sky-600 px-3.5 py-2 text-xs font-bold text-white shadow-sm hover:bg-sky-500 disabled:opacity-40 transition-colors"
                  >
                    <Send size={13} /> Submit
                  </button>
                </form>
              </div>
            </div>
          </div>
        )}

        {error && <p role="alert" className="mb-2 text-sm text-red-600">{error} <button onClick={() => { setError(""); setReady(false); setRevision((value) => value + 1); }} className="underline">Reconnect</button></p>}
        {attachment && <div className="mb-2 flex items-center gap-2 rounded-xl bg-[#eef0e9] px-3 py-2 text-sm text-[#20242a]"><Paperclip size={15} /><span className="min-w-0 flex-1 truncate">{attachment.name}</span><button type="button" aria-label="Remove attachment" onClick={() => setAttachment(null)}><X size={16} /></button></div>}
        {attachment && isImageAttachment(attachment) && <p className="mb-2 text-xs text-[#4c5557]">Images are sent to INDRA Vision automatically for reading and OCR.</p>}
        <div className="indra-composer-tools mb-2 flex items-center gap-2">
          <input ref={fileInputRef} type="file" className="hidden" onChange={(event) => { setAttachment(event.target.files?.[0] ?? null); event.target.value = ""; }} />
          <button type="button" aria-label="Attach file" disabled={!ready || busy} onClick={() => fileInputRef.current?.click()} className="indra-chat-tool"><Paperclip size={16} /> Attach</button>
          <button
            type="button"
            aria-label="Open Conversation Mode"
            disabled={!ready}
            onClick={() => setConversationModeOpen(true)}
            className="indra-chat-tool flex items-center gap-1.5 font-medium text-emerald-800 bg-emerald-50/80 border-emerald-200 hover:bg-emerald-100/90 transition-colors shadow-sm"
            title="Interactive Conversation Mode (100% Local STT & TTS)"
          >
            <Headphones size={15} className="text-emerald-700" />
            <span>Voice Mode</span>
            <span className="rounded bg-emerald-200/80 px-1 py-0.2 text-[9px] font-bold text-emerald-900 tracking-wider">LOCAL</span>
          </button>
          <button type="button" aria-label={recording ? "Stop voice input" : "Start voice input"} disabled={!ready} onClick={toggleVoice} className="indra-chat-tool">{recording ? <MicOff size={16} /> : <Mic size={16} />} {recording ? "Stop voice" : "Voice"}</button>
          <button type="button" aria-label={`Current model: ${currentModel || "Loading model"}. Change model`} disabled={!ready || busy} onClick={() => setModelOpen(true)} className="indra-chat-tool indra-model-button ml-auto"><span className="truncate">{currentModel || "Loading model"}</span><ChevronDown size={15} /></button>
        </div>
        <div className="indra-composer-input flex items-end gap-2 rounded-2xl border border-[#d9dddf] bg-white p-2 shadow-sm"><textarea aria-label="Message INDRA" placeholder={ready ? "Message INDRA…" : "Connecting to INDRA…"} value={draft} disabled={!ready} rows={2} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); } }} className="max-h-40 min-h-12 flex-1 resize-none bg-transparent px-3 py-2 outline-none" /><button type="button" aria-label={busy ? "Stop response" : "Send message"} disabled={!ready || (!busy && !draft.trim() && !attachment)} onClick={() => { if (busy) { void clientRef.current?.request("session.interrupt", { session_id: sessionRef.current }); setBusy(false); } else void send(); }} className="rounded-xl bg-[#ebf836] p-3 text-[#161b1e] disabled:opacity-40">{busy ? <Square size={18} /> : <ArrowUp size={18} />}</button></div>
        <p className="mt-2 text-center text-xs text-[#90969a]">Press Enter to send · Shift+Enter for a new line</p>
      </div>
    </section>
    {modelOpen && <ModelPickerDialog loader={() => api.getModelOptions(scopedProfile)} alwaysGlobal onApply={applyModel} onClose={() => setModelOpen(false)} />}
    <ModelReloadConfirm model={pendingReloadModel} onCancel={() => { setPendingReloadModel(null); setError("Model saved. Start a new chat to use it; this conversation still uses the previous model."); }} onConfirm={() => { window.location.href = window.location.pathname; }} />
    <ArtifactViewerModal
      filePath={selectedArtifactPath}
      onClose={() => setSelectedArtifactPath(null)}
    />
    <ConversationModeModal
      isOpen={conversationModeOpen}
      onClose={() => setConversationModeOpen(false)}
      onSendMessage={handleConversationMessage}
      lastAssistantMessage={latestMessage?.role === "assistant" ? latestMessage.text : ""}
      isModelBusy={busy}
    />
    <ServerSettingsModal
      isOpen={serverSettingsOpen}
      onClose={() => setServerSettingsOpen(false)}
      onSaved={fetchServerStatus}
    />
  </div>;
}

