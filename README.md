# Henry Rollins Radio Scraper 📻

A Python web scraper that extracts track listings from [Henry Rollins' KCRW radio show](https://www.henryrollins.com/radio) — two hours of fanatic-level deep cuts every Friday.

This project is built as a companion to the [cww-scraper](https://github.com/your-org/cww-scraper) (Chances With Wolves), sharing the same MusicBrainz resolution and beets tagging architecture.

## What it does

- **Scrapes** all monthly archive pages from `henryrollins.com/radio` (back to 2017)
- **Parses** each episode's track listing (Hour 1 / Hour 2, numbered tracks with artist/title/album)
- **Extracts** Bandcamp links separately (Henry shares a lot of them)
- **Stores** everything in SQLite for analytics + JSON for beets tagging
- **Resolves** artist names against MusicBrainz via `build_artist_cache.py`
- **Tags** your local beets library with the `FANATIC` genre via `add_fanatic_genre.py`
- **Tracks** incremental state so subsequent runs only fetch new episodes

## Requirements

- Python 3.10+
- `uv` (recommended for venv)
- `beets` (for tagging)
- (Optional) MusicBrainz user agent for artist resolution

## Setup

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

Copy and edit the environment file (needed for MusicBrainz lookups):

```bash
cp .env.example .env
# Edit .env with your MusicBrainz User-Agent
```

## Usage

### 1. Scrape episodes

```bash
# Full historical scrape (back to 2017)
./scraper

# Just the most recent 3 months
./scraper --limit-months 3

# Re-export JSON from existing database without re-scraping
./scraper --export-only
```

The scraper stores data in:
- `db/henryrollins.db` — SQLite database (primary store, for analytics)
- `episodes.json` — JSON export (for beets tagger)
- `scraper_state.json` — tracks which months have been scraped

### 2. Build artist cache

```bash
# Resolve artists via beets library (fast) + MusicBrainz API (fallback)
./build-cache
```

### 3. Tag your beets library

```bash
# Preview what would be tagged
./tagger --dry-run

# Apply FANATIC genre tag
./tagger
```

### 4. Analytics queries

```bash
# Show summary stats
./analytics

# Top 20 most-played artists
./analytics top-artists

# Top 30 most-played artists
./analytics top-artists --limit 30

# Search for a specific artist
./analytics artist "Wire"

# Track count per episode
./analytics per-episode

# All bandcamp links
./analytics bandcamp-links
```

### 5. Cron automation

Add this to your crontab to check for new episodes weekly (the show airs Fridays):

```cron
# Check for new Henry Rollins episodes every Monday at 9am
0 9 * * 1 cd /path/to/henryrollins-scraper && ./scraper
```

## Data schema (SQLite)

```sql
episodes — id, broadcast (#NNN), url, date, scraped_at
tracks   — id, episode_id, hour (1|2), position, artist, title, album,
           artist_norm, title_norm
links    — id, episode_id, url, label        (bandcamp links, etc.)
```

## How parsing works

The scraper fetches monthly archive pages (`/on-the-radio-all?month=MM-YYYY`), which contain full track listings for every episode that month. Each `<article>` element is parsed for:

1. **Broadcast number** from the `RADIO BROADCAST #NNN` header
2. **URL** from the episode permalink
3. **Hour markers** (`Hour 1`, `Hour 2`) to split the track listing
4. **Numbered tracks** matching the pattern: `NN. Artist - Title / Album`
5. **Bandcamp links** via URL pattern matching

Non-music content (commentary, recommendations, links) is naturally filtered out since it doesn't match the numbered track pattern.

## Related

- [cww-scraper](https://github.com/your-org/cww-scraper) — Same architecture for Chances With Wolves radio show
- [HenryRollins.com](https://www.henryrollins.com/radio) — The show page
