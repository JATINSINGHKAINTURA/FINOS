import { useEffect, useState } from "react";
import { health } from "../api";

export function PipelineStrip() {
  const [dry, setDry] = useState<boolean | null>(null);
  useEffect(() => { health().then((h) => setDry(h.dry_run)).catch(() => {}); }, []);
  const steps = ["Facts", "Rules / State", "AI Reasoning", "Policy Gate", "Approved Action"];
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
