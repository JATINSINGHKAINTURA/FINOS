import { useEffect, useRef, useState } from "react";
import { guideHistory, guideSend, guidebots, type ChatMsg, type GuidebotInfo, type ToolResult } from "../api";

function ToolCard({ t }: { t: ToolResult }) {
  const label: Record<string, string> = {
    get_cases: "Looked up cases", get_case: "Read case facts", investigate: "Ran investigation",
    approve: "Approval", execute: "Execution", test_webhook: "Test event",
  };
  const bad = t.blocked || t.ok === false;
  return (
    <div className={`toolcard ${bad ? "warn" : "ok"}`}>
      <span className="mono">{bad ? "◌" : "●"} {label[t.tool] ?? t.tool}</span>
      {t.blocked && typeof t.message === "string" && <span> — {t.message}</span>}
      {t.ok && t.tool === "execute" && typeof t.data === "object" && t.data !== null && (
        <span> — {String((t.data as { status?: string }).status ?? "")}</span>
      )}
    </div>
  );
}

export default function Guidebots() {
  const [bots, setBots] = useState<GuidebotInfo[] | null>(null);
  const [active, setActive] = useState<GuidebotInfo | null>(null);
  const [sid, setSid] = useState<string | null>(null);
  const [step, setStep] = useState(0);
  const [done, setDone] = useState(false);
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [cards, setCards] = useState<ToolResult[][]>([]);
  const [sugg, setSugg] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => { guidebots().then(setBots).catch((e) => setError(e.message)); }, []);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);

  const pick = (b: GuidebotInfo) => {
    const saved = localStorage.getItem(`finos-guide-${b.id}`);
    setActive(b); setMsgs([]); setCards([]); setSugg([]); setDone(false); setError("");
    if (saved) {
      setSid(saved);
      guideHistory(b.id, saved).then((h) => {
        setMsgs(h.messages); setStep(h.step);
      }).catch(() => { localStorage.removeItem(`finos-guide-${b.id}`); setSid(null); setStep(0); });
    } else { setSid(null); setStep(0); }
  };

  const send = async (text: string) => {
    const t = text.trim();
    if (!t || busy || !active) return;
    setBusy(true); setError(""); setInput("");
    setMsgs((m) => [...m, { role: "user", content: t }]);
    setCards((c) => [...c, []]);
    try {
      const r = await guideSend(active.id, t, sid);
      setSid(r.session_id);
      localStorage.setItem(`finos-guide-${active.id}`, r.session_id);
      setMsgs((m) => [...m, { role: "assistant", content: r.reply }]);
      setCards((c) => { const n = [...c]; n[n.length - 1] = r.tool_results ?? []; return n; });
      setSugg(r.suggestions); setStep(r.step); setDone(r.done);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setMsgs((m) => m.slice(0, -1));
      setCards((c) => c.slice(0, -1));
      setInput(t);
    }
    setBusy(false);
  };

  const restart = () => {
    if (!active) return;
    localStorage.removeItem(`finos-guide-${active.id}`);
    setSid(null); setMsgs([]); setCards([]); setStep(0); setDone(false); setSugg([]);
  };

  if (error && !bots) return <div className="banner error">{error}</div>;
  if (!bots) return <div className="loading"><span className="typing" aria-hidden="true"><i /><i /><i /></span></div>;

  return (
    <div>
      <h1>Guidebots</h1>
      <div className="muted" style={{ marginBottom: 14 }}>
        Task-oriented guides. They act only through governed tools — and never claim an action they didn't perform.
      </div>
      <div className="botgrid">
        {bots.map((b) => (
          <button key={b.id} className={`card ${active?.id === b.id ? "selected" : ""}`} onClick={() => pick(b)}
            aria-pressed={active?.id === b.id}>
            <div className="card-title">{b.name}</div>
            <div className="card-sub">{b.tagline}</div>
            <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>{b.description}</div>
          </button>
        ))}
      </div>
      {active && (
        <div className="panel guidechat">
          <div className="steps" aria-label="Guide progress">
            {active.steps.map((s, i) => (
              <div key={s} className={`step ${i <= step || done ? "done" : ""}${i === step && !done ? " current" : ""}`}>
                <span className="dot">{i <= step || done ? "✓" : i + 1}</span>{s}
              </div>
            ))}
          </div>
          {error && <div className="banner error" role="alert">{error}</div>}
          <div className="chatlog" role="log" aria-live="polite" aria-label={`${active.name} conversation`}>
            {msgs.length === 0 && <div className="empty"><span className="big" aria-hidden="true">✦</span>Say hello to start “{active.name}”.</div>}
            {msgs.map((m, i) => {
              const ai = assistantIndex(msgs, i);
              const tc = m.role === "assistant" ? cards[ai] ?? [] : [];
              return (
                <div key={i}>
                  <div className={`msg ${m.role}`}><div className="bubble">{m.content}</div></div>
                  {tc.length > 0 && (
                    <div className="toolcards">
                      {tc.map((t, k) => <ToolCard key={k} t={t} />)}
                    </div>
                  )}
                </div>
              );
            })}
            {busy && <div className="msg assistant"><div className="bubble"><span className="typing" aria-label={`${active.name} is working`}><i /><i /><i /></span></div></div>}
            <div ref={bottom} />
          </div>
          <div className="chips">
            {sugg.map((s) => (
              <button key={s} className="chip" disabled={busy} onClick={() => send(s)}>{s}</button>
            ))}
          </div>
          <form className="chatinput" onSubmit={(e) => { e.preventDefault(); send(input); }}>
            <input value={input} onChange={(e) => setInput(e.target.value)}
                   placeholder={`Reply to ${active.name}…`} maxLength={2000} disabled={busy || done} />
            <button className="btn primary" disabled={busy || done || !input.trim()}>Send</button>
            <button type="button" className="btn ghost" onClick={restart}>Restart</button>
          </form>
        </div>
      )}
    </div>
  );
}

function assistantIndex(msgs: ChatMsg[], i: number) {
  return msgs.slice(0, i + 1).filter((x) => x.role === "assistant").length - 1;
}
