import { useEffect, useState } from "react";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Cpu,
  Database,
  Eye,
  EyeOff,
  Globe,
  HardDrive,
  Layers,
  Loader2,
  RefreshCw,
  Server,
  Sliders,
  Sparkles,
  X,
  Zap,
} from "lucide-react";

interface ServerStatus {
  connected: boolean;
  server_url: string;
  api_key_set: boolean;
  masked_key: string;
  latency_ms: number | null;
  active_model: string;
  context_length: number;
  context_preset: string;
  available_models: string[];
  vault_path: string;
  vault_docs_count: number;
  rag_enabled: boolean;
  error_message: string | null;
}

interface ServerSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

const CONTEXT_CARDS = [
  {
    id: "eco",
    tokens: 4096,
    label: "Eco",
    vram: "6GB – 8GB VRAM",
    target: "RTX 3060 / 4060 / Laptops",
    desc: "Ultra-fast response with minimum memory overhead. Ideal for entry-level GPUs.",
    icon: Zap,
    color: "from-amber-500/10 to-amber-500/5 text-amber-600 border-amber-500/30",
  },
  {
    id: "balanced",
    tokens: 16384,
    label: "Balanced",
    vram: "12GB – 16GB VRAM",
    target: "RTX 3080 / 4070 / 4080",
    desc: "Optimal balance of document depth and inference speed. Recommended for general use.",
    icon: Layers,
    color: "from-sky-500/10 to-sky-500/5 text-sky-600 border-sky-500/30",
    recommended: true,
  },
  {
    id: "power",
    tokens: 32768,
    label: "Power",
    vram: "24GB VRAM",
    target: "RTX 3090 / 4090",
    desc: "Handles lengthy research dossiers and complex multi-page document synthesis.",
    icon: Cpu,
    color: "from-indigo-500/10 to-indigo-500/5 text-indigo-600 border-indigo-500/30",
  },
  {
    id: "ultra",
    tokens: 65536,
    label: "Ultra",
    vram: "48GB+ VRAM",
    target: "NVIDIA A100 / H100 / Multi-GPU",
    desc: "Enterprise deep context archive ingestion and massive knowledge correlation.",
    icon: Sparkles,
    color: "from-purple-500/10 to-purple-500/5 text-purple-600 border-purple-500/30",
  },
];

