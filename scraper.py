#!/usr/bin/env python3
"""
Scraper for Henry Rollins KCRW Radio Show track listings.

Scrapes monthly archive pages from https://www.henryrollins.com/radio
to extract episode broadcast info, track listings, and bandcamp links.

Stores data in both SQLite (for analytics) and JSON (for beets tagging).
"""

import argparse
import json
import difflib
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

BASE_URL = "https://www.henryrollins.com"
RADIO_URL = f"{BASE_URL}/radio"

OUTPUT_JSON = "episodes.json"
STATE_FILE = "scraper_state.json"
DB_DIR = Path("db")
DB_PATH = DB_DIR / "henryrollins.db"
DEFAULT_REQUEST_DELAY = 1.0  # be polite


# ---------------------------------------------------------------------------
# SQLite setup
# ---------------------------------------------------------------------------

def init_db(db_path: Path) -> sqlite3.Connection:
    """Create tables and return connection."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS episodes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            broadcast   INTEGER,
            url         TEXT UNIQUE NOT NULL,
            title       TEXT,
            date        TEXT,
            scraped_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS artists (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS albums (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            artist_id   INTEGER NOT NULL REFERENCES artists(id),
            name        TEXT NOT NULL,
            UNIQUE(artist_id, name)
        );

        CREATE TABLE IF NOT EXISTS tracks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_id  INTEGER NOT NULL REFERENCES episodes(id),
            hour        INTEGER NOT NULL,
            position    INTEGER NOT NULL,
            artist      TEXT NOT NULL,
            title       TEXT NOT NULL,
            album       TEXT,
            artist_id   INTEGER REFERENCES artists(id),
            album_id    INTEGER REFERENCES albums(id)
        );

        CREATE TABLE IF NOT EXISTS links (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_id  INTEGER NOT NULL REFERENCES episodes(id),
            url         TEXT NOT NULL,
            label       TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_tracks_episode     ON tracks(episode_id);
        CREATE INDEX IF NOT EXISTS idx_tracks_artist_id   ON tracks(artist_id);
        CREATE INDEX IF NOT EXISTS idx_tracks_album_id    ON tracks(album_id);
        CREATE INDEX IF NOT EXISTS idx_episodes_broadcast ON episodes(broadcast);
    """)
    # Migration: add mbid column to artists and albums if missing
    for table in ("artists", "albums"):
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN mbid TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# State persistence (what we've already scraped)
# ---------------------------------------------------------------------------

def load_state() -> dict[str, Any]:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"months_scraped": [], "latest_broadcast": 0}


