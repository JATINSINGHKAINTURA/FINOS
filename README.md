# FINOS — payment-state intelligence

Web-based AI financial-operations system. Razorpay payment events → ingest & verify →
reconstruct payment timeline → detect exceptions → investigate with AI → show evidence →
recommend → policy checks → execute approved actions → audit log.

**Architecture: Facts → Rules/State Engine → AI Reasoning → Policy Gate → Approved Action.**
The AI investigates and explains. Financial truth comes from verified events/data;
sensitive actions pass through policy controls. No invented "retry payment" — FINOS never re-charges.

## What it does

- **Cases dashboard** — ambiguous payment (#1042), duplicate payment (#1043), settlement anomaly (#1044),
  each with timeline, AI diagnosis, evidence, policy preview, approval/execution, audit trail.
- **Assistant** — read-only chatbot grounded in live case data (with DeepSeek when configured,
  deterministic fallback otherwise). Sessions persist.
- **Guidebots** — task-oriented assistants that act through governed tools and never claim
  unexecuted actions: **Case Pilot** (resolve a case step by step) and **Webhook Helper**
  (explain + fire real test events). Registry-based — add new bots in
  `backend/app/guidebots/registry.py` without touching the engine.
- **Audit trail** — every detection, decision, approval, execution, and test event.

## Run locally

```bash
# backend (Python 3.11, uv) — serves API + built UI at http://localhost:8000
cd backend
uv venv .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000

# frontend dev (optional)
cd frontend && npm install && npm run dev   # proxied to :8000, see vite.config.ts
cd frontend && npm run build                # output consumed by the backend at /
```

Tests: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -q`

## Configuration (`backend/.env`, see `.env.example` — never commit `.env`)

| Var | Default | Meaning |
|-----|---------|---------|
| `DEEPSEEK_API_KEY` | (unset) | AI investigator/assistant/guidebot brain; unset = deterministic fallback |
| `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` | `https://api.deepseek.com` / `deepseek-chat` | Any OpenAI-compatible endpoint |
| `RAZORPAY_WEBHOOK_SECRET` | (unset) | Real HMAC verification; otherwise events are stored flagged unverified |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | (unset) | Live API; unset = dry-run refunds (simulated, recorded) |
| `RAZORPAY_LIVE=1` | off | Only with real keys: executes real refunds through the guarded layer |
| `FINOS_API_KEY` | (unset) | When set, mutating endpoints require header `X-API-Key` |
| `FINOS_CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `FINOS_RL_WRITE_PER_MIN` / `FINOS_RL_CHAT_PER_MIN` | `60` / `30` | Per-IP rate limits |
| `FINOS_DB` | `backend/finos.db` | SQLite path (`/tmp/finos.db` on serverless) |

## API

- `POST /webhooks/razorpay` — ingest + verify + detect (`x-razorpay-signature`)
- `GET /api/cases` · `GET /api/cases/{no}` (case + reconstruction + decisions + action + policy + audit)
- `POST /api/cases/{no}/investigate` → `{decision, action, policy}`
- `POST /api/cases/{no}/approve` · `POST /api/cases/{no}/execute` (idempotent; executed actions immutable)
- `POST /api/chat` · `GET /api/chat/{session_id}` (assistant)
- `GET /api/guidebots` · `POST /api/guidebots/{id}/chat` · `GET /api/guidebots/{id}/chat/{session_id}`
- `GET /api/audit` · `POST /api/seed/reset` (demo-only)
- Errors are always `{ok:false, error, code}`.

## Deploy

- **Vercel** (frontend + serverless API): `vercel.json` + `api/index.py` wrap this same FastAPI app;
  set `FINOS_DB=/tmp/finos.db` plus any keys in the Vercel dashboard, then `vercel --prod`.
  Note: serverless instances are ephemeral — each cold start reseeds the demo DB.
- **Docker** (persistent): `Dockerfile` + `render.yaml` (Render/Railway/Fly).

## Security notes

- No secrets in the repo (verified by scan); keys only via env, server-side only.
- Webhook HMAC verification, optional API-key guard, per-IP rate limits, input sanitization
  + length caps, no business truth from the LLM, policy gate + idempotency on money movement.

## DSH server

This project was built alongside the DeepSeek Harness CLI (`npx -y @deepseek-ai/dsh`, profile `web`).
FINOS uses the DeepSeek API directly for its AI layers; the key ref lives in
`~/.dsh/.credentials.yaml` (`DEEPSEEK_API_KEY`).