export function ServerSettingsModal({ isOpen, onClose, onSaved }: ServerSettingsModalProps) {
  const [activeTab, setActiveTab] = useState<"server" | "context" | "rag" | "artifactory">("server");

  // Form State
  const [serverUrl, setServerUrl] = useState("http://127.0.0.1:8000");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [selectedTokens, setSelectedTokens] = useState<number>(16384);
  const [vaultPath, setVaultPath] = useState("./MyVault");
  const [ragEnabled, setRagEnabled] = useState(true);

  // Artifactory State
  const [enableArtifactory, setEnableArtifactory] = useState(false);
  const [artifactoryUrl, setArtifactoryUrl] = useState("");
  const [artifactoryRepo, setArtifactoryRepo] = useState("");
  const [artifactoryUser, setArtifactoryUser] = useState("");
  const [artifactoryToken, setArtifactoryToken] = useState("");

  // Testing & Status State
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    latency_ms?: number;
    models?: string[];
    message: string;
  } | null>(null);
  const [reindexMsg, setReindexMsg] = useState<string | null>(null);
  const [reindexing, setReindexing] = useState(false);
  const [status, setStatus] = useState<ServerStatus | null>(null);

  // Fetch initial status when modal opens
  useEffect(() => {
    if (!isOpen) return;

    fetch("/api/indra/server-status")
      .then((res) => res.json())
      .then((data: ServerStatus) => {
        setStatus(data);
        if (data.server_url) setServerUrl(data.server_url);
        if (data.context_length) setSelectedTokens(data.context_length);
        if (data.vault_path) setVaultPath(data.vault_path);
        setRagEnabled(data.rag_enabled);
      })
      .catch((err) => {
        console.error("Could not fetch server status:", err);
      });
  }, [isOpen]);

  if (!isOpen) return null;

  async function handleTestConnection() {
    setLoading(true);
    setTestResult(null);
    try {
      const res = await fetch("/api/indra/test-connection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ server_url: serverUrl, api_key: apiKey }),
      });
      const data = await res.json();
      setTestResult(data);
    } catch (err) {
      setTestResult({
        ok: false,
        message: `Network Error: Could not reach client gateway. (${String(err)})`,
      });
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveSettings() {
    setSaving(true);
    try {
      const payload: any = {
        server_url: serverUrl,
        api_key: apiKey || undefined,
        context_length: selectedTokens,
        vault_path: vaultPath,
        rag_enabled: ragEnabled,
      };

      if (enableArtifactory) {
        payload.artifactory_url = artifactoryUrl;
        payload.artifactory_repo = artifactoryRepo;
        payload.artifactory_user = artifactoryUser;
        payload.artifactory_token = artifactoryToken;
      }

      const res = await fetch("/api/indra/configure-server", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.ok) {
        if (onSaved) onSaved();
        onClose();
      } else {
        alert(data.message || "Failed to save settings.");
      }
    } catch (err) {
      alert(`Error saving settings: ${String(err)}`);
    } finally {
      setSaving(false);
    }
  }

  async function handleReindexVault() {
    setReindexing(true);
    setReindexMsg(null);
    try {
      const res = await fetch("/api/indra/rag-reindex", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ vault_path: vaultPath }),
      });
      const data = await res.json();
      setReindexMsg(data.message);
    } catch (err) {
      setReindexMsg(`Indexing failed: ${String(err)}`);
    } finally {
      setReindexing(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="flex h-auto max-h-[90vh] w-full max-w-2xl flex-col rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/60 px-6 py-4 dark:border-slate-800 dark:bg-slate-900/60">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/10 text-blue-600 dark:bg-blue-500/20 dark:text-blue-400">
              <Server size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">
                  INDRA Server & AI Settings
                </h2>
                {status && (
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                      status.connected
                        ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                        : "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300"
                    }`}
                  >
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        status.connected ? "bg-emerald-500" : "bg-rose-500"
                      }`}
                    />
                    {status.connected
                      ? `Connected (${status.latency_ms ?? 0}ms)`
                      : "Disconnected"}
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Configure your GPU inference server, context window, and knowledge vault.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-slate-100 px-6 bg-slate-50/30 dark:border-slate-800 dark:bg-slate-900/30">
          {[
            { id: "server", label: "GPU Server & Key", icon: Globe },
            { id: "context", label: "Context Window", icon: Sliders },
            { id: "rag", label: "Knowledge Vault (RAG)", icon: Database },
            { id: "artifactory", label: "Artifactory", icon: HardDrive },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center gap-2 border-b-2 py-3 px-3 text-xs font-semibold transition-all ${
                  isActive
                    ? "border-blue-600 text-blue-600 dark:border-blue-400 dark:text-blue-400"
                    : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
                }`}
              >
                <Icon size={14} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Tab Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* TAB 1: GPU SERVER & KEY */}
          {activeTab === "server" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <label className="text-xs font-bold text-slate-700 dark:text-slate-300">
                  Target Inference Node
                </label>
                <div className="flex items-center gap-2 text-xs">
                  <button
                    type="button"
                    onClick={() => setServerUrl("http://127.0.0.1:8000")}
                    className={`rounded-md px-2.5 py-1 font-medium transition-all ${
                      serverUrl.includes("127.0.0.1") || serverUrl.includes("localhost")
                        ? "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300 font-bold"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300"
                    }`}
                  >
                    🏠 Localhost
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (serverUrl.includes("127.0.0.1") || serverUrl.includes("localhost")) {
                        setServerUrl("http://192.168.1.100:8000");
                      }
                    }}
                    className={`rounded-md px-2.5 py-1 font-medium transition-all ${
                      !serverUrl.includes("127.0.0.1") && !serverUrl.includes("localhost")
                        ? "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300 font-bold"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300"
                    }`}
                  >
                    🌐 Remote GPU Server
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                  Server Base URL (Summertime-server)
                </label>
                <input
                  type="text"
                  value={serverUrl}
                  onChange={(e) => setServerUrl(e.target.value)}
                  placeholder="http://192.168.1.100:8000"
                  className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                />
                <p className="mt-1 text-[11px] text-slate-400">
                  Decoupled GPU server address. Point this to your GPU host or cluster over LAN / VPN.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                  Client API Key (Bearer Token)
                </label>
                <div className="relative">
                  <input
                    type={showKey ? "text" : "password"}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={
                      status?.api_key_set
                        ? `Configured (${status.masked_key}) — leave blank to keep unchanged`
                        : "wb_live_..."
                    }
                    className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 pr-10 text-sm text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-3 top-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                  >
                    {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                <p className="mt-1 text-[11px] text-slate-400">
                  Generated on your GPU server via{" "}
                  <code className="rounded bg-slate-100 px-1 dark:bg-slate-800 font-mono text-[10px]">
                    workbench admin export-client
                  </code>
                </p>
              </div>

              <div className="pt-2">
                <button
                  type="button"
                  onClick={handleTestConnection}
                  disabled={loading}
                  className="inline-flex items-center gap-2 rounded-xl bg-slate-100 px-4 py-2.5 text-xs font-bold text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 transition-all"
                >
                  {loading ? (
                    <Loader2 size={14} className="animate-spin text-blue-600" />
                  ) : (
                    <Zap size={14} className="text-amber-500" />
                  )}
                  <span>Test Connection & Discover Models</span>
                </button>
              </div>

              {testResult && (
                <div
                  className={`rounded-xl border p-3.5 text-xs animate-in fade-in duration-200 ${
                    testResult.ok
                      ? "border-emerald-200 bg-emerald-50/70 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200"
                      : "border-rose-200 bg-rose-50/70 text-rose-900 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-200"
                  }`}
                >
                  <div className="flex items-start gap-2.5">
                    {testResult.ok ? (
                      <CheckCircle2 size={16} className="text-emerald-600 shrink-0 mt-0.5" />
                    ) : (
                      <AlertCircle size={16} className="text-rose-600 shrink-0 mt-0.5" />
                    )}
                    <div className="space-y-1">
                      <p className="font-semibold">{testResult.message}</p>
                      {testResult.models && testResult.models.length > 0 && (
                        <div className="flex flex-wrap gap-1 pt-1">
                          {testResult.models.map((m) => (
                            <span
                              key={m}
                              className="rounded bg-emerald-200/60 dark:bg-emerald-800/60 px-1.5 py-0.5 text-[10px] font-mono font-bold"
                            >
                              {m}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: CONTEXT WINDOW (1-CLICK GPU OPTIMIZER) */}
          {activeTab === "context" && (
            <div className="space-y-4">
              <div>
                <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">
                  GPU VRAM & Context Window Presets
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Select your machine's GPU profile with one click to optimize KV cache allocation and prevent memory stalls:
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {CONTEXT_CARDS.map((card) => {
                  const Icon = card.icon;
                  const isSelected = selectedTokens === card.tokens;
                  return (
                    <button
                      key={card.id}
                      type="button"
                      onClick={() => setSelectedTokens(card.tokens)}
                      className={`relative flex flex-col text-left rounded-xl border p-4 transition-all ${
                        isSelected
                          ? "border-blue-600 bg-blue-50/50 shadow-md ring-2 ring-blue-500/20 dark:border-blue-400 dark:bg-blue-950/30"
                          : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:hover:bg-slate-800/60"
                      }`}
                    >
                      {card.recommended && (
                        <span className="absolute top-3 right-3 rounded-full bg-blue-100 text-blue-700 px-2 py-0.5 text-[10px] font-bold dark:bg-blue-950 dark:text-blue-300">
                          Recommended
                        </span>
                      )}
                      <div className="flex items-center gap-2 mb-1.5">
                        <div className={`p-1.5 rounded-lg border ${card.color}`}>
                          <Icon size={16} />
                        </div>
                        <div>
                          <span className="text-sm font-bold text-slate-900 dark:text-slate-100">
                            {card.label}
                          </span>
                          <span className="ml-2 font-mono text-xs font-semibold text-slate-500">
                            {card.tokens.toLocaleString()} tokens
                          </span>
                        </div>
                      </div>
                      <div className="mt-1 flex items-center gap-2 text-[11px] font-semibold text-slate-700 dark:text-slate-300">
                        <span className="text-blue-600 dark:text-blue-400">{card.vram}</span>
                        <span>•</span>
                        <span>{card.target}</span>
                      </div>
                      <p className="mt-1.5 text-[11px] text-slate-500 dark:text-slate-400 leading-snug">
                        {card.desc}
                      </p>
                      {isSelected && (
                        <div className="mt-3 flex items-center gap-1 text-[11px] font-bold text-blue-600 dark:text-blue-400">
                          <Check size={13} />
                          <span>Active Preset</span>
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>

              <div className="rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800 p-3.5 text-xs">
                <span className="font-semibold text-slate-800 dark:text-slate-200">
                  Custom Context Length:
                </span>
                <div className="mt-2 flex items-center gap-3">
                  <input
                    type="range"
                    min={2048}
                    max={65536}
                    step={2048}
                    value={selectedTokens}
                    onChange={(e) => setSelectedTokens(Number(e.target.value))}
                    className="flex-1 accent-blue-600"
                  />
                  <span className="font-mono font-bold text-slate-900 dark:text-slate-100 min-w-[70px] text-right">
                    {selectedTokens.toLocaleString()} t
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: KNOWLEDGE VAULT & RAG */}
          {activeTab === "rag" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">
                    Obsidian Knowledge Vault (RAG)
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Index notes, PDFs, and internal research dossiers into local hybrid search.
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={ragEnabled}
                    onChange={(e) => setRagEnabled(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                </label>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                  Vault Folder Path
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={vaultPath}
                    onChange={(e) => setVaultPath(e.target.value)}
                    placeholder="./MyVault"
                    className="flex-1 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                  />
                  <button
                    type="button"
                    onClick={handleReindexVault}
                    disabled={reindexing}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-xs font-bold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 transition-all shadow-sm"
                  >
                    {reindexing ? (
                      <Loader2 size={14} className="animate-spin text-blue-600" />
                    ) : (
                      <RefreshCw size={14} className="text-slate-500" />
                    )}
                    <span>Reindex Vault</span>
                  </button>
                </div>
                <p className="mt-1 text-[11px] text-slate-400">
                  Default: <code className="font-mono">./MyVault</code>. Synchronizes bidirectionally with Obsidian notes.
                </p>
              </div>

              {status && (
                <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4 dark:border-slate-800 dark:bg-slate-800/30 text-xs space-y-1">
                  <div className="flex items-center justify-between text-slate-700 dark:text-slate-300">
                    <span className="font-medium">Indexed Documents in Vault:</span>
                    <span className="font-mono font-bold text-blue-600 dark:text-blue-400">
                      {status.vault_docs_count} file(s)
                    </span>
                  </div>
                </div>
              )}

              {reindexMsg && (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-3 text-xs text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200 font-semibold animate-in fade-in duration-200">
                  {reindexMsg}
                </div>
              )}
            </div>
          )}

          {/* TAB 4: ENTERPRISE ARTIFACTORY */}
          {activeTab === "artifactory" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">
                    Internal JFrog / Enterprise Artifactory
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Optional secure model distribution and deliverable synchronization layer.
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={enableArtifactory}
                    onChange={(e) => setEnableArtifactory(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                </label>
              </div>

              {enableArtifactory && (
                <div className="space-y-3 animate-in fade-in duration-150">
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                      Artifactory URL
                    </label>
                    <input
                      type="text"
                      value={artifactoryUrl}
                      onChange={(e) => setArtifactoryUrl(e.target.value)}
                      placeholder="http://artifactory.internal/artifactory"
                      className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                        Repository Name
                      </label>
                      <input
                        type="text"
                        value={artifactoryRepo}
                        onChange={(e) => setArtifactoryRepo(e.target.value)}
                        placeholder="models"
                        className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                        Service Username
                      </label>
                      <input
                        type="text"
                        value={artifactoryUser}
                        onChange={(e) => setArtifactoryUser(e.target.value)}
                        placeholder="service-account"
                        className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                      Access Token / Secret
                    </label>
                    <input
                      type="password"
                      value={artifactoryToken}
                      onChange={(e) => setArtifactoryToken(e.target.value)}
                      placeholder="cmVwb3MtYWNjZXNzLXRva2Vu..."
                      className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                    />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/60 px-6 py-4 dark:border-slate-800 dark:bg-slate-900/60">
          <div className="text-[11px] text-slate-500">
            Changes are saved locally to <code className="font-mono text-[10px]">.env</code> &{" "}
            <code className="font-mono text-[10px]">config.yaml</code>.
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 transition-all shadow-sm"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSaveSettings}
              disabled={saving}
              className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-2 text-xs font-bold text-white shadow hover:bg-blue-700 disabled:opacity-50 transition-all"
            >
              {saving ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Check size={14} />
              )}
              <span>Save & Apply Settings</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
