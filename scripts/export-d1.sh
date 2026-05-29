#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# export-d1.sh — Export local SQLite to D1-compatible SQL seed
#
# Uses scripts/generate-d1-seed.py internally, which produces clean
# D1-safe SQL (no unistr(), no PRAGMAs, no sqlite_sequence).
#
# Usage:
#   ./scripts/export-d1.sh                    # writes to seed.sql
#   ./scripts/export-d1.sh --remote           # pushes directly to D1
#   ./scripts/export-d1.sh seed-output.sql    # writes to named file
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB="$ROOT/db/henryrollins.db"
OUT="${1:-$ROOT/seed.sql}"
PUSH_REMOTE=false

if [ "$1" = "--remote" ]; then
  OUT="$ROOT/seed.sql"
  PUSH_REMOTE=true
fi

if [ ! -f "$DB" ]; then
  echo "❌ Database not found at $DB"
  echo "   Run the scraper first, or check your path."
  exit 1
fi

echo "📦 Exporting $DB → $OUT"
python3 "$ROOT/scripts/generate-d1-seed.py" "$OUT"

if $PUSH_REMOTE; then
  echo ""
  echo "☁️  Pushing to D1 (remote)..."
  cd "$ROOT"
  "$ROOT/worker/node_modules/.bin/wrangler" d1 execute henryrollins --remote --file="$OUT" 2>&1 | tail -3
  echo "✅ D1 updated"
fi
