import { useEffect, useState } from "react";
import { auditList, listCases, type CaseSummary } from "../api";
import { CountUp, Reveal } from "../motion";
import { PipelineStrip } from "./Pipeline";

const KIND_LABEL: Record<string, string> = {
  ambiguous: "Ambiguous payment",
  duplicate: "Duplicate payment",
  settlement: "Settlement anomaly",
};

function Skeletons() {
  return (
    <div className="grid" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <div key={i} className="skel-card">
          <div className="skel skel-line" style={{ width: "38%" }} />
          <div className="skel skel-line" style={{ width: "82%", height: 17 }} />
          <div className="skel skel-line" style={{ width: "55%" }} />
        </div>
      ))}
    </div>
  );
}

export default function Dashboard({ onOpen, onAssistant, refreshKey }: {
  onOpen: (no: number) => void; onAssistant: () => void; refreshKey: number;
}) {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [audits, setAudits] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    listCases().then(setCases).catch((e) => setError(e.message));
    auditList(200).then((r) => setAudits(r.length)).catch(() => {});
  }, [refreshKey]);

  if (error) return <div className="banner error" role="alert">{error}</div>;
  if (!cases) return (<>
    <div className="hero"><div className="skel skel-line" style={{ width: "30%" }} />
      <div className="skel skel-line" style={{ width: "70%", height: 22 }} />
      <div className="skel skel-line" style={{ width: "50%" }} /></div>
    <Skeletons />
  </>);

  const open = cases.filter((c) => c.status === "open").length;
  const resolved = cases.filter((c) => c.status === "resolved").length;
  const firstOpen = cases.find((c) => c.status === "open");

  return (
    <>
      <section className="hero" aria-label="FINOS introduction">
        <div className="orb" aria-hidden="true" />
        <Reveal><span className="eyebrow">Payment-state intelligence</span></Reveal>
        <Reveal delay={70}>
          <h1>Every payment,<br />accounted for.</h1>
        </Reveal>
        <Reveal delay={140}>
          <p className="lede">
            FINOS reconstructs payment truth from verified events, investigates exceptions
            with AI, and executes only approved actions — every step audited.
          </p>
        </Reveal>
        <Reveal delay={210}>
          <div className="hero-cta">
            {firstOpen && (
              <button className="btn accent" onClick={() => onOpen(firstOpen.case_no)}>
                Review Case #{firstOpen.case_no}
              </button>
            )}
            <button className="btn ghost" onClick={onAssistant}>Ask the Assistant</button>
            <a className="btn ghost" href="#case-grid">All cases ↓</a>
          </div>
        </Reveal>
        <Reveal delay={280}>
          <div className="hero-stats">
            <div className="stat"><b><CountUp to={open} /></b><span>Open cases</span></div>
            <div className="stat"><b><CountUp to={resolved} /></b><span>Resolved</span></div>
            <div className="stat"><b><CountUp to={audits} /></b><span>Audit events</span></div>
            <div className="stat"><b>5</b><span>Pipeline stages</span></div>
          </div>
        </Reveal>
        <Reveal delay={340}>
          <div className="hero-pipe"><PipelineStrip /></div>
        </Reveal>
      </section>

      <div className="section-head" id="case-grid">
        <h2>Cases</h2>
        <span className="muted" style={{ fontSize: 13 }}>{cases.length} total</span>
      </div>
      <div className="grid">
        {cases.map((c, i) => (
          <Reveal key={c.case_no} delay={Math.min(i, 5) * 80}>
            <button className="card" style={{ width: "100%", height: "100%" }} onClick={() => onOpen(c.case_no)}>
              <div className="card-top">
                <span className="case-no">Case #{c.case_no}</span>
                <span className={`pill status-${c.status}`}>{c.status.replace(/_/g, " ")}</span>
              </div>
              <div className="card-title">{c.title}</div>
              <div className="card-sub">{KIND_LABEL[c.kind] ?? c.kind}{c.order_id ? ` · ${c.order_id}` : ""}</div>
              <div className="card-foot"><span className="link">Open investigation <span className="arr">→</span></span></div>
            </button>
          </Reveal>
        ))}
      </div>
    </>
  );
}
