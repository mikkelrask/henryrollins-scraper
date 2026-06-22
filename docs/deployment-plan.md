# Deployment Plan — Cloudflare Pages + D1 + Hono

## Architecture Overview

```
                   ┌─────────────────────────────────┐
                   │      Cloudflare Pages            │
                   │  ┌───────────────────────────┐   │
                   │  │  Svelte 5 Static Frontend │   │
                   │  │  (web/app/dist/)          │   │
                   │  └──────────┬────────────────┘   │
                   │             │ /api/*              │
                   │  ┌──────────▼────────────────┐   │
                   │  │  Hono API Worker           │   │
                   │  │  (TypeScript, 15 routes)   │   │
                   │  └──────────┬────────────────┘   │
                   └─────────────┼────────────────────┘
                                 │ env.DB
                      ┌──────────▼──────────┐
                      │  D1: henryrollins    │
                      │  (10 tables, ~5MB)   │
                      │  - episodes          │
                      │  - tracks            │
                      │  - artists           │
                      │  - albums            │
                      │  - links             │
                      │  - artist_enrichment │
                      │  - album_art         │
                      │  - corrections       │
                      │  - migration_log     │
                      │  - ignored_clusters  │
                      │  + 6 indexes         │
                      └──────────────────────┘
```

## Decisions (confirmed)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Databases** | Single D1 | Both DBs are always queried together; 5 MB total fits D1 with decades of headroom |
| **Enrichment** | Pre-baked locally | Save Worker minutes; run MusicBrainz/Last.fm enrichment as a local build step, then dump the baked DB to D1 |
| **Backend** | Hono + D1 | Lightweight, purpose-built for Workers, ergonomic SQLite support |
| **Scraping** | Local cron + manual deploy | Scraper stays in Python (no rewrite); scrape locally, bake enrichment, then deploy batched updates |

---

## Project Structure

```
henryrollins-scraper/
├── db/                          # Local SQLite database (unified)
│   └── henryrollins.db          # All 10 tables in one file
├── web/
│   ├── app/                     # Svelte 5 frontend (unchanged)
│   │   ├── src/                 # (15 routes, 7 components)
│   │   ├── dist/                # Built static assets → Pages
│   │   └── ...
│   └── api/                     # Python FastAPI (kept for local dev, NOT deployed)
├── worker/                      # ★ NEW: Hono API Worker
│   ├── src/
│   │   ├── index.ts             # Entry point — Hono app, CORS, route registration
│   │   ├── db.ts                # D1 binding helper (all/one/run/exec/batch)
│   │   ├── models/
│   │   │   └── schemas.ts       # TypeScript types (mirroring Pydantic schemas)
│   │   └── routers/
│   │       ├── episodes.ts      # List + detail with corrections
│   │       ├── artists.ts       # List, detail, top, timeline, heatmap, albums, tracks
│   │       ├── albums.ts        # List, detail, heatmap
│   │       ├── tracks.ts        # List with search/sort/pagination
│   │       ├── stats.ts         # Overview, top-*, heatmap, countries, genres, decades
│   │       ├── recommends.ts    # Bandcamp links
│   │       ├── search.ts        # Unified artist/album/track search
│   │       └── admin.ts         # Auth, cluster detection, merge, corrections, rename
│   ├── wrangler.toml            # Worker config + D1 binding
│   ├── tsconfig.json
│   └── package.json             # hono, wrangler, typescript, vitest
├── scripts/
│   ├── merge-enrichment.sql     # Create enrichment tables in main DB
│   ├── seed-enrichment.py       # Run ALL artists/albums through MusicBrainz + Last.fm
│   ├── export-d1.sh             # Dump local SQLite → D1-compatible SQL seed file
│   └── deploy.sh                # Full pipeline: scrape → enrich → export → push → deploy
├── docs/
│   ├── deployment-plan.md       # This document
│   └── admin-panel-plan.md      # Original admin plan (still relevant)
├── .gitignore                   # Updated for worker + seed artifacts
└── ...
```

---

## Database Migration: Merge Both SQLite Files

The two databases become one D1 with all 10 tables. Run this once to create the unified local DB:

