#!/usr/bin/env bash
# Deploy the Looper demo to Vercel.
#
# Usage:
#   VERCEL_TOKEN=xxxxx ./scripts/deploy_vercel.sh          # production
#   VERCEL_TOKEN=xxxxx ./scripts/deploy_vercel.sh preview  # preview
#
# Create a token at https://vercel.com/account/tokens
set -euo pipefail

MODE="${1:-prod}"
cd "$(dirname "$0")/.."

if ! command -v vercel >/dev/null 2>&1; then
  echo "vercel CLI not found — installing locally via npx..."
  VERCEL="npx --yes vercel"
else
  VERCEL="vercel"
fi

if [[ -z "${VERCEL_TOKEN:-}" ]]; then
  echo "ERROR: set VERCEL_TOKEN (https://vercel.com/account/tokens)" >&2
  exit 1
fi

ARGS=(deploy --yes --token "$VERCEL_TOKEN")
if [[ "$MODE" == "prod" ]]; then
  ARGS+=(--prod)
fi

echo "Deploying ($MODE)…"
$VERCEL "${ARGS[@]}"
