import { useState } from "react";
import Dashboard, { PipelineStrip } from "./components/Dashboard";
import CaseView from "./components/CaseView";
import { resetDemo } from "./api";

export default function App() {
  const [route, setRoute] = useState<{ view: "dash" } | { view: "case"; no: number }>({ view: "dash" });
  const [refreshKey, setRefreshKey] = useState(0);

  const reset = async () => {
    if (!confirm("Reset the demo to its three seeded cases?")) return;
    await resetDemo();
    setRoute({ view: "dash" });
    setRefreshKey((k) => k + 1);
  };

  return (
    <div className="shell">
      <header className="top">
        <div className="brand" onClick={() => setRoute({ view: "dash" })}>
          <span className="logo">◈</span>
          <span><b>FINOS</b> <span className="muted">· payment-state intelligence</span></span>
        </div>
        <button className="btn ghost" onClick={reset}>Reset demo</button>
      </header>
      <main key={route.view === "case" ? route.no : "dash"}>
        {route.view === "dash" ? (
          <>
            <PipelineStrip />
            <h1>Cases</h1>
            <Dashboard onOpen={(no) => setRoute({ view: "case", no })} refreshKey={refreshKey} />
          </>
        ) : (
          <CaseView no={route.no} onBack={() => { setRoute({ view: "dash" }); setRefreshKey((k) => k + 1); }} />
        )}
      </main>
      <footer className="foot muted">Facts → Rules/State → AI Reasoning → Policy Gate → Approved Action · every step audited</footer>
    </div>
  );
}
