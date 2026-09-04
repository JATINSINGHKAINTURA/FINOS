import { Suspense, lazy, useState } from "react";
import { PipelineStrip } from "./components/Pipeline";
import { resetDemo } from "./api";

const Dashboard = lazy(() => import("./components/Dashboard"));
const CaseView = lazy(() => import("./components/CaseView"));
const Chat = lazy(() => import("./components/Chat"));
const Guidebots = lazy(() => import("./components/Guidebots"));
const AuditView = lazy(() => import("./components/AuditView"));

type Tab = "cases" | "assistant" | "guidebots" | "audit";
const TABS: { id: Tab; label: string }[] = [
  { id: "cases", label: "Cases" },
  { id: "assistant", label: "Assistant" },
  { id: "guidebots", label: "Guidebots" },
  { id: "audit", label: "Audit" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("cases");
  const [caseNo, setCaseNo] = useState<number | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const go = (t: Tab) => { setTab(t); if (t !== "cases") setCaseNo(null); };
  const reset = async () => {
    if (!confirm("Reset the demo to its three seeded cases?")) return;
    await resetDemo();
    setCaseNo(null); setTab("cases");
    setRefreshKey((k) => k + 1);
  };

  return (
    <div className="shell">
      <header className="top">
        <div className="brand" onClick={() => go("cases")}>
          <span className="logo">◈</span>
          <span><b>FINOS</b> <span className="muted">· payment-state intelligence</span></span>
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t.id} className={`tab ${tab === t.id ? "active" : ""}`} onClick={() => go(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
        <button className="btn ghost" onClick={reset}>Reset demo</button>
      </header>
      <main key={`${tab}-${caseNo ?? "dash"}-${refreshKey}`}>
        <Suspense fallback={<div className="loading"><span className="dots" />Loading…</div>}>
          {tab === "cases" && caseNo === null && (
            <>
              <PipelineStrip />
              <h1>Cases</h1>
              <Dashboard onOpen={setCaseNo} refreshKey={refreshKey} />
            </>
          )}
          {tab === "cases" && caseNo !== null && (
            <CaseView no={caseNo} onBack={() => { setCaseNo(null); setRefreshKey((k) => k + 1); }} />
          )}
          {tab === "assistant" && <Chat />}
          {tab === "guidebots" && <Guidebots />}
          {tab === "audit" && <AuditView />}
        </Suspense>
      </main>
      <footer className="foot muted">Facts → Rules/State → AI Reasoning → Policy Gate → Approved Action · every step audited</footer>
    </div>
  );
}
