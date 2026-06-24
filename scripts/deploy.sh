#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# deploy.sh — Deploy pipeline to Cloudflare
#
# The scraper (./scraper) is run separately BEFORE deploy.
# This script only pushes data to D1 and deploys the Worker + Pages.
#
# Prerequisites:
#   - wrangler installed and authenticated
#   - D1 database created: npx wrangler d1 create henryrollins
#   - ADMIN_API_KEY set: npx wrangler secret put ADMIN_API_KEY
#   - Frontend built: cd web/app && npm run build
#
# Usage:
#   ./scripts/deploy.sh
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

WRANGLER="$ROOT/worker/node_modules/.bin/wrangler"

echo "═══════════════════════════════════════════════"
echo "  Fanatic — Henry Rollins Scraper Deploy"
echo "═══════════════════════════════════════════════"

# ── Step 1: Export to D1 seed and push ──

echo ""
echo "=== Step 1/3: Exporting to D1 SQL seed ==="
python3 scripts/generate-d1-seed.py seed.sql
echo "✅ Seed exported"

echo ""
echo "=== Step 2/3: Pushing to D1 (remote) ==="
$WRANGLER d1 execute henryrollins --remote --file=seed.sql 2>&1 | tail -3
echo "✅ D1 updated"

# ── Step 2: Deploy Worker + Pages ──

echo ""
echo "=== Step 3a/3: Deploying API Worker ==="
cd "$ROOT/worker"
$WRANGLER deploy 2>&1 | tail -3
echo "✅ Worker deployed"

echo ""
echo "=== Step 3b/3: Deploying Frontend (Pages) ==="
cd "$ROOT/web/app"
"$ROOT/worker/node_modules/.bin/wrangler" pages deploy dist --project-name=fanatic --branch=main 2>&1 | tail -5
echo "✅ Pages deployed"

echo ""
echo "═══════════════════════════════════════════════"
echo "  ✅ Deployment complete!"
echo "  🌐 https://fanatic.raske.xyz"
echo "═══════════════════════════════════════════════"
