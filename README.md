# FINOS — Phase 0 Scaffold

Local folder: `FINOS-AI` · GitHub repo: `FINOS`

Minimal bootstrap. No app spec yet — this is the working root the DSH server and future phases will build on.

## DSH server (verified on this machine)

- CLI: `npx -y @deepseek-ai/dsh` (`@deepseek-ai/dsh@0.1.2-rc.1`)
- Home: `C:\Users\Jatin Singh Kaintura\.dsh`
- Installed profile: `web` (`@deepseek-ai/dsh-base`, `@deepseek-ai/dsh-web-app`)
- Boot it: `npx -y @deepseek-ai/dsh web` or `npx -y @deepseek-ai/dsh --profile web`
- Headless (one-shot): `npx -y @deepseek-ai/dsh --profile headless "task"` — requires a `headless` profile (not installed here; only `web` exists)

Credentials live in `.dsh/.credentials.yaml` (`DEEPSEEK_API_KEY` ref). Do not commit keys.

## This scaffold

```
FINOS-AI/
├── README.md
├── package.json
├── src/index.js
└── .env.example
```

## Next

Define what FINOS should do (one line is enough), then Phase 1 begins.
