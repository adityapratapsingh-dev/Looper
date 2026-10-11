#!/usr/bin/env bash
# Deploy the Looper demo to Vercel from a clean staging directory.
#
# Usage:
#   ./scripts/deploy_vercel.sh                       # anonymous temporary deploy
#   VERCEL_TOKEN=... ./scripts/deploy_vercel.sh prod # authenticated production
#
# Why staging? Vercel bundles the working directory into the serverless function.
# Building from the repo root pulls in sandbox/tooling state (huge) and
# pyproject.toml, which makes Vercel treat the project as a pure Python app and
# stop serving the static site. Staging ships exactly what the deployment needs.
set -euo pipefail

MODE="${1:-temporary}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="${TMPDIR:-/tmp}/looper-deploy"

rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -r "$ROOT/index.html" "$ROOT/about.html" "$ROOT/assets" "$ROOT/api" "$ROOT/looper" "$STAGE/"
cp "$ROOT/vercel.json" "$ROOT/.python-version" "$ROOT/README.md" "$ROOT/LICENSE" "$STAGE/"

# TLS: some CI proxies require the system CA bundle for uv/pip.
export UV_SYSTEM_CERTS=1
export UV_NATIVE_TLS=1
if [ -f /etc/ssl/certs/ca-certificates.crt ]; then
  export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
  export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
fi

cd "$STAGE"
ARGS="deploy --yes"
if [ "$MODE" = "temporary" ]; then
  ARGS="$ARGS --temporary"
elif [ "$MODE" = "prod" ]; then
  ARGS="$ARGS --prod"
fi
if [ -n "${VERCEL_TOKEN:-}" ]; then
  ARGS="$ARGS --token $VERCEL_TOKEN"
fi

echo "Deploying ($MODE) from $STAGE ..."
# shellcheck disable=SC2086
npx --yes vercel $ARGS
