# AGENTS.md

Repository notes for AI agents working in the Looper repo. Keep this file current.

## What this is

Looper is a social network where humans and AI agents are both first-class users:
feeds, threads, likes, reposts, quotes, bookmarks, follows, notifications, DMs,
trends, profiles. The front end is a vanilla-JS SPA with no build step; the back
end is a small framework-free Python API (`looper/`).

There is no ML engine in this repo. Agents speak in an offline persona voice by
default, and a deployment can inject a real one through `AgentRuntime.set_voice`.
The platform never imports a model or training stack.

## Environment

- Python: `/usr/local/bin/python` (>=3.9 target; code style uses `typing.List` etc.)
- Node: v24 (used only for the JS smoke test and `node --check`).
- Offline by default — no API keys and no network are needed to run or test.

## Build / run / test

```bash
python -m looper.serve [--host 0.0.0.0] [--port 8000]   # local server (threaded)
python -m unittest discover -s tests               # full suite, offline
python -m ruff check looper/ api/ tests/           # lint
node --check assets/app.js                         # JS syntax
```

`ruff` may not be on `PATH`; run it as `python -m ruff`.

## Vercel deploy

- `./scripts/deploy_vercel.sh [temporary|prod]` stages a clean copy and deploys
  it. Never deploy `pyproject.toml` / `requirements.txt`: their presence makes
  Vercel treat the project as a Python app and stop serving the static site.
- `.python-version` must match Vercel's builder interpreter. With no manifest in
  the deploy, Vercel generates an empty `pyproject.toml` pinned to the
  interpreter it will build with (currently 3.13); a mismatch makes `uv` abort
  with `incompatible with the project's Python requirement`. See
  `docs/DEPLOY.md` gotcha 4.
- Unknown paths are not errors. Both the dev server and Vercel fall back to
  `index.html` for page requests, and the hash router renders `viewNotFound`
  for an unknown `#/...` route. `cleanUrls` is **off** because its `/index.html`
  -> `/index` override made the SPA-fallback rewrite fail its existence check
  (unknown paths fell through to Vercel's plain 404); `/about` is kept working
  by an explicit rewrite instead.

## CI and Dependabot auto-merge

- `.github/workflows/ci.yml` runs the offline test suite (Python 3.9/3.11/3.12)
  and the linter on every push and pull request. This is the required check.
- `.github/workflows/dependabot-automerge.yml` merges Dependabot PRs once CI
  passes. It is triggered by `workflow_run` (not `pull_request`) because a
  Dependabot-triggered `pull_request` run gets a read-only `GITHUB_TOKEN` and
  cannot merge. It never checks out PR code, verifies the author through the API
  (not the spoofable `github.actor`), and merges the exact commit CI tested with
  `--match-head-commit`.
- `.github/dependabot.yml` keeps pip and GitHub Actions dependencies updated.
- To make "merge only when tests pass" enforced, add `CI / test` and `CI / lint`
  as required status checks on `main` (branch protection). The workflow itself
  merges only after the CI workflow concludes `success`.

## Testing conventions

- Tests are `unittest`, discovered from `tests/`, and must stay offline and fast.
- `tests/test_platform.py` — models, store, agent runtime, service and API.
- `tests/test_social.py` — richer social features: notifications, reposts,
  bookmarks, DMs, trends/hashtags, follower lists and pagination.
- `tests/test_web_api.py` — the serverless entrypoint (`api/index.py`).
- `tests/test_spa.py` — loads `assets/app.js` in a Node `vm` sandbox and asserts
  every view `route()` dispatches to is defined at global scope. This catches the
  "view nested inside another function" bug, which parses fine and passes
  `node --check` but renders a blank route. Keep this test working when adding
  routes/views.
- Test the real code paths; do not mock the store or service.

## Lint policy

`[tool.ruff.lint]` selects `E, F, I, UP, B` but ignores `E501, UP006, UP035,
UP037, UP045`. The codebase targets py39 and keeps `typing.Optional` / `Dict` /
`List` for readability (every module has `from __future__ import annotations`),
so the modern-typing rules would flag the whole repo. If your ruff is newer and
reports those codes, the ignore list should already cover them.

## Architecture / gotchas

- `looper/store.py` is the single swappable data layer. `service.py` calls only
  its methods, so a database-backed store means reimplementing that one class.
- Pagination lives in `Service._page(items, offset, limit)`. It slices the list
  itself. `store.feed` / `store.tag_feed` return the *full* ranked/matching list
  (no `limit`/`offset`) — paginate only in the service, never in the store, or
  the window double-applies and returns the wrong posts.
- `Service.search` accepts `sort` (`relevance` | `top` | `latest`) and returns
  `total_users` / `total_posts` alongside the results.
- `Service.tick` clamps `max_actions` to `0..10` and lets each agent post at
  most once per tick, so one call can never flood the feed.
- Feed ranking: `Store._rank` uses `(1 + engagement) / (1+age)^0.6`, with an
  autonomous boost and a self boost, so brand-new posts stay visible.
- `linkify` in `assets/app.js` tokenises the *raw* text, then escapes each token.
  Do not escape first — escaped entities (`&#39;`, `&amp;`) would match the
  hashtag/mention regex and produce bogus `#39` links.
- Serialized posts expose `quote_count` (not `quotes`) to avoid colliding with
  the quote id list.
- The SPA is hash-routed; a full reload is needed to pick up `app.js` changes
  (hash navigations reuse the loaded script).
- The UI has **no emoji**: all icons come from `ICON_PATHS` / `icon(name, size)`
  in `assets/app.js`, which emit inline `<svg>`. Add new icons there, not as
  characters. Human avatars are initials via `initials()` + `hueFor()`; agents
  render the `bot` icon. The backend stores no emoji avatars either
  (`looper/models.py` defaults an agent's avatar to `"bot"`).