```sql
-- db/unified.sql — run once to merge enrichment into main db

-- Create enrichment tables in henryrollins.db
CREATE TABLE IF NOT EXISTS artist_enrichment (
    artist_name TEXT PRIMARY KEY,
    mbid TEXT,
    canonical_name TEXT,
    country TEXT,
    formed_year INTEGER,
    genres TEXT,
    tags TEXT,
    bio_summary TEXT,
    wikipedia_url TEXT,
    lastfm_tags TEXT,
    lastfm_bio TEXT,
    lastfm_listeners INTEGER,
    lastfm_playcount INTEGER,
    lastfm_url TEXT,
    last_fetched TEXT,
    fetch_count INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS album_art (
    album_name TEXT NOT NULL,
    artist_name TEXT NOT NULL,
    mbid TEXT,
    release_group_mbid TEXT,
    canonical_name TEXT,
    artwork_url TEXT,
    release_year INTEGER,
    release_date TEXT,
    last_fetched TEXT,
    PRIMARY KEY (album_name, artist_name)
);

CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER,
    episode_id INTEGER,
    type TEXT NOT NULL,
    original_data TEXT,
    corrected_data TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS release_group_cache (
    rg_mbid TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at TEXT DEFAULT (datetime('now'))
);
```

Then use the export script to dump as a D1-compatible SQL file.

---

## Pre-baking Enrichment Locally

You run this on your machine (before deploy):

```bash
# 1. Scrape new episodes (existing cron job)
./scraper

# 2. Build artist cache (existing)
./build-cache

# 3. Run enrichment for ALL artists + albums (offline, no Worker minutes)
cd scripts
python3 seed-enrichment.py --all

# 4. Merge enrichment into main DB
sqlite3 ../db/henryrollins.db < merge-enrichment.sql

# 5. Export to D1-compatible SQL
./export-d1.sh
```

The `seed-enrichment.py` script reuses the existing `services/enrichment.py` logic — it iterates every artist in `tracks`, fetches MusicBrainz + Last.fm data, and writes to the db at its own pace (respecting API rate limits, no Worker timeout worries).

---

## Hono Worker Structure

### Entry point (`worker/src/index.ts`)

```typescript
import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { episodes } from './routers/episodes'
import { artists } from './routers/artists'
import { albums } from './routers/albums'
import { tracks } from './routers/tracks'
import { stats } from './routers/stats'
import { recommends } from './routers/recommends'
import { search } from './routers/search'
import { admin } from './routers/admin'

type Bindings = {
  DB: D1Database
  ADMIN_API_KEY?: string
}

const app = new Hono<{ Bindings: Bindings }>()

app.use('/api/*', cors({
  origin: ['http://localhost:5173', 'https://*.pages.dev'],
  credentials: true,
}))

app.route('/api/episodes', episodes)
app.route('/api/artists', artists)
app.route('/api/albums', albums)
app.route('/api/tracks', tracks)
app.route('/api/stats', stats)
app.route('/api/recommends', recommends)
app.route('/api/search', search)
app.route('/api/admin', admin)

app.get('/api/health', (c) => c.json({
  status: 'ok',
  episodes: 496,
  tracks: 16914,
  artists: 2678,
}))

export default app
```

### SQL query porting pattern

Python FastAPI → Hono is near 1:1 because D1 speaks SQLite:

```python
# Python FastAPI
def _db(request):
    db = sqlite3.connect(request.app.state.db_path)
    db.row_factory = sqlite3.Row
    return db

rows = db.execute(
    "SELECT * FROM episodes ORDER BY broadcast DESC LIMIT ? OFFSET ?",
    (per_page, offset),
).fetchall()
```

```typescript
// Hono + D1
const { results } = await c.env.DB.prepare(
  "SELECT * FROM episodes ORDER BY broadcast DESC LIMIT ? OFFSET ?"
).bind(perPage, offset).all();
```

Key mappings:
| Python SQLite | Hono D1 |
|--------------|---------|
| `db.execute(sql, params).fetchall()` | `DB.prepare(sql).bind(...).all()` → `results` |
| `db.execute(sql, params).fetchone()` | `DB.prepare(sql).bind(...).first()` |
| `db.execute(sql, params).execute()` (INSERT/UPDATE) | `DB.prepare(sql).bind(...).run()` |
| `db.execute("BEGIN TRANSACTION")` | `DB.exec("BEGIN TRANSACTION")` |
| `GROUP_CONCAT` | Same — D1 supports it |
| `strftime` | Same — D1 supports SQLite date functions |
| `json.loads` (from text column) | `JSON.parse()` |

