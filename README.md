# FINOS — payment-state intelligence (MVP)

Web-based AI financial-operations system. Razorpay payment events → ingest & verify →
reconstruct payment timeline → detect exceptions → investigate with AI → show evidence →
recommend → policy checks → execute approved actions → audit log.

**Architecture: Facts → Rules/State Engine → AI Reasoning → Policy Gate → Approved Action.**
The AI investigates and explains. Financial truth comes from verified events/data;
sensitive actions pass through policy controls. No invented "retry payment" — FINOS never re-charges.

## MVP cases (seeded demo)

| Case | Kind | Outcome |
|------|------|---------|
| #1042 | Ambiguous payment (O-123/P-456 captured, checkout timed out) | Do not ask again — already captured |
| #1043 | Duplicate payment (O-124, two captured) | Guarded refund of the later payment |
| #1044 | Settlement anomaly (S-789) | Explain gap, flag for review |

## Run locally

```bash
# backend (Python 3.11, uv)
cd backend
uv venv .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000

# frontend dev (optional — backend serves the built UI at /)
cd frontend && npm install && npm run build
```

Open http://localhost:8000 — dashboard → case → timeline → AI diagnosis →
evidence → approval → execution → audit. `Reset demo` restores the three cases.

## Configuration (env)

| Var | Default | Meaning |
|-----|---------|---------|
| `DEEPSEEK_API_KEY` | (unset) | AI investigator key; unset = deterministic fallback so the demo always works |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | Override for OpenRouter etc. (`DEEPSEEK_MODEL` likewise) |
| `RAZORPAY_WEBHOOK_SECRET` | (unset) | Enables real HMAC webhook verification; events without it are ingested as unverified |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | (unset) | Live Razorpay API; unset = dry-run refunds (simulated, recorded) |
| `RAZORPAY_LIVE=1` | off | **Only** with real keys: executes real refunds through the guarded layer |
| `FINOS_DB` | `backend/finos.db` | SQLite path |

## API

- `POST /webhooks/razorpay` — ingest + verify + detect (header `x-razorpay-signature`)
- `GET /api/cases` · `GET /api/cases/{no}` (case + timeline + decisions + action + policy + audit)
- `POST /api/cases/{no}/investigate` → `{decision, action, policy}`
- `POST /api/cases/{no}/approve` · `POST /api/cases/{no}/execute` (idempotent)
- `GET /api/audit` · `POST /api/seed/reset` (demo-only)

## Deploy

Single service: backend serves the built frontend. `Dockerfile` + `render.yaml` included
(Render/Railway/Fly: build frontend, run uvicorn). Set env keys in the host dashboard.

## DSH server

This machine has the DeepSeek Harness CLI (`npx -y @deepseek-ai/dsh`, profile `web`).
FINOS uses the DeepSeek API directly for the investigator; the key ref lives in
`~/.dsh/.credentials.yaml` (`DEEPSEEK_API_KEY`). Point `DEEPSEEK_BASE_URL` at any
OpenAI-compatible endpoint.
