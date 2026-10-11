# Deploying the Looper demo to Vercel

The repository doubles as a Vercel project:

- **Static site** — `index.html` + `assets/` (landing page + live playground).
- **Python serverless function** — `api/index.py` runs the *real* `data`
  distillation mode at `/api` (offline `echo` teacher, no keys needed).
- **`vercel.json`** — pins function limits and bundles `distill/**` into the function.
- **`.python-version`** — pins the Python runtime (3.12) for the function.

## Quick deploy (no account needed)

```bash
./scripts/deploy_vercel.sh          # anonymous, claimable deployment
```

This prints a URL and a **claim link**. Anonymous deployments expire after ~60
minutes unless you open the claim link (or log in) to keep them.

## Production deploy

```bash
export VERCEL_TOKEN=...             # https://vercel.com/account/tokens
./scripts/deploy_vercel.sh prod     # or: npx vercel deploy --prod --yes
```

## Git integration

1. Import the repo in the Vercel dashboard.
2. Framework preset: **Other**. Leave build/output defaults.
3. Deploy. Pushes to `main` redeploy automatically.

## How the pieces map

| File | Role on Vercel |
|------|----------------|
| `index.html` | `/` |
| `assets/styles.css`, `assets/app.js` | `/assets/*` |
| `api/index.py` | `/api` (GET = catalogue, POST = run data mode) |
| `vercel.json` | function limits + `includeFiles: distill/**` |
| `.python-version` | Python 3.12 for the function |
| `.vercelignore` | keeps tooling state, tests, docs and build config out of the deploy |

## Two things that will bite you

1. **Never deploy `pyproject.toml` (or `requirements.txt`).** When Vercel sees
   them it classifies the project as a *Python app*: it emits a single catch-all
   function and **stops serving the static site** (so `/` returns JSON instead of
   the page). Both files are listed in `.vercelignore`; the deploy script also
   stages a clean copy without them. The demo needs no third-party packages —
   the framework core is standard-library only.
2. **Deploy from a clean directory.** Vercel bundles the whole working directory
   into the function. Running `vercel` from the repo root can sweep in caches and
   tooling state (easily hundreds of MB) and trip the 500 MB function limit.
   `scripts/deploy_vercel.sh` builds in `${TMPDIR}/looper-deploy` instead.

## Notes & limits

- The demo uses the deterministic `echo` teacher, so it is free, offline and
  secret-free. To distil with a real teacher, add the key as a Vercel environment
  variable and switch `provider` in `api/index.py`.
- Vercel functions are stateless and time-limited (`maxDuration: 30`); the demo
  caps input at 25 prompts.
- Vercel's Python runtime does not ship `torch`, so the **logits** mode is not
  exposed serverlessly — run it locally or on a GPU host.
