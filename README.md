# Fanatic 📻

**Henry Rollins Radio Scraper** — extracts track listings from [Henry Rollins' KCRW radio show](https://www.henryrollins.com/radio), two hours of fanatic-level deep cuts every Friday.

| Component | URL | Stack |
|-----------|-----|-------|
| **Frontend** | https://fanatic.raske.xyz | Svelte 5 + Tailwind + D3 |
| **API** | https://henryrollins-api.terminal-share.workers.dev | Hono + D1 (TypeScript) |
| **Database** | Cloudflare D1 | SQLite (5.4 MB, 11 tables) |

## What it does

- **Scrapes** all monthly archive pages from `henryrollins.com/radio` (back to 2017)
- **Parses** each episode's track listing (Hour 1 / Hour 2, numbered tracks with artist/title/album)
- **Extracts** Bandcamp links separately (Henry shares a lot of them)
- **Stores** everything in SQLite for analytics
- **Resolves** artist names against MusicBrainz via `build_artist_cache.py`
- **Enriches** artists with country, formed year, genres, tags, and bios from MusicBrainz / Last.fm / Wikipedia
- **Tags** your local beets library with the `FANATIC` genre via `add_fanatic_genre.py`
- **Deploys** the full stack to Cloudflare (Pages + D1 + Workers)

## Architecture

```
                     ┌───────────────────────────────┐
                     │    Cloudflare Pages            │
                     │  ┌─────────────────────────┐   │
                     │  │  Svelte 5 App           │   │
                     │  │  (web/app/dist/)        │   │
                     │  └────────┬────────────────┘   │
                     │  /api/*   │ Pages Function      │
                     │  ┌────────▼────────────────┐   │
                     │  │  Hono API Worker         │   │
                     │  │  (TypeScript, 38 routes) │   │
                     │  └────────┬────────────────┘   │
                     └───────────┼────────────────────┘
                                │ env.DB
                     ┌──────────▼──────────┐
                     │  D1: henryrollins    │
                     │  11 tables, 5.4 MB   │
                     │  ~34K rows total     │
                     └──────────────────────┘

Scraping / enrichment happen locally (Python). Only the data is pushed to
the cloud — zero external API calls at request time.
```

## Quick Start (Local Dev)

### Setup

```bash
# Python environment
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Frontend
cd web/app && npm install
```

### Run locally

```bash
# Terminal 1: Python API backend
cd web/api && uvicorn main:app --reload --port 8000

# Terminal 2: Svelte dev server (proxies /api → localhost:8000)
cd web/app && npm run dev
```

The Svelte dev proxy routes `/api/*` to the Python backend, so the frontend
works identically to production — just open `localhost:5173`.

### Scraping

```bash
# Full historical scrape (back to 2017)
./scraper

# Just the most recent 3 months
./scraper --limit-months 3

# Re-export JSON from existing database without re-scraping
./scraper --export-only
```

### Analytics

```bash
# Show summary stats
./analytics

# Top 20 most-played artists
./analytics top-artists

# Search for a specific artist
./analytics artist "Wire"

# All bandcamp links
./analytics bandcamp-links
```

## Deploying to Cloudflare

The full stack (Worker + Pages + D1) runs on Cloudflare. Deploying pushes
locally scraped + enriched data up without making any API calls from the
Worker itself.

### Prerequisites

```bash
# Authenticate wrangler (one-time)
cd worker && npx wrangler login

# Create the D1 database (one-time — if not already done)
npx wrangler d1 create henryrollins
# Then paste the database_id into worker/wrangler.toml

# Set the admin API key (one-time)
echo "your-secret-key" | npx wrangler secret put ADMIN_API_KEY
```

### Full deploy

```bash
# Scrape → enrich → export → push D1 → deploy Worker → deploy Pages
./scripts/deploy.sh --scrape
```

Or step by step:

```bash
# 1. Scrape new episodes
./scraper

# 2. Build artist cache + enrich all artists/albums
./build-cache
python3 scripts/seed-enrichment.py --all

# 3. Merge enrichment into main DB
sqlite3 db/henryrollins.db < scripts/merge-enrichment.sql

# 4. Export to D1 SQL seed + push to Cloudflare
python3 scripts/generate-d1-seed.py seed.sql
cd worker
npx wrangler d1 execute henryrollins --remote --file=../seed.sql

# 5. Deploy API Worker
npx wrangler deploy

# 6. Deploy frontend to Pages
cd ../web/app
npx wrangler pages deploy dist --project-name=fanatic --branch=main
```

### Quick re-deploy (no new data)

```bash
# Just re-deploy Worker + Pages (skip scrape, enrichment, D1)
cd worker && npx wrangler deploy
cd ../web/app && npx wrangler pages deploy dist --project-name=fanatic --branch=main
```

## Admin Panel

The admin panel is at https://fanatic.raske.xyz/#/admin. It's gated by an
API key sent as the `x-admin-key` header.

The key is set via `wrangler secret put ADMIN_API_KEY` and is also stored
locally in `.env` and `worker/.dev.vars`.

To use the admin API directly:

```bash
curl -H 'x-admin-key: your-secret-key' \
  https://fanatic.raske.xyz/api/admin/entities
```

## Cron Automation

Add this to your crontab to check for new episodes weekly:

```cron
# Scrape new Henry Rollins episodes every Monday at 9am
0 9 * * 1 cd /path/to/henryrollins-scraper && ./scraper

# For full deploy pipeline on a schedule (if you want auto-publish)
# 30 9 * * 1 cd /path/to/henryrollins-scraper && ./scripts/deploy.sh
```

## Data Schema (SQLite)

```sql
episodes           — id, broadcast (#NNN), url, date, scraped_at
tracks             — id, episode_id, hour (1|2), position, artist, title, album,
                     artist_norm, title_norm
artists            — artist (normalized name), episode_count, track_count
albums             — artist, album (normalized), plays, first_seen, last_seen
links              — id, episode_id, url, label (bandcamp links, etc.)
artist_enrichment  — artist_name, mbid, country, formed_year, genres, tags,
                     bio_summary, wikipedia_url, lastfm_tags, lastfm_bio,
                     lastfm_listeners, lastfm_playcount, lastfm_url
album_art          — album_name, artist_name, mbid, artwork_url, release_year
corrections        — track_id, episode_id, type, original_data, corrected_data
release_group_cache — rg_mbid, data, fetched_at
```

## How Parsing Works

The scraper fetches monthly archive pages (`/on-the-radio-all?month=MM-YYYY`),
which contain full track listings for every episode that month. Each `<article>`
element is parsed for:

1. **Broadcast number** from the `RADIO BROADCAST #NNN` header
2. **URL** from the episode permalink
3. **Hour markers** (`Hour 1`, `Hour 2`) to split the track listing
4. **Numbered tracks** matching the pattern: `NN. Artist - Title / Album`
5. **Bandcamp links** via URL pattern matching

Non-music content (commentary, recommendations, links) is naturally filtered
out since it doesn't match the numbered track pattern.

## Local Files

```
henryrollins-scraper/
├── scraper              — Compiled scraper binary
├── scraper.py           — Python scraper source
├── build-cache          — Artist cache builder (binary)
├── build_artist_cache.py
├── analytics.py         — CLI analytics queries
├── db/
│   └── henryrollins.db  — Main SQLite database
├── web/
│   ├── app/             — Svelte 5 frontend
│   └── api/             — Python FastAPI (local dev only)
├── worker/              — Hono + D1 API Worker
├── scripts/
│   ├── deploy.sh        — Full deployment pipeline
│   ├── generate-d1-seed.py  — DB → D1-safe SQL export
│   ├── seed-enrichment.py   — Offline enrichment runner
│   └── merge-enrichment.sql — Enrichment table DDL
├── .env                 — ADMIN_API_KEY (local copy)
└── worker/.dev.vars     — ADMIN_API_KEY for wrangler dev
```
