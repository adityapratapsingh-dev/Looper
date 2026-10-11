# Deploying the Looper demo to Vercel

The repository doubles as a Vercel project:

- **Static site** — `index.html` + `assets/` (the landing page and playground).
- **Python serverless function** — `api/demo.py` runs the *real* `data`
  distillation mode on demand at `/api/demo` (offline `echo` teacher, no keys).
- **`requirements.txt`** — installed by Vercel for the Python runtime.
- **`vercel.json`** — pins the Python runtime and bundles `distill/**` into the function.

## Option A — Git integration (recommended)

1. Push the branch / merge the PR into `main`.
2. In the Vercel dashboard: **Add New → Project → Import** `Looper`.
3. Framework preset: **Other**. Leave build/output settings at their defaults.
4. **Deploy.** Every push to `main` redeploys automatically.

## Option B — Vercel CLI

```bash
npm i -g vercel
vercel login                 # interactive, or set VERCEL_TOKEN for CI
vercel                       # preview deployment
vercel --prod                # production deployment
```

For non-interactive/CI use:

```bash
export VERCEL_TOKEN=...            # from vercel.com/account/tokens
vercel deploy --prod --yes --token "$VERCEL_TOKEN"
```

Or use the helper script:

```bash
VERCEL_TOKEN=... ./scripts/deploy_vercel.sh
```

## How the pieces map

| File | Role on Vercel |
|------|----------------|
| `index.html` | `/` |
| `assets/styles.css`, `assets/app.js` | `/assets/*` |
| `api/demo.py` | `/api/demo` (GET = catalogue, POST = run data mode) |
| `requirements.txt` | Python deps for the function |
| `vercel.json` | runtime pin, `includeFiles: distill/**`, cache headers |
| `.vercelignore` | keeps tests/examples/docs out of the deployment |

## Notes & limits

- The demo uses the deterministic `echo` teacher so it is free, offline and
  needs no secrets. To distil with a real teacher, add the key as a Vercel
  environment variable and switch `provider` in `api/demo.py`.
- Vercel functions are stateless and time-limited (`maxDuration: 30`). The demo
  caps input at 25 prompts.
- Python on Vercel does not ship `torch`, so the **logits** mode is not exposed
  in the serverless demo — it runs locally/on a GPU host instead.