def save_state(state: dict[str, Any]) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _archive_sort_key(label: str) -> str:
    try:
        dt = datetime.strptime(label, "%B %Y")
        return dt.strftime("%Y-%m")
    except ValueError:
        return "0000-00"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def get_soup(url: str, retries: int = 3) -> BeautifulSoup | None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as e:
            print(f"  Attempt {attempt + 1} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None


# ---------------------------------------------------------------------------
# Monthly archive discovery
# ---------------------------------------------------------------------------

def discover_monthly_archives() -> list[dict[str, str]]:
    """Extract monthly archive links from the radio page.

    Returns list of dicts with 'label' (e.g. 'May 2026') and 'url'.
    Sorted newest-first.
    """
    soup = get_soup(RADIO_URL)
    if not soup:
        print("FATAL: Could not fetch radio page.")
        sys.exit(1)

    archives: list[dict[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        # Archive links look like "May 2026", "April 2026", etc.
        if href.startswith("/on-the-radio-all?month=") and re.match(
            r"^[A-Z][a-z]+ \d{4}$", text
        ):
            full_url = urljoin(BASE_URL, href)
            archives.append({"label": text, "url": full_url})

    # Sort newest-first by parsing the label date
    archives.sort(key=lambda entry: _archive_sort_key(entry["label"]), reverse=True)
    return archives


# ---------------------------------------------------------------------------
# Episode / track parsing
# ---------------------------------------------------------------------------

def _extract_broadcast_number(text: str, url: str | None = None) -> int | None:
    m = re.search(r"RADIO BROADCAST\s*#(\d+)", text)
    if m:
        return int(m.group(1))
    # Fallback: extract from URL like /radio-broadcast-458-01-0718
    if url:
        m = re.search(r"/radio-broadcast-(\d+)-", url)
        if m:
            return int(m.group(1))
    return None


def _extract_episode_url(article: BeautifulSoup, base: str) -> str | None:
    """Find the episode permalink inside an article."""
    # Try the most specific link first (the one containing the broadcast number)
    for a in article.find_all("a", href=True):
        href = a["href"]
        if "radio-broadcast" in href:
            return urljoin(base, href)
    # Fallback: any on-the-radio-all link that isn't a monthly archive
    for a in article.find_all("a", href=True):
        href = a["href"]
        if "/on-the-radio-all/" in href and "?month=" not in href:
            return urljoin(base, href)
    return None


def _extract_date_from_url(url: str) -> str | None:
    """Try to get ISO date from URL path like /2026/5/8/..."""
    parsed = urlparse(url)
    m = re.search(r"/(\d{4})/(\d{1,2})/(\d{1,2})/", parsed.path)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None


def _parse_tracks_and_links(
    body_text: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Parse track listing and external links from episode body text.

    Returns:
        tracks: list of {hour, position, artist, title, album}
        bandcamp_links: list of {url, label}
    """
    tracks: list[dict[str, Any]] = []
    bandcamp_links: list[dict[str, str]] = []

    # ---- Extract Bandcamp links first ----
    for m in re.finditer(r"(https?://[^\s]+bandcamp\.com[^\s]*)", body_text):
        url = m.group(1).rstrip(".,;:!?)")
        bandcamp_links.append({"url": url, "label": ""})

    # ---- Normalise dashes ----
    text = body_text.replace("\u2013", "-").replace("\u2014", "--")

    # ---- Split into hour sections ----
    hour_sections: list[tuple[int, str]] = []

    hour_pattern = re.compile(r"^(Hour\s*[12])\s*$", re.MULTILINE | re.IGNORECASE)
    matches = list(hour_pattern.finditer(text))

    if len(matches) >= 1:
        for i, m in enumerate(matches):
            hour_num = int(re.search(r"[12]", m.group(1)).group())
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            hour_sections.append((hour_num, text[start:end]))
    else:
        # No hour markers — treat the entire body as hour=0
        hour_sections.append((0, text))

    # ---- Parse numbered tracks ----
    # Pattern:  NN. Artist - Title / Album
    # Greedy before the last slash handles titles with w/ feat. artist
    track_re = re.compile(
        r"^\s*(\d+)\s*\.\s+(.*?)\s*-\s+(.*)\s*/\s*(.*?)\s*$", re.MULTILINE
    )

    for hour_num, section in hour_sections:
        for tm in track_re.finditer(section):
            full_line = tm.group(0)
            slash_count = full_line.count("/")
            if slash_count > 3:
                print(f"  ⚠ Many slashes ({slash_count}) in: {full_line.strip()[:120]}...")

            position = int(tm.group(1))
            artist = tm.group(2).strip()
            title = tm.group(3).strip()
            album = tm.group(4).strip()

            if artist and title:
                tracks.append({
                    "hour": hour_num,
                    "position": position,
                    "artist": artist,
                    "title": title,
                    "album": album,
                })

    return tracks, bandcamp_links


def parse_episode_article(
    article: BeautifulSoup, base_url: str
) -> dict[str, Any] | None:
    """Parse a single <article> element into an episode dict."""
    entry = article.find("div", class_="entry-content")
    if not entry:
        return None

    body_text = entry.get_text(separator="\n", strip=True)
    if not body_text:
        return None

    episode_url = _extract_episode_url(article, base_url)
    broadcast = _extract_broadcast_number(body_text, episode_url)
    date = _extract_date_from_url(episode_url) if episode_url else None

    tracks, bandcamp_links = _parse_tracks_and_links(body_text)

    return {
        "broadcast": broadcast,
        "url": episode_url or "",
        "date": date or "",
        "title": f"Radio Broadcast #{broadcast}" if broadcast else "Untitled Episode",
        "tracks": tracks,
        "bandcamp_links": bandcamp_links,
    }


# ---------------------------------------------------------------------------
# SQLite persistence
# ---------------------------------------------------------------------------

from web.api.services import enrichment
from web.api.services.enrichment import get_artist_enrichment, get_album_art

# ...


def _trigram_similarity(a: str, b: str) -> float:
    """Simple trigram overlap similarity for fuzzy name matching.
    Normalizes punctuation first so 'X-Ray' and 'X Ray' score 1.0."""
    def norm(s: str) -> str:
        s = s.lower().strip()
        s = re.sub(r"[^\w\s]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s
    def trigrams(s: str):
        return {s[i:i+3] for i in range(len(s) - 2)}
    na, nb = norm(a), norm(b)
    if na == nb:
        return 1.0
    ta, tb = trigrams(na), trigrams(nb)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _find_similar_artist(conn: sqlite3.Connection, name: str, threshold: float = 0.65) -> dict | None:
    """Search existing artists for a name that is a strong trigram match.
    Returns {id, name} or None."""
    norm_name = _normalize(name)
    rows = conn.execute("SELECT id, name FROM artists").fetchall()
    best = None
    best_score = 0.0
    for row in rows:
        # Fast exact match on normalized form
        if _normalize(row["name"]) == norm_name:
            return {"id": row["id"], "name": row["name"]}
        score = _trigram_similarity(name, row["name"])
        if score > best_score:
            best_score = score
            best = {"id": row["id"], "name": row["name"]}
    if best and best_score >= threshold:
        return best
    return None


def _find_similar_album(conn: sqlite3.Connection, name: str, artist_id: int, threshold: float = 0.65) -> dict | None:
    """Search existing albums for the same artist that are strong trigram matches."""
    norm_name = _normalize(name)
    rows = conn.execute("SELECT id, name FROM albums WHERE artist_id = ?", (artist_id,)).fetchall()
    best = None
    best_score = 0.0
    for row in rows:
        if _normalize(row["name"]) == norm_name:
            return {"id": row["id"], "name": row["name"]}
        score = _trigram_similarity(name, row["name"])
        if score > best_score:
            best_score = score
            best = {"id": row["id"], "name": row["name"]}
    if best and best_score >= threshold:
        return best
    return None


def store_episode(conn: sqlite3.Connection, ep: dict[str, Any]) -> int | None:
    """Insert episode + its tracks + bandcamp links into DB using MBID-based canonicalization."""
    # Deduplicate by broadcast number or URL
    if ep["broadcast"]:
        existing = conn.execute("SELECT id FROM episodes WHERE broadcast = ?", (ep["broadcast"],)).fetchone()
        if existing: return None
    elif ep["url"]:
        existing = conn.execute("SELECT id FROM episodes WHERE url = ?", (ep["url"],)).fetchone()
        if existing: return None

    cursor = conn.execute("INSERT OR IGNORE INTO episodes (broadcast, url, title, date) VALUES (?, ?, ?, ?)",
                          (ep["broadcast"], ep["url"], ep["title"], ep["date"]))
    episode_id = cursor.lastrowid
    if episode_id is None: return None

    for trk in ep["tracks"]:
        raw_artist = trk["artist"]
        raw_album = trk.get("album", "")

        # 1. Resolve Canonical Artist via MBID
        art_meta = get_artist_enrichment(raw_artist)
        artist_mbid = art_meta.get("mbid")
        canonical_artist = art_meta.get("canonical_name") or raw_artist

        # Deduplicate by MBID first, then by canonical name
        artist_id = None
        if artist_mbid:
            existing = conn.execute(
                "SELECT id, name FROM artists WHERE mbid = ?", (artist_mbid,)
            ).fetchone()
            if existing:
                artist_id = existing["id"]
                canonical_artist = existing["name"]

        if not artist_id:
            # Fallback: fuzzy match against existing artists when MB fails us
            similar = _find_similar_artist(conn, canonical_artist)
            if similar:
                artist_id = similar["id"]
                canonical_artist = similar["name"]
            else:
                conn.execute(
                    "INSERT OR IGNORE INTO artists (name, mbid) VALUES (?, ?)",
                    (canonical_artist, artist_mbid)
                )
                row = conn.execute(
                    "SELECT id FROM artists WHERE name = ?", (canonical_artist,)
                ).fetchone()
                artist_id = row["id"] if row else None

        # 2. Resolve Canonical Album via MBID
        album_id = None
        canonical_album = raw_album
        if raw_album and artist_id:
            alb_meta = get_album_art(raw_album, canonical_artist)
            album_mbid = alb_meta.get("mbid")
            canonical_album = alb_meta.get("canonical_name") or raw_album

            if album_mbid:
                existing = conn.execute(
                    "SELECT id, name FROM albums WHERE mbid = ?", (album_mbid,)
                ).fetchone()
                if existing:
                    album_id = existing["id"]
                    canonical_album = existing["name"]

            if not album_id:
                similar = _find_similar_album(conn, canonical_album, artist_id)
                if similar:
                    album_id = similar["id"]
                    canonical_album = similar["name"]
                else:
                    conn.execute(
                        "INSERT OR IGNORE INTO albums (artist_id, name, mbid) VALUES (?, ?, ?)",
                        (artist_id, canonical_album, album_mbid)
                    )
                    row = conn.execute(
                        "SELECT id FROM albums WHERE artist_id = ? AND name = ?",
                        (artist_id, canonical_album)
                    ).fetchone()
                    album_id = row["id"] if row else None

            # Write full album enrichment to main DB
            conn.execute("""INSERT OR REPLACE INTO album_art
                (album_name, artist_name, mbid, release_group_mbid, canonical_name,
                 artwork_url, release_year, release_date, last_fetched, total_tracks, tracklist)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?)""",
                (raw_album, canonical_artist,
                 alb_meta.get("mbid"),
                 alb_meta.get("release_group_mbid"),
                 alb_meta.get("canonical_name"),
                 alb_meta.get("artwork_url"),
                 alb_meta.get("release_year"),
                 alb_meta.get("release_date"),
                 alb_meta.get("total_tracks"),
                 json.dumps(alb_meta.get("tracklist")) if alb_meta.get("tracklist") else None))

        # Write full artist enrichment to main DB (done after album lookups
        # so canonical_artist is finalised)
        conn.execute("""INSERT OR REPLACE INTO artist_enrichment
            (artist_name, mbid, canonical_name, country, formed_year, genres, tags,
             bio_summary, wikipedia_url, lastfm_tags, lastfm_bio, lastfm_listeners,
             lastfm_playcount, lastfm_url, last_fetched)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (raw_artist,
             art_meta.get("mbid"),
             art_meta.get("canonical_name"),
             art_meta.get("country"),
             art_meta.get("formed_year"),
             json.dumps(art_meta.get("genres", [])),
             json.dumps(art_meta.get("tags", [])),
             art_meta.get("bio_summary"),
             art_meta.get("wikipedia_url"),
             json.dumps(art_meta.get("lastfm_tags", [])),
             art_meta.get("lastfm_bio"),
             art_meta.get("lastfm_listeners"),
             art_meta.get("lastfm_playcount"),
             art_meta.get("lastfm_url")))

        conn.execute("""INSERT INTO tracks (episode_id, hour, position, artist, title, album, artist_id, album_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                     (episode_id, trk["hour"], trk["position"], canonical_artist, trk["title"], canonical_album, artist_id, album_id))

    # Dedup track titles against cached MB tracklists for albums touched by this episode
    _dedup_episode_tracks(conn, episode_id)

    for lnk in ep.get("bandcamp_links", []):
        conn.execute(
            "INSERT INTO links (episode_id, url, label) VALUES (?, ?, ?)",
            (episode_id, lnk["url"], lnk.get("label", "")),
        )

    return episode_id


def _dedup_episode_tracks(conn: sqlite3.Connection, episode_id: int) -> None:
    """Normalize track titles for albums touched by this episode.
    Phase 1: match against cached MB tracklists.
    Phase 2: merge same-album variants that normalize to the same string.
    """
    albums = conn.execute("""
        SELECT DISTINCT t.artist, t.album
        FROM tracks t WHERE t.episode_id = ? AND t.album != ''
    """, (episode_id,)).fetchall()
    for row in albums:
        artist, album = row["artist"], row["album"]

        # Phase 1: MB-based dedup
        aa = conn.execute("""
            SELECT tracklist FROM album_art
            WHERE artist_name = ? AND album_name = ? AND tracklist IS NOT NULL
        """, (artist, album)).fetchone()
        if aa:
            mb_tracks = json.loads(aa["tracklist"])
            playeds = conn.execute(
                "SELECT DISTINCT title FROM tracks WHERE album = ? AND artist = ? AND title != ''",
                (album, artist),
            ).fetchall()
            mb_norm = {}
            for t in mb_tracks:
                n = enrichment.norm_track(t)
                if n not in mb_norm:
                    mb_norm[n] = t
            for pt in playeds:
                pt_title = pt["title"]
                pt_norm = enrichment.norm_track(pt_title)
                canonical = None
                if pt_norm in mb_norm:
                    canonical = mb_norm[pt_norm]
                else:
                    best, best_score = None, 0
                    for n, t in mb_norm.items():
                        score = difflib.SequenceMatcher(None, pt_norm, n).ratio()
                        if score > best_score:
                            best, best_score = t, score
                    if best_score >= 0.75:
                        canonical = best
                if canonical and canonical != pt_title:
                    conn.execute(
                        "UPDATE tracks SET title = ? WHERE title = ? AND album = ? AND artist = ?",
                        (canonical, pt_title, album, artist),
                    )

        # Phase 2: intra-album dedup — merge variants that normalize identically
        titles = conn.execute(
            "SELECT title, COUNT(*) AS cnt FROM tracks WHERE album = ? AND artist = ? AND title != '' GROUP BY title",
            (album, artist),
        ).fetchall()
        norm_groups: dict[str, list[tuple[str, int]]] = {}
        for t in titles:
            n = enrichment.norm_track(t["title"])
            norm_groups.setdefault(n, []).append((t["title"], t["cnt"]))
        for n, group in norm_groups.items():
            if len(group) > 1:
                # Pick most frequent variant as canonical
                canonical = max(group, key=lambda x: x[1])[0]
                for variant, _ in group:
                    if variant != canonical:
                        conn.execute(
                            "UPDATE tracks SET title = ? WHERE title = ? AND album = ? AND artist = ?",
                            (canonical, variant, album, artist),
                        )
        conn.commit()


# ---------------------------------------------------------------------------
# Normalisation (shared with tagger / cache builder)
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Basic normalisation for matching."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"\(.*?\)", "", text)
    text = text.replace("&", "and")
    text = text.replace("/", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Export to JSON (for beets tagger compatibility)
# ---------------------------------------------------------------------------

def export_json(conn: sqlite3.Connection, path: str) -> None:
    """Export episodes to JSON in the same format as cww-scraper."""
    rows = conn.execute(
        "SELECT id, broadcast, url, title, date FROM episodes ORDER BY broadcast DESC"
    ).fetchall()

    episodes = []
    for row in rows:
        track_rows = conn.execute(
            """SELECT hour, position, artist, title, album
               FROM tracks WHERE episode_id = ?
               ORDER BY hour, position""",
            (row["id"],),
        ).fetchall()

        tracklist = [
            {
                "track": t["title"],
                "artist": t["artist"],
                "album": t["album"],
                "hour": t["hour"],
                "position": t["position"],
            }
            for t in track_rows
        ]

        link_rows = conn.execute(
            "SELECT url, label FROM links WHERE episode_id = ?", (row["id"],)
        ).fetchall()
        bandcamp_links = [{"url": l["url"], "label": l["label"]} for l in link_rows]

        episodes.append({
            "url": row["url"],
            "broadcast": row["broadcast"],
            "date": row["date"],
            "tracklist": tracklist,
            "bandcamp_links": bandcamp_links,
        })

    with open(path, "w", encoding="utf-8") as f:
        json.dump(episodes, f, indent=2, ensure_ascii=False)

    print(f"Exported {len(episodes)} episodes to {path}")


# ---------------------------------------------------------------------------
# Main scrape flow
# ---------------------------------------------------------------------------

def scrape_all(
    conn: sqlite3.Connection,
    delay: float = DEFAULT_REQUEST_DELAY,
    limit_months: int = 0,
    resume: bool = True,
    refresh_months: int = 2,
) -> None:
    """Scrape all monthly archives and store episodes."""
    state = load_state() if resume else {"months_scraped": [], "latest_broadcast": 0}
    already_scraped_months = set(state.get("months_scraped", []))

    print("Discovering monthly archives from radio page...")
    archives = discover_monthly_archives()
    print(f"Found {len(archives)} monthly archive pages (newest first)\n")

    if limit_months > 0:
        archives = archives[:limit_months]
        print(f"Limited to {limit_months} months\n")

    total_new_eps = 0
    total_new_tracks = 0
    latest_broadcast = state.get("latest_broadcast", 0)

    for arch_index, arch in enumerate(tqdm(archives, desc="Months", unit="month", ncols=80)):
        label = arch["label"]
        should_refresh = resume and arch_index < refresh_months
        if label in already_scraped_months and resume and not should_refresh:
            continue

        print(f"\n--- {label} ---")
        soup = get_soup(arch["url"])
        if not soup:
            print(f"  SKIP (failed to fetch)")
            continue

        articles = soup.find_all("article")
        if not articles:
            print(f"  No articles found")
            continue

        month_new = 0
        for art in articles:
            ep = parse_episode_article(art, BASE_URL)
            if ep is None:
                continue

            # Skip episodes with no broadcast number AND no tracks
            if ep["broadcast"] is None and not ep["tracks"]:
                continue

            ep_id = store_episode(conn, ep)
            if ep_id is not None:
                month_new += 1
                total_new_eps += 1
                total_new_tracks += len(ep["tracks"])
                if ep["broadcast"] and ep["broadcast"] > latest_broadcast:
                    latest_broadcast = ep["broadcast"]

                # Print first couple of tracks as confirmation
                first_tracks = ep["tracks"][:2]
                track_preview = "; ".join(
                    f"{t['artist']} - {t['title']}" for t in first_tracks
                )
                ellipsis = " …" if len(ep["tracks"]) > 2 else ""
                print(
                    f"  + #{ep['broadcast']} ({ep['date']}) "
                    f"{len(ep['tracks'])} tracks — "
                    f"{track_preview}{ellipsis}"
                )

        if month_new > 0:
            already_scraped_months.add(label)
            conn.commit()

        time.sleep(delay)

    # Final commit and save state
    conn.commit()

    state["months_scraped"] = sorted(already_scraped_months, key=_archive_sort_key, reverse=True)
    state["latest_broadcast"] = latest_broadcast
    save_state(state)

    print(f"\n{'='*60}")
    print(f"Scrape complete!")
    print(f"  New episodes:  {total_new_eps}")
    print(f"  New tracks:    {total_new_tracks}")
    print(f"  Latest broadcast: #{latest_broadcast}")
    print(f"{'='*60}")

    # Export JSON for the tagger
    export_json(conn, OUTPUT_JSON)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Henry Rollins KCRW radio show track listings"
    )
    parser.add_argument(
        "--limit-months",
        type=int,
        default=0,
        help="Only scrape this many most-recent months (0 = all)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore state file and re-scrape everything",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_REQUEST_DELAY,
        help=f"Delay between requests in seconds (default {DEFAULT_REQUEST_DELAY})",
    )
    parser.add_argument(
        "--refresh-months",
        type=int,
        default=2,
        help="Always re-check this many newest archive months when resuming (default 2)",
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Just re-export JSON from existing DB, don't scrape",
    )
    args = parser.parse_args()

    conn = init_db(DB_PATH)

    if args.export_only:
        export_json(conn, OUTPUT_JSON)
        conn.close()
        return

    scrape_all(
        conn,
        delay=args.delay,
        limit_months=args.limit_months,
        resume=not args.no_resume,
        refresh_months=max(0, args.refresh_months),
    )
    conn.close()


if __name__ == "__main__":
    main()