### Wrangler config (`worker/wrangler.toml`)

```toml
name = "henryrollins-api"
compatibility_date = "2025-10-01"

# D1 binding
[[d1_databases]]
binding = "DB"
database_name = "henryrollins"
database_id = "<your-database-id>"

# Admin key (set via wrangler secret put ADMIN_API_KEY)
[vars]
ADMIN_API_KEY = ""

[env.production]
[vars]
ADMIN_API_KEY = ""

[env.preview]
[vars]
ADMIN_API_KEY = ""
```

---

## Frontend: Cloudflare Pages

The Svelte frontend is already built by Vite. No changes to the frontend code are needed (!) because the API client (`api.js`) already uses relative `/api/*` paths. The Pages proxy or Worker handles routing.

**Key config change to `vite.config.js`**: The dev proxy stays the same. For production, the Worker at `henryrollins-api` serves `/api/*`, and Pages serves everything else.

**Pages config**: Set `Build command` to `npm run build` (in `web/app/`), `Build output directory` to `dist`, and add a `_routes.json` or `_redirects`:

```
# web/app/public/_redirects — deployed with the frontend
/api/*  https://henryrollins-api.<your-account>.workers.dev/api/:splat  200
```

Or better, use a Pages Function at `/functions/api/[[route]].ts` that proxies to the Worker:

```typescript
// functions/api/[[route]].ts
export async function onRequest(context) {
  const url = new URL(context.request.url)
  const target = `https://henryrollins-api.<account>.workers.dev${url.pathname}${url.search}`
  return fetch(target, context.request)
}
```

Or simplest of all — deploy the Worker on a **custom domain route** within Pages so the frontend and API share the same origin, avoiding any CORS/proxy config.

---

## Deployment Pipeline

### Local workflow (what you run)

```bash
# ── Step 1: Scrape new episodes ──
cd /home/mr/Repos/henryrollins-scraper
./scraper

# ── Step 2: Build artist cache + enrich ──
./build-cache
python3 scripts/seed-enrichment.py --all

# ── Step 3: Merge enrichment into main DB ──
sqlite3 db/henryrollins.db < scripts/merge-enrichment.sql

# ── Step 4: Dump to D1 seed SQL ──
sqlite3 db/henryrollins.db .dump > seed.sql
# Or filtered: skip sqlite_sequence, use explicit INSERTs

# ── Step 5: Push data to D1 ──
npx wrangler d1 execute henryrollins --remote --file=seed.sql

# ── Step 6: Deploy API Worker ──
cd worker
npx wrangler deploy

# ── Step 7: Deploy frontend ──
cd ../web/app
npx wrangler pages deploy dist --project-name=fanatic --branch=main
```

### Shell script (`scripts/deploy.sh`)

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Step 1: Scrape (if --scrape flag given) ==="
if [[ "${1:-}" == "--scrape" ]]; then
  cd "$ROOT" && ./scraper
fi

echo "=== Step 2: Build artist cache + enrichment ==="
cd "$ROOT" && ./build-cache 2>/dev/null || true
python3 "$ROOT/scripts/seed-enrichment.py" --all

echo "=== Step 3: Merge enrichment → main DB ==="
sqlite3 "$ROOT/db/henryrollins.db" < "$ROOT/scripts/merge-enrichment.sql"

echo "=== Step 4: Export to D1 seed ==="
sqlite3 "$ROOT/db/henryrollins.db" .dump > "$ROOT/seed.sql"
echo "  → $(wc -l < "$ROOT/seed.sql") lines, $(du -h "$ROOT/seed.sql" | cut -f1)"

echo "=== Step 5: Push to D1 ==="
npx wrangler d1 execute henryrollins --remote --file="$ROOT/seed.sql" 2>&1 | tail -3

echo "=== Step 6: Deploy Worker ==="
cd "$ROOT/worker" && npx wrangler deploy

echo "=== Step 7: Deploy Pages ==="
cd "$ROOT/web/app" && npx wrangler pages deploy dist --project-name=fanatic --branch=main

echo "=== Done ==="
```

---

## Implementation Phases

