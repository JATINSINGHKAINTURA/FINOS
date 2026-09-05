import { useEffect, useState } from "react";
import { auditList } from "../api";

export default function AuditView() {
  const [rows, setRows] = useState<Awaited<ReturnType<typeof auditList>> | null>(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => { auditList().then(setRows).catch((e) => setError(e.message)); }, []);

  if (error) return <div className="banner error" role="alert">{error}</div>;
  if (!rows) return (
    <div className="panel" aria-hidden="true">
      <div className="skel skel-line" style={{ width: "30%" }} />
      <div className="skel skel-line" /><div className="skel skel-line" style={{ width: "85%" }} />
      <div className="skel skel-line" style={{ width: "70%" }} /><div className="skel skel-line" style={{ width: "90%" }} />
    </div>
  );

  const f = q.trim().toLowerCase();
  const shown = f
    ? rows.filter((r) => `${r.audit_id} ${r.actor} ${r.event} ${JSON.stringify(r.details)}`.toLowerCase().includes(f))
    : rows;

  return (
    <div>
      <h1>Audit trail</h1>
      <div className="muted" style={{ marginBottom: 12 }}>
        Every detection, decision, approval, and execution — newest first.
      </div>
      <input className="filter" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter audit entries…" />
      {shown.length === 0 && <div className="empty">No audit entries match.</div>}
      <div className="panel">
        <table className="kv audit-table">
          <tbody>
            {shown.map((r) => (
              <tr key={r.audit_id}>
                <td className="mono">{r.audit_id}</td>
                <td><b>{r.event}</b><div className="muted" style={{ fontSize: 12 }}>{r.actor}</div></td>
                <td className="muted" style={{ fontSize: 12 }}>
                  {r.created_at ? new Date(r.created_at).toLocaleString() : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
