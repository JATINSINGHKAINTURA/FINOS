async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((data as { error?: string }).error || `Request failed (${r.status})`);
  return data as T;
}

export interface CaseSummary {
  case_no: number; kind: string; title: string; summary: string;
  status: string; order_id: string; payment_id: string; created_at: string;
}
export interface Decision {
  id: number; diagnosis: string; evidence: string[]; confidence: string;
  recommended_action: string; rationale: string; model: string; created_at: string;
}
export interface FinAction {
  action_id: string; kind: string; status: string;
  params: Record<string, unknown>; result: Record<string, unknown>; created_at: string;
}
export interface Policy { allowed: boolean; requires_approval: boolean; reasons: string[]; }
export interface CaseDetail {
  case: CaseSummary;
  reconstruction?: {
    state: Record<string, unknown>;
    payments: { payment_id: string; amount: number; status: string; method: string }[];
    timeline: { at: string; label: string; detail: string }[];
  };
  settlement?: Record<string, number | string>;
  decisions: Decision[];
  action: FinAction | null;
  policy?: Policy | null;
  audit: { audit_id: string; actor: string; event: string; details: Record<string, unknown>; created_at: string }[];
}

export const health = () => req<{ ok: boolean; dry_run: boolean }>("GET", "/health");
export const listCases = () => req<CaseSummary[]>("GET", "/api/cases");
export const getCase = (no: number) => req<CaseDetail>("GET", `/api/cases/${no}`);
export const investigate = (no: number) =>
  req<{ decision: Decision; action: FinAction; policy: Policy }>("POST", `/api/cases/${no}/investigate`);
export const approve = (no: number, actor = "judge") =>
  req<{ ok: boolean; verdict: Policy; action: FinAction }>("POST", `/api/cases/${no}/approve`, { actor });
export const execute = (no: number, actor = "judge") =>
  req<{ ok: boolean; result: Record<string, unknown>; action: FinAction }>("POST", `/api/cases/${no}/execute`, { actor });
export const resetDemo = () => req<{ ok: boolean }>("POST", "/api/seed/reset");

export const rs = (paise: number | unknown) =>
  typeof paise === "number" ? "₹" + (paise / 100).toLocaleString("en-IN") : String(paise ?? "—");

export interface ChatMsg { role: string; content: string }
export interface GuidebotInfo {
  id: string; name: string; tagline: string; description: string; steps: string[];
}
export interface ToolResult { tool: string; ok?: boolean; blocked?: boolean; [k: string]: unknown }

export const chatSend = (message: string, session_id?: string | null) =>
  req<{ session_id: string; reply: string; suggestions: string[] }>(
    "POST", "/api/chat", { message, ...(session_id ? { session_id } : {}) });
export const chatHistory = (session_id: string) =>
  req<{ session_id: string; messages: ChatMsg[] }>("GET", `/api/chat/${session_id}`);
export const guidebots = () => req<GuidebotInfo[]>("GET", "/api/guidebots");
export const guideSend = (bot: string, message: string, session_id?: string | null) =>
  req<{ session_id: string; reply: string; suggestions: string[]; tool_results: ToolResult[];
        step: number; done: boolean; bot: GuidebotInfo }>(
    "POST", `/api/guidebots/${bot}/chat`, { message, ...(session_id ? { session_id } : {}) });
export const guideHistory = (bot: string, session_id: string) =>
  req<{ session_id: string; step: number; messages: ChatMsg[] }>(
    "GET", `/api/guidebots/${bot}/chat/${session_id}`);
export const auditList = (limit = 200) =>
  req<{ audit_id: string; actor: string; event: string;
        details: Record<string, unknown>; created_at: string }[]>("GET", `/api/audit?limit=${limit}`);
