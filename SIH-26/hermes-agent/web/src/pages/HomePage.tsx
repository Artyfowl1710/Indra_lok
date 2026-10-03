import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ArrowUpRight, Clock3, FileText, FolderOpen, Layers3, MessageSquare, ShieldCheck } from "lucide-react";
import { api, type PaginatedSessions, type StatusResponse } from "@/lib/api";
import { useUiPhrase } from "@/i18n/UiTextLocalizer";

export default function HomePage() {
  const title = useUiPhrase("What would you like INDRA to do?");
  const [titleBeforeIndra, ...titleAfterIndra] = (title.includes("INDRA") ? title : "What would you like INDRA to do?").split("INDRA");
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [sessions, setSessions] = useState<PaginatedSessions | null>(null);

  useEffect(() => {
    let active = true;
    void api.getStatus().then(value => { if (active) setStatus(value); }).catch(() => {});
    void api.getSessions(3, 0, undefined, "recent").then(value => { if (active) setSessions(value); }).catch(() => {});
    return () => { active = false; };
  }, []);

  return (
    <main className="indra-home">
      <div className="indra-home-eyebrow"><span className="indra-home-dot" /> SOVEREIGN AI INTELLIGENCE WORKBENCH</div>
      <section className="indra-home-hero" aria-labelledby="indra-home-title">
        <div>
          <p className="indra-home-kicker">Your workspace, ready when you are.</p>
          <h1 id="indra-home-title">{titleBeforeIndra}<span>INDRA</span>{titleAfterIndra.join("INDRA")}</h1>
          <p className="indra-home-intro">Ask a question, analyze a document, create something new, or give INDRA a complex task.</p>
        </div>
        <Link className="indra-home-composer" to="/chat" aria-label="Open Command Center and ask INDRA">
          <span>Ask INDRA anything...</span>
          <span className="indra-home-composer-footer"><span><FileText size={17} /> Files and images <span className="indra-home-divider">·</span> <Layers3 size={17} /> Model selection in workspace</span><span className="indra-home-send"><ArrowUpRight size={23} /></span></span>
        </Link>
        <p className="indra-home-hint">Your request opens the live Command Center, where you can attach files and follow execution.</p>
      </section>

      <div className="indra-home-grid">
        <section className="indra-home-panel" aria-labelledby="recent-heading">
          <div className="indra-home-section-heading"><div><span>CONTINUE YOUR WORK</span><h2 id="recent-heading">Recent tasks</h2></div><Link to="/sessions">View all <ArrowUpRight size={16} /></Link></div>
          {sessions?.sessions.length ? <div className="indra-home-task-list">{sessions.sessions.map(session => <Link key={session.id} to={`/chat?resume=${encodeURIComponent(session.id)}`} className="indra-home-task"><span className="indra-home-task-icon"><MessageSquare size={20} /></span><span><strong translate={session.title || session.preview ? "no" : undefined}>{session.title || session.preview || "Untitled session"}</strong><small>{session.model || "Model unavailable"} · {session.message_count} messages</small></span><ArrowUpRight size={18} /></Link>)}</div> : <div className="indra-home-empty"><Clock3 size={22} /><p>{sessions ? "No recent tasks yet. Start with a request above." : "Recent tasks unavailable."}</p></div>}
        </section>
        <section className="indra-home-panel indra-home-runtime" aria-labelledby="runtime-heading">
          <div className="indra-home-section-heading"><div><span>WORKSPACE HEALTH</span><h2 id="runtime-heading">Runtime</h2></div><Link to="/system">Details <ArrowUpRight size={16} /></Link></div>
          <div className="indra-home-runtime-state"><span className={status?.gateway_running ? "indra-home-status-dot ready" : "indra-home-status-dot"} /><strong>{status ? (status.gateway_running ? "Ready to work" : "Runtime stopped") : "Status unavailable"}</strong></div>
          <p>{status?.gateway_running ? "INDRA is available for new tasks." : "Open runtime details for connection and service information."}</p>
          <div className="indra-home-runtime-meta"><span>Active sessions</span><strong>{status ? status.active_sessions : "—"}</strong></div>
        </section>
      </div>
      <div className="indra-home-links"><Link to="/files"><FolderOpen size={19} /> Knowledge <ArrowUpRight size={16} /></Link><Link to="/models"><Layers3 size={19} /> Models <ArrowUpRight size={16} /></Link><Link to="/logs"><ShieldCheck size={19} /> Audit <ArrowUpRight size={16} /></Link></div>
    </main>
  );
}
