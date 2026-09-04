import { useEffect, useState } from "react";
import { health, listCases, type CaseSummary } from "../api";
import { rs } from "../api";

const KIND_LABEL: Record<string, string> = {
  ambiguous: "Ambiguous payment",
  duplicate: "Duplicate payment",
  settlement: "Settlement anomaly",
};

export default function Dashboard({ onOpen, refreshKey }: { onOpen: (no: number) => void; refreshKey: number }) {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    listCases().then(setCases).catch((e) => setError(e.message));
  }, [refreshKey]);

  if (error) return <div className="banner error">{error}</div>;
  if (!cases) return <div className="loading"><span className="dots" />Loading cases…</div>;

  return (
    <div className="grid">
      {cases.map((c) => (
        <button key={c.case_no} className="card hover-lift slide-up" onClick={() => onOpen(c.case_no)}>
          <div className="card-top">
            <span className="case-no">Case #{c.case_no}</span>
            <span className={`pill status-${c.status}`}>{c.status.replace(/_/g, " ")}</span>
          </div>
          <div className="card-title">{c.title}</div>
          <div className="card-sub">{KIND_LABEL[c.kind] ?? c.kind}{c.order_id ? ` · ${c.order_id}` : ""}</div>
          <div className="card-foot"><span className="link">Open investigation →</span></div>
        </button>
      ))}
    </div>
  );
}

export function PipelineStrip() {
  const [dry, setDry] = useState<boolean | null>(null);
  useEffect(() => { health().then((h) => setDry(h.dry_run)).catch(() => {}); }, []);
  const steps = ["Facts", "Rules / State", "AI Reasoning", "Policy Gate", "Approved Action"];
  void rs;
  return (
    <div className="pipeline fade-in" title="FINOS architecture: AI explains, never invents financial truth.">
      {steps.map((s, i) => (
        <span key={s} className="pipe-step">
          {i > 0 && <span className="pipe-arrow">→</span>}{s}
        </span>
      ))}
      {dry !== null && <span className={`pill ${dry ? "dry" : "live"}`}>{dry ? "DRY-RUN" : "LIVE"}</span>}
    </div>
  );
}
