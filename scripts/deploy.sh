#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# deploy.sh — Full deployment pipeline to Cloudflare
#
# Prerequisites:
#   - wrangler installed and authenticated
#   - D1 database created: npx wrangler d1 create henryrollins
#   - ADMIN_API_KEY set: npx wrangler secret put ADMIN_API_KEY
#   - Frontend built: cd web/app && npm run build
#
# Usage:
#   ./scripts/deploy.sh              # Deploy without scraping
#   ./scripts/deploy.sh --scrape     # Scrape new episodes first
#   ./scripts/deploy.sh --fast       # Skip enrichment, use existing data
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

WRANGLER="$ROOT/worker/node_modules/.bin/wrangler"
SCRAPE=false
FAST=false

for arg in "$@"; do
  case "$arg" in
    --scrape) SCRAPE=true ;;
    --fast)   FAST=true ;;
  esac
done

echo "═══════════════════════════════════════════════"
echo "  Fanatic — Henry Rollins Scraper Deploy"
echo "═══════════════════════════════════════════════"

# ── Step 1: Scrape new episodes (optional) ──

if $SCRAPE; then
  echo ""
  echo "=== Step 1/5: Scraping new episodes ==="
  if [ -f ./scraper ]; then
    ./scraper
    echo "✅ Scrape complete"
  else
    echo "⚠️  scraper not found, skipping"
  fi
fi

# ── Step 2: Build artist cache + enrichment ──

if ! $FAST; then
  echo ""
  echo "=== Step 2a/5: Building artist cache ==="
  if [ -f ./build-cache ]; then
    ./build-cache 2>/dev/null || true
    echo "✅ Build cache complete"
  fi

  echo ""
  echo "=== Step 2b/5: Pre-baking enrichment data (offline) ==="
  python3 scripts/seed-enrichment.py 2>&1 | tail -5
  echo "✅ Enrichment complete"
fi

# ── Step 3: Merge enrichment into main DB ──

echo ""
echo "=== Step 3/5: Merging enrichment into main DB ==="
sqlite3 db/henryrollins.db < scripts/merge-enrichment.sql
echo "✅ Merge complete"

# ── Step 4: Export to D1 seed and push ──

echo ""
echo "=== Step 4a/5: Exporting to D1 SQL seed ==="
python3 scripts/generate-d1-seed.py seed.sql
echo "✅ Seed exported"

echo ""
echo "=== Step 4b/5: Pushing to D1 (remote) ==="
$WRANGLER d1 execute henryrollins --remote --file=seed.sql 2>&1 | tail -3
echo "✅ D1 updated"

# ── Step 5: Deploy Worker + Pages ──

echo ""
echo "=== Step 5a/5: Deploying API Worker ==="
cd "$ROOT/worker"
$WRANGLER deploy 2>&1 | tail -3
echo "✅ Worker deployed"

echo ""
echo "=== Step 5b/5: Deploying Frontend (Pages) ==="
cd "$ROOT/web/app"
"$ROOT/worker/node_modules/.bin/wrangler" pages deploy dist --project-name=fanatic --branch=main 2>&1 | tail -5
echo "✅ Pages deployed"

echo ""
echo "═══════════════════════════════════════════════"
echo "  ✅ Deployment complete!"
echo "  🌐 https://fanatic.raske.xyz"
echo "  🔧 https://henryrollins-api.terminal-share.workers.dev"
echo "═══════════════════════════════════════════════"
