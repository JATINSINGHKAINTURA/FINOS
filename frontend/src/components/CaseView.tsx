import { useCallback, useEffect, useState } from "react";
import { approve, execute, getCase, investigate, rs, type CaseDetail } from "../api";
import { Reveal } from "../motion";

const ACTION_LABEL: Record<string, string> = {
  no_action: "Resolve — no financial action",
  refund: "Refund duplicate payment",
  flag_review: "Flag for finance review",
};

function Steps({ d }: { d: CaseDetail }) {
  const inv = d.decisions.length > 0;
  const appr = d.action != null && ["approved", "executed"].includes(d.action.status);
  const exec = d.action?.status === "executed";
  const steps = [
    { label: "Detected", done: true },
    { label: "Investigated", done: inv },
    { label: "Approved", done: appr },
    { label: "Executed", done: exec },
  ];
  const current = exec ? -1 : steps.findIndex((s) => !s.done);
  return (
    <div className="steps" aria-label="Case progress">
      {steps.map((s, i) => (
        <div key={s.label} className={`step ${s.done ? "done" : ""}${i === current ? " current" : ""}`}
          aria-current={i === current ? "step" : undefined}>
          <span className="dot">{s.done ? "✓" : i + 1}</span>{s.label}
        </div>
      ))}
    </div>
  );
}

function CaseSkeleton() {
  return (
    <div aria-hidden="true">
      <div className="skel skel-line" style={{ width: "12%" }} />
      <div className="skel skel-line" style={{ width: "45%", height: 24 }} />
      <div className="skel skel-line" style={{ width: "70%" }} />
      <div className="cols" style={{ marginTop: 16 }}>
        <div className="skel-card"><div className="skel skel-line" style={{ width: "40%" }} />
          <div className="skel skel-line" /><div className="skel skel-line" style={{ width: "80%" }} />
          <div className="skel skel-line" style={{ width: "60%" }} /></div>
        <div className="skel-card"><div className="skel skel-line" style={{ width: "40%" }} />
          <div className="skel skel-line" style={{ width: "90%" }} />
          <div className="skel skel-line" style={{ width: "50%" }} /></div>
      </div>
    </div>
  );
}

export default function CaseView({ no, onBack }: { no: number; onBack: () => void }) {
  const [d, setD] = useState<CaseDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    try { setD(await getCase(no)); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }, [no]);
  useEffect(() => { load(); }, [load]);

  const run = async (what: "investigate" | "approve" | "execute") => {
    setBusy(what); setError("");
    try {
      if (what === "investigate") await investigate(no);
      if (what === "approve") await approve(no);
      if (what === "execute") await execute(no);
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    setBusy("");
  };

  if (error && !d) return <div className="banner error" role="alert">{error}</div>;
  if (!d) return <CaseSkeleton />;

  const latest = d.decisions[d.decisions.length - 1];
  const st = d.reconstruction?.state;

  const busyBtn = (what: "investigate" | "approve" | "execute", label: string, doing: string) => (
    <button className="btn primary" disabled={busy !== ""} onClick={() => run(what)} aria-busy={busy === what}>
      {busy === what && <span className="spin" aria-hidden="true" />}{busy === what ? doing : label}
    </button>
  );

  return (
    <div className="case" key={no}>
      <button className="back" onClick={onBack}><span aria-hidden="true">←</span> All cases</button>
      <div className="case-head">
        <div>
          <div className="case-no">Payment Case #{d.case.case_no}</div>
          <h2>{latest ? latest.diagnosis : d.case.title}</h2>
          <div className="muted">{d.case.summary}</div>
        </div>
        <span className={`pill status-${d.case.status}`}>{d.case.status.replace(/_/g, " ")}</span>
      </div>

      <Steps d={d} />

      {error && <div className="banner error" role="alert">{error}</div>}

      <div className="cols">
        <div className="col">
          <Reveal as="section" className="panel">
            <h3>Payment timeline</h3>
            {d.reconstruction ? (
              <>
                <div className="facts">
                  <span className="fact">Captured: <b>{String(st?.captured_count ?? 0)}×</b></span>
                  <span className="fact">Total: <b>{rs(st?.captured_total)}</b></span>
                  <span className="fact">Due: <b>{rs(st?.amount_due)}</b></span>
                </div>
                <ol className="timeline">
                  {d.reconstruction.timeline.map((t, i) => (
                    <li key={i}><span className="t">{t.at ? new Date(t.at).toLocaleString() : ""}</span>
                      <b>{t.label}</b><span className="muted">{t.detail}</span></li>
                  ))}
                </ol>
              </>
            ) : null}
            {d.settlement && (
              <table className="kv">
                <tbody>
                  {[["Expected", rs(d.settlement.expected)], ["Actual", rs(d.settlement.actual)],
                    ["Fees", rs(d.settlement.fees)], ["Tax", rs(d.settlement.tax)],
                    ["Reference", String(d.settlement.reference)],
                    ["Unexplained", rs(d.settlement.unexplained)]].map(([k, v]) => (
                    <tr key={k}><td>{k}</td><td><b>{v}</b></td></tr>
                  ))}
                </tbody>
              </table>
            )}
          </Reveal>

          <Reveal as="section" className="panel" delay={90}>
            <h3>Audit trail</h3>
            {d.audit.length === 0 && <div className="muted">No audit entries yet.</div>}
            <ol className="audit">
              {d.audit.map((a) => (
                <li key={a.audit_id}><code>{a.audit_id}</code> <b>{a.event}</b>
                  <span className="muted"> · {a.actor} · {a.created_at ? new Date(a.created_at).toLocaleString() : ""}</span></li>
              ))}
            </ol>
          </Reveal>
        </div>

        <div className="col">
          <Reveal as="section" className="panel" delay={60}>
            <h3>AI diagnosis</h3>
            {!latest && busyBtn("investigate", "Run AI investigation", "Investigating…")}
            {latest && (
              <>
                <p className="diagnosis">“{latest.diagnosis}”</p>
                <ul className="evidence">
                  {latest.evidence.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
                <div className="muted">Reason: {latest.rationale}</div>
                <div className="meta">
                  <span className={`pill conf-${latest.confidence}`}>{latest.confidence} confidence</span>
                  <span className="muted">model: {latest.model}</span>
                </div>
              </>
              )}
          </Reveal>

          {d.action && (
            <Reveal as="section" className="panel" delay={120}>
              <h3>Recommended action</h3>
              <div className="action-kind">{ACTION_LABEL[d.action.kind] ?? d.action.kind}</div>
              <div className="muted mono">Action ID: {d.action.action_id} · status: {d.action.status}</div>
              {d.policy && (
                <ul className="policy">
                  {d.policy.reasons.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              )}
              <div className="row">
                {d.action.status === "proposed" && busyBtn("approve", "Approve", "Approving…")}
                {d.action.status === "approved" && busyBtn("execute", "Execute", "Executing…")}
                {d.action.status === "blocked" && <span className="pill blocked">Blocked by policy</span>}
                {d.action.status === "executed" && <span className="pill executed">✓ Executed</span>}
              </div>
              {d.action.status === "executed" && d.action.result && (
                <div className="result">{String((d.action.result as { outcome?: string }).outcome ?? "")}</div>
              )}
            </Reveal>
          )}
        </div>
      </div>
    </div>
  );
}
