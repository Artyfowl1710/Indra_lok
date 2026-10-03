import { useCallback, useEffect, useState } from "react";
import { ArrowUpRight, CheckCircle2, Laptop, Package, RefreshCw, ShieldCheck, Terminal } from "lucide-react";
import { Link } from "react-router";
import { api, type StatusResponse, type SystemStats } from "@/lib/api";
import { IndraMetric, IndraPanel, IndraState } from "@/components/IndraSurface";

export default function SandboxPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [activeBackend, setActiveBackend] = useState<string>("local");
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);
  const [feedback, setFeedback] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [error, setError] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(false);
    const [runtime, host, tb] = await Promise.allSettled([
      api.getStatus(),
      api.getSystemStats(),
      api.getTerminalBackends(),
    ]);
    if (runtime.status === "fulfilled") setStatus(runtime.value);
    if (host.status === "fulfilled") setStats(host.value);
    if (tb.status === "fulfilled" && tb.value) {
      setActiveBackend(tb.value.active || "local");
    }
    if (runtime.status === "rejected" && host.status === "rejected" && tb.status === "rejected") {
      setError(true);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleSwitch = async (target: "local" | "docker") => {
    if (target === activeBackend || switching) return;
    setSwitching(true);
    setFeedback(null);
    try {
      const res = await api.selectTerminalBackend(target);
      if (res.ok) {
        setActiveBackend(target);
        setFeedback({
          message: `Switched execution backend to ${target === "docker" ? "Docker Sandbox" : "Local Host"}. Configuration updated in 1 click!`,
          type: "success",
        });
        await refresh();
      } else {
        setFeedback({ message: "Failed to switch backend.", type: "error" });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setFeedback({ message: `Error switching backend: ${msg}`, type: "error" });
    } finally {
      setSwitching(false);
    }
  };

  const isLocalActive = activeBackend === "local";
  const isDockerActive = activeBackend === "docker";

  return (
    <main className="stitch-page indra-product-page">
      <div className="indra-page-heading">
        <div>
          <span>EXECUTION ENVIRONMENT & SANDBOX</span>
          <h1>Work within your perimeter.</h1>
          <p>
            Choose where INDRA executes commands, code, and document tools. Switch between Local Host and Docker Sandbox in one click without reconfiguring skills or paths.
          </p>
        </div>
        <button
          type="button"
          className="indra-icon-action"
          onClick={() => void refresh()}
          disabled={loading || switching}
          aria-label="Refresh sandbox status"
        >
          <RefreshCw size={18} className={loading || switching ? "animate-spin" : ""} />
        </button>
      </div>

      {feedback && (
        <div
          style={{
            padding: "12px 18px",
            marginBottom: "20px",
            borderRadius: "14px",
            background: feedback.type === "success" ? "rgba(77, 128, 99, 0.12)" : "rgba(220, 53, 69, 0.12)",
            border: feedback.type === "success" ? "1px solid #4D8063" : "1px solid #DC3545",
            color: feedback.type === "success" ? "#2B5E41" : "#A71D2A",
            display: "flex",
            alignItems: "center",
            gap: "10px",
            fontWeight: 600,
            fontSize: "14px",
          }}
        >
          <CheckCircle2 size={18} />
          <span>{feedback.message}</span>
        </div>
      )}

      {loading && !status && !stats && <IndraState title="Loading execution environment…" />}

      {error && (
        <IndraState
          title="Environment unavailable"
          description="The runtime endpoints could not be reached."
          tone="error"
          action={
            <button type="button" onClick={() => void refresh()}>
              Try again
            </button>
          }
        />
      )}

      {/* ── 1-CLICK BACKEND SWITCHER ─────────────────────────────── */}
      <IndraPanel
        title="Execution Mode Selector"
        description="One-click toggle between native host processing and containerized Docker isolation."
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
            gap: "18px",
            marginTop: "12px",
          }}
        >
          {/* LOCAL CARD */}
          <div
            style={{
              padding: "20px",
              borderRadius: "18px",
              border: isLocalActive ? "2px solid #39D9EC" : "1px solid #E3E5E1",
              background: isLocalActive ? "rgba(57, 217, 236, 0.05)" : "#FFFFFF",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              gap: "14px",
              transition: "all 0.2s ease",
            }}
          >
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "10px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <span
                    style={{
                      display: "grid",
                      placeItems: "center",
                      width: "38px",
                      height: "38px",
                      borderRadius: "10px",
                      background: isLocalActive ? "#39D9EC" : "#E3E5E1",
                      color: "#181C22",
                    }}
                  >
                    <Laptop size={20} />
                  </span>
                  <strong style={{ fontSize: "16px", color: "#181C22" }}>Local Host (Native)</strong>
                </div>
                {isLocalActive && (
                  <span
                    style={{
                      fontSize: "11px",
                      fontWeight: 800,
                      padding: "4px 10px",
                      borderRadius: "999px",
                      background: "#4D8063",
                      color: "#FFFFFF",
                      letterSpacing: "0.06em",
                      textTransform: "uppercase",
                    }}
                  >
                    Active
                  </span>
                )}
              </div>
              <p style={{ fontSize: "13px", color: "#62676B", lineHeight: "1.5", margin: 0 }}>
                Executes directly on your Windows host machine using local Python, installed libraries (Poppler, reportlab, pypdf, python-pptx), and writes deliverables to <code>./outputs/</code> in your project.
              </p>
            </div>
            <button
              type="button"
              disabled={isLocalActive || switching}
              onClick={() => void handleSwitch("local")}
              style={{
                width: "100%",
                padding: "10px 16px",
                borderRadius: "12px",
                border: isLocalActive ? "1px solid #E3E5E1" : "1px solid #181C22",
                background: isLocalActive ? "#F4F5F2" : "#181C22",
                color: isLocalActive ? "#94989B" : "#FFFFFF",
                fontWeight: 700,
                fontSize: "13px",
                cursor: isLocalActive ? "default" : "pointer",
                transition: "all 0.15s ease",
              }}
            >
              {isLocalActive ? "Currently Active" : switching ? "Switching…" : "Switch to Local Host"}
            </button>
          </div>

          {/* DOCKER CARD */}
          <div
            style={{
              padding: "20px",
              borderRadius: "18px",
              border: isDockerActive ? "2px solid #39D9EC" : "1px solid #E3E5E1",
              background: isDockerActive ? "rgba(57, 217, 236, 0.05)" : "#FFFFFF",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              gap: "14px",
              transition: "all 0.2s ease",
            }}
          >
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "10px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <span
                    style={{
                      display: "grid",
                      placeItems: "center",
                      width: "38px",
                      height: "38px",
                      borderRadius: "10px",
                      background: isDockerActive ? "#39D9EC" : "#E3E5E1",
                      color: "#181C22",
                    }}
                  >
                    <Package size={20} />
                  </span>
                  <strong style={{ fontSize: "16px", color: "#181C22" }}>Docker Sandbox Container</strong>
                </div>
                {isDockerActive && (
                  <span
                    style={{
                      fontSize: "11px",
                      fontWeight: 800,
                      padding: "4px 10px",
                      borderRadius: "999px",
                      background: "#4D8063",
                      color: "#FFFFFF",
                      letterSpacing: "0.06em",
                      textTransform: "uppercase",
                    }}
                  >
                    Active
                  </span>
                )}
              </div>
              <p style={{ fontSize: "13px", color: "#62676B", lineHeight: "1.5", margin: 0 }}>
                Executes inside the isolated <code>indra-documents:1</code> container. The host workspace is automatically bind-mounted to <code>/workspace</code>, keeping your host system protected.
              </p>
            </div>
            <button
              type="button"
              disabled={isDockerActive || switching}
              onClick={() => void handleSwitch("docker")}
              style={{
                width: "100%",
                padding: "10px 16px",
                borderRadius: "12px",
                border: isDockerActive ? "1px solid #E3E5E1" : "1px solid #181C22",
                background: isDockerActive ? "#F4F5F2" : "#181C22",
                color: isDockerActive ? "#94989B" : "#FFFFFF",
                fontWeight: 700,
                fontSize: "13px",
                cursor: isDockerActive ? "default" : "pointer",
                transition: "all 0.15s ease",
              }}
            >
              {isDockerActive ? "Currently Active" : switching ? "Switching…" : "Switch to Docker Sandbox"}
            </button>
          </div>
        </div>
      </IndraPanel>

      {(status || stats) && (
        <div className="indra-metric-grid">
          <IndraPanel title="Runtime Gateway" description="State reported by the active Indra core.">
            <IndraMetric
              label="STATUS"
              value={status ? (status.gateway_running ? "Ready" : "Stopped") : "Unavailable"}
              hint={status?.gateway_state || undefined}
            />
          </IndraPanel>
          <IndraPanel title="Host Process" description="Operating system process status.">
            <IndraMetric
              label="PROCESS"
              value={stats?.process?.pid ? `PID ${stats.process.pid}` : "Unavailable"}
              hint={stats?.hostname || undefined}
            />
          </IndraPanel>
          <IndraPanel title="Active Backend" description="Execution backend in config.yaml.">
            <IndraMetric
              label="BACKEND"
              value={isLocalActive ? "Local Host" : isDockerActive ? "Docker Sandbox" : activeBackend}
              hint={isLocalActive ? "Native Windows Host" : "Container Sandbox"}
            />
          </IndraPanel>
        </div>
      )}

      <IndraPanel
        title="Execute a Task"
        description="The Command Center owns the live execution session, file input, and tool output."
        action={
          <Link className="indra-text-link" to="/chat">
            Open workspace <ArrowUpRight size={16} />
          </Link>
        }
      >
        <div className="indra-feature-row">
          <span>
            <Terminal size={22} />
          </span>
          <div>
            <strong>Run with INDRA</strong>
            <p>
              Ask INDRA to execute code, process a file, or use an installed skill. File deliverables always save to{" "}
              <code>./outputs/</code> regardless of whether Local or Docker mode is selected.
            </p>
          </div>
        </div>
      </IndraPanel>

      <IndraPanel
        className="indra-disclosure"
        title="Seamless Portability"
        description="Unified workspace paths ensure zero friction between Local and Docker modes."
      >
        <div className="indra-feature-row">
          <span>
            <ShieldCheck size={22} />
          </span>
          <div>
            <strong>Zero Re-configuration</strong>
            <p>
              Deliverables and skill helpers use project-relative paths (<code>./outputs/</code>). When switched to Docker, the workspace is automatically mounted so you never need to adjust script paths or settings in 10 different files.
            </p>
          </div>
        </div>
      </IndraPanel>
    </main>
  );
}
