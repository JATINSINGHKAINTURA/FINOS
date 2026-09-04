import { useEffect, useRef, useState } from "react";
import { chatHistory, chatSend, type ChatMsg } from "../api";

const KEY = "finos-chat-sid";

export default function Chat() {
  const [sid, setSid] = useState<string | null>(() => localStorage.getItem(KEY));
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [sugg, setSugg] = useState<string[]>(["List cases", "Explain case 1042", "How do approvals work?"]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!sid) return;
    chatHistory(sid).then((h) => setMsgs(h.messages)).catch(() => {
      localStorage.removeItem(KEY); setSid(null);
    });
  }, [sid]);

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);

  const send = async (text: string) => {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true); setError(""); setInput("");
    setMsgs((m) => [...m, { role: "user", content: t }]);
    try {
      const r = await chatSend(t, sid);
      setSid(r.session_id);
      localStorage.setItem(KEY, r.session_id);
      setMsgs((m) => [...m, { role: "assistant", content: r.reply }]);
      setSugg(r.suggestions);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  };

  const fresh = () => {
    localStorage.removeItem(KEY); setSid(null); setMsgs([]);
    setSugg(["List cases", "Explain case 1042", "How do approvals work?"]);
  };

  return (
    <div className="chatwrap fade-in">
      <div className="chathead">
        <div>
          <h1>Assistant</h1>
          <div className="muted">Read-only, grounded in verified case data. For actions, use a case page or Guidebot.</div>
        </div>
        <button className="btn ghost" onClick={fresh}>New chat</button>
      </div>
      {error && <div className="banner error">{error}</div>}
      <div className="chatlog">
        {msgs.length === 0 && (
          <div className="empty">Ask about cases, payment states, approvals, or webhooks.</div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble">{m.content}</div>
          </div>
        ))}
        {busy && <div className="msg assistant"><div className="bubble"><span className="dots" /></div></div>}
        <div ref={bottom} />
      </div>
      <div className="chips">
        {sugg.map((s) => (
          <button key={s} className="chip" disabled={busy} onClick={() => send(s)}>{s}</button>
        ))}
      </div>
      <form className="chatinput" onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <input value={input} onChange={(e) => setInput(e.target.value)}
               placeholder="Ask about FINOS…" maxLength={2000} disabled={busy} />
        <button className="btn primary" disabled={busy || !input.trim()}>Send</button>
      </form>
    </div>
  );
}