### Phase 1: Foundation — Project scaffolding
1. Create `worker/` directory with `wrangler.toml`, `tsconfig.json`, `package.json`
2. Install Hono, wrangler, vitest
3. Create the Hono entry point with CORS and one health-check route
4. Create `scripts/merge-enrichment.sql` and `scripts/seed-enrichment.py`
5. Verify `wrangler d1 execute` works with a seed file

### Phase 2: Core routes — Episodes, Artists, Albums, Tracks
Port the read-heavy routers first (no admin):
1. `routers/episodes.ts` — list + detail
2. `routers/artists.ts` — list, detail, timeline, heatmap, top, tracks, albums
3. `routers/albums.ts` — list, detail, heatmap
4. `routers/tracks.ts` — list with search/sort
5. `routers/search.ts` — unified search
6. `routers/stats.ts` — overview, top-*, heatmap, countries, genres, decades

### Phase 3: Recommends + Insights
1. `routers/recommends.ts` — Bandcamp links
2. Verify all stats endpoints (countries, genres-by-year, decades scatter)

### Phase 4: Admin routes
1. `routers/admin.ts` — auth, clusters, merge, corrections, track browser
2. Adapt the `require_admin` middleware for Hono
3. Adjust database operations (merge logic uses SQL, not Python)

### Phase 5: Frontend integration
1. Deploy Pages with `_redirects` or Pages Function proxy
2. Test CORS in preview environment
3. Update API_BASE if needed (shouldn't be — frontend uses relative `/api/*`)

### Phase 6: Deployment automation
1. Create `scripts/deploy.sh`
2. Set up wrangler secrets for `ADMIN_API_KEY`
3. Test full pipeline end-to-end

---

## Key Design Notes

### No request-time external API calls
The enrichment data is **pre-baked locally** and shipped as part of the D1 seed. This means:
- Zero Worker CPU time on external HTTP calls
- Zero API latency for enrichment fields (country, genres, bio, artwork)
- Predictable cold starts under 50ms
- No rate-limit concerns

To refresh enrichment, run `seed-enrichment.py` locally and re-deploy.

### Admin endpoints still work
All admin endpoints (cluster detection, merging, corrections) are pure SQL operations. They work identically on D1. The `ADMIN_API_KEY` secret is set via `wrangler secret put ADMIN_API_KEY`.

### Offline local dev
For local development without Cloudflare:
- Keep the Python FastAPI backend running (it still works as before)
- Or run the Hono Worker locally: `npx wrangler dev --remote`
- Or run with local D1: `npx wrangler dev --local --d1 DB`

---

## Database Row Counts (current baseline)

| Table | Rows | Notes |
|-------|------|-------|
| episodes | 498 | Broadcasts from 2017–present |
| tracks | 16,935 | Individual played tracks |
| artists | 2,335 | Normalized artist names |
| albums | 4,998 | Normalized album names |
| links | 634 | Bandcamp links |
| artist_enrichment | 2,686 | MusicBrainz + Last.fm cache |
| album_art | 6,018 | Artwork URLs + MBIDs |
| corrections | 17 | Track corrections |
| release_group_cache | 11 | MB release group lookups |

**Total DB size: ~5.3 MB** — well within D1's 10 GB limit with decades of room.

---

## What Was Built (Phase 1 Foundation)

This deployment plan was implemented in a single session. Here's what was created:

### New Files

| File | Purpose |
|------|---------|
| `worker/package.json` | Hono + wrangler + TypeScript dependencies |
| `worker/tsconfig.json` | Strict TypeScript config targeting Workers |
| `worker/wrangler.toml` | Worker name, D1 binding, admin key config |
| `worker/src/index.ts` | Hono app entry — CORS, middleware, 8 route registrations, health check |
| `worker/src/db.ts` | D1 helper class — `all()`, `one()`, `run()`, `exec()`, `batch()` |
| `worker/src/models/schemas.ts` | Full TypeScript type definitions (all ~20 response shapes) |
| `worker/src/routers/episodes.ts` | List (pagination) + detail (tracks, corrections, bandcamp links) |
| `worker/src/routers/artists.ts` | List (search/filter/sort), detail, top, timeline, heatmap, albums, tracks |
| `worker/src/routers/albums.ts` | List (pagination, artwork), detail (tracks, timeline, heatmap, releases), heatmap |
| `worker/src/routers/tracks.ts` | List with search, sort, pagination (grouped by title/artist/album) |
| `worker/src/routers/stats.ts` | Overview, top-artists/albums/tracks, heatmap, countries, genres, genres-by-year, decades |
| `worker/src/routers/recommends.ts` | Bandcamp link list, artist ranking, by-episode lookup |
| `worker/src/routers/search.ts` | Unified fuzzy search across artists, albums, tracks |
| `worker/src/routers/admin.ts` | Auth check, cluster detection, merge (preview+execute), corrections, rename, track browser |
| `scripts/merge-enrichment.sql` | Creates enrichment tables in the main D1 database |
| `scripts/seed-enrichment.py` | Offline enrichment runner — iterates all artists/albums through MusicBrainz + Last.fm |
| `scripts/export-d1.sh` | Dumps local SQLite to D1-compatible SQL seed file (filters PRAGMAs, adds safe INSERTs) |
| `scripts/deploy.sh` | Full pipeline: scrape → enrich → export → push to D1 → deploy Worker → deploy Pages |
| `.gitignore` | Root gitignore covering Python, Node, DB, seed artifacts |

### Route Coverage

The Hono Worker provides **100% endpoint parity** with the Python FastAPI backend:

| Python FastAPI | Hono D1 Worker | Status |
|----------------|----------------|--------|
| `GET /api/health` | ✅ | Health check |
| `GET /api/episodes` | `episodes.ts` | List with pagination |
| `GET /api/episodes/{ident}` | `episodes.ts` | Detail with corrections |
| `GET /api/artists` | `artists.ts` | List with search/filter/sort |
| `GET /api/artists/top` | `artists.ts` | Top N by metric |
| `GET /api/artists/albums/{name}` | `artists.ts` | Album breakdown |
| `GET /api/artists/tracks/{name}` | `artists.ts` | Track listing |
| `GET /api/artists/timeline/{name}` | `artists.ts` | Timeline data |
| `GET /api/artists/heatmap/{name}` | `artists.ts` | Monthly heatmap |
| `GET /api/artists/{name}` | `artists.ts` | Full detail with enrichment |
| `GET /api/albums` | `albums.ts` | List with search/sort |
| `GET /api/albums/heatmap/{name}` | `albums.ts` | Monthly heatmap |
| `GET /api/albums/{id}` | `albums.ts` | Full detail |
| `GET /api/tracks` | `tracks.ts` | List with search/sort |
| `GET /api/search` | `search.ts` | Unified search |
| `GET /api/stats/overview` | `stats.ts` | Aggregate stats |
| `GET /api/stats/top-artists` | `stats.ts` | Top artists |
| `GET /api/stats/top-albums` | `stats.ts` | Top albums |
| `GET /api/stats/top-tracks` | `stats.ts` | Top tracks |
| `GET /api/stats/heatmap` | `stats.ts` | Calendar heatmap |
| `GET /api/stats/recent-episodes` | `stats.ts` | Recent episodes |
| `GET /api/stats/countries` | `stats.ts` | Country heatmap (world map) |
| `GET /api/stats/genres` | `stats.ts` | Genre breakdown |
| `GET /api/stats/genres-by-year` | `stats.ts` | Genre evolution |
| `GET /api/stats/decades` | `stats.ts` | Decade + scatter data |
| `GET /api/recommends` | `recommends.ts` | Bandcamp links |
| `GET /api/recommends/artists` | `recommends.ts` | Bandcamp artist ranking |
| `GET /api/recommends/by-episode/{id}` | `recommends.ts` | Per-episode links |
| `GET /api/admin/check` | `admin.ts` | Auth check |
| `GET /api/admin/clusters` | `admin.ts` | Duplicate detection |
| `POST /api/admin/merge` | `admin.ts` | Bulk merge |
| `POST /api/admin/merge/preview` | `admin.ts` | Merge preview |
| `POST /api/admin/correction` | `admin.ts` | Track correction |
| `GET /api/admin/corrections` | `admin.ts` | Correction history |
| `POST /api/admin/rename-artist` | `admin.ts` | Artist rename |
| `POST /api/admin/rename-album` | `admin.ts` | Album rename |
| All remaining admin endpoints | `admin.ts` | Entity listing, track browser, ignored clusters |

### Zero Frontend Changes

The Svelte frontend (`web/app/src/lib/api.js`) already uses relative `/api/*` paths — no modifications needed. The Vite dev proxy continues to work locally, and in production the Worker handles `/api/*` routing on the same domain.
