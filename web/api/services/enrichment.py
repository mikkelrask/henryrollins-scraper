"""
Enrichment service — fetches artist metadata and album artwork from external APIs,
cached locally in enrichment.db for zero-cost repeat access.
"""

import json
import sqlite3
import time
import requests
from pathlib import Path
from typing import Optional

USER_AGENT = "HenryRollinsListensTo/1.0 (music analytics project)"

ENRICHMENT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "enrichment.db"
API_DELAY = 0.25


# ── Database setup ──

def get_db() -> sqlite3.Connection:
    ENRICHMENT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(ENRICHMENT_DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    _init_schema(db)
    return db


def _init_schema(db: sqlite3.Connection):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS artist_enrichment (
            artist_name TEXT PRIMARY KEY,
            mbid TEXT,
            country TEXT,
            formed_year INTEGER,
            genres TEXT,
            tags TEXT,
            bio_summary TEXT,
            wikipedia_url TEXT,
            last_fetched TEXT,
            fetch_count INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS album_art (
            album_name TEXT NOT NULL,
            artist_name TEXT NOT NULL,
            mbid TEXT,
            artwork_url TEXT,
            release_year INTEGER,
            release_date TEXT,
            last_fetched TEXT,
            PRIMARY KEY (album_name, artist_name)
        );
        CREATE INDEX IF NOT EXISTS idx_album_art_artist ON album_art(artist_name);
    """)

    # Migration: add release_date column if missing on existing tables
    try:
        db.execute("ALTER TABLE album_art ADD COLUMN release_date TEXT")
        db.commit()
    except sqlite3.OperationalError:
        pass  # column already exists

    db.commit()


# ── Artist enrichment ──

def _is_enriched(row: dict) -> bool:
    """Check if a cached row has full metadata (not just an MBID)."""
    return bool(row.get("country")) or bool(row.get("genres")) or bool(row.get("bio_summary"))


def get_artist_enrichment(artist_name: str, mbid: Optional[str] = None) -> dict:
    """Get enriched artist data. Returns cached data if available, otherwise
    fetches from MusicBrainz. Best-effort — never throws."""
    db = get_db()
    try:
        row = db.execute(
            "SELECT * FROM artist_enrichment WHERE artist_name = ?", (artist_name,)
        ).fetchone()

        if row:
            d = _row_to_dict(row)
            db.execute(
                "UPDATE artist_enrichment SET fetch_count = fetch_count + 1 WHERE artist_name = ?",
                (artist_name,),
            )
            db.commit()

            # If the cached row is incomplete (e.g. just an MBID from seeding),
            # try to fetch full metadata from MusicBrainz
            if not _is_enriched(d):
                data = _fetch_artist_from_musicbrainz(artist_name, d.get("mbid") or mbid)
                if data:
                    db.execute(
                        """UPDATE artist_enrichment SET
                           country=?, formed_year=?, genres=?, tags=?,
                           bio_summary=?, wikipedia_url=?, last_fetched=datetime('now')
                           WHERE artist_name=?""",
                        (
                            data.get("country"), data.get("formed_year"),
                            json.dumps(data.get("genres", [])),
                            json.dumps(data.get("tags", [])),
                            data.get("bio_summary"), data.get("wikipedia_url"),
                            artist_name,
                        ),
                    )
                    db.commit()
                    return data
                # MusicBrainz had no additional data — save empty arrays so we don't retry
                db.execute(
                    """UPDATE artist_enrichment SET genres='[]', tags='[]',
                       last_fetched=datetime('now') WHERE artist_name=?""",
                    (artist_name,),
                )
                db.commit()
                d["genres"] = []
                d["tags"] = []

            return d

        # No row at all — fetch fresh
        data = _fetch_artist_from_musicbrainz(artist_name, mbid)

        if data:
            db.execute(
                """INSERT OR REPLACE INTO artist_enrichment
                   (artist_name, mbid, country, formed_year, genres, tags, bio_summary, wikipedia_url, last_fetched)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (
                    artist_name, data.get("mbid"), data.get("country"),
                    data.get("formed_year"), json.dumps(data.get("genres", [])),
                    json.dumps(data.get("tags", [])), data.get("bio_summary"),
                    data.get("wikipedia_url"),
                ),
            )
            db.commit()
            return data

        # Still nothing — store minimal tombstone
        db.execute(
            "INSERT OR REPLACE INTO artist_enrichment (artist_name, mbid, genres, tags, last_fetched) VALUES (?, ?, '[]', '[]', datetime('now'))",
            (artist_name, mbid),
        )
        db.commit()
        return {"artist_name": artist_name, "mbid": mbid, "genres": [], "tags": []}
    finally:
        db.close()


def _fetch_artist_from_musicbrainz(artist_name: str, mbid: Optional[str] = None) -> Optional[dict]:
    try:
        if mbid:
            url = f"https://musicbrainz.org/ws/2/artist/{mbid}"
            params = {"fmt": "json", "inc": "genres+tags+aliases"}
        else:
            url = "https://musicbrainz.org/ws/2/artist"
            params = {"query": artist_name, "fmt": "json", "limit": 1, "inc": "genres+tags+aliases"}

        resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=8)
        if resp.status_code != 200:
            return None

        artist = resp.json().get("artists", [None])[0] if not mbid else resp.json()
        if not artist or not artist.get("id"):
            return None

        time.sleep(API_DELAY)

        bio = _fetch_wikipedia_bio(artist.get("name", artist_name))
        if bio:
            time.sleep(API_DELAY)

        return {
            "artist_name": artist_name,
            "mbid": artist.get("id"),
            "country": artist.get("country"),
            "formed_year": _parse_year(artist.get("life-span", {}).get("begin")),
            "genres": [g["name"] for g in artist.get("genres", [])],
            "tags": [t["name"] for t in artist.get("tags", [])],
            "bio_summary": bio,
            "wikipedia_url": f"https://en.wikipedia.org/wiki/{artist.get('name', '').replace(' ', '_')}" if bio else None,
        }
    except Exception:
        return None


def _fetch_wikipedia_bio(artist_name: str) -> Optional[str]:
    try:
        params = {
            "action": "query", "format": "json", "titles": artist_name,
            "prop": "extracts", "exintro": True, "explaintext": True, "redirects": 1,
        }
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php", params=params,
            headers={"User-Agent": USER_AGENT}, timeout=5,
        )
        if resp.status_code != 200:
            return None
        for page in resp.json().get("query", {}).get("pages", {}).values():
            if page.get("extract"):
                text = page["extract"].strip()
                para = text.split("\n")[0] if "\n" in text else text[:500]
                return para[:500]
        return None
    except Exception:
        return None


# ── Album artwork ──

CAA_250 = "https://coverartarchive.org/release/{mbid}/front-250"
CAA_500 = "https://coverartarchive.org/release/{mbid}/front-500"


def get_album_art(album_name: str, artist_name: str) -> dict:
    """Get artwork URL for an album. Returns cached data immediately;
    fetches from MusicBrainz + Cover Art Archive on first request (best-effort, fast timeouts)."""
    db = get_db()
    try:
        row = db.execute(
            "SELECT * FROM album_art WHERE album_name = ? AND artist_name = ?",
            (album_name, artist_name),
        ).fetchone()

        if row:
            d = _row_to_dict(row)
            # Reconstruct artwork URLs from MBID (no need to re-verify)
            if d.get("mbid"):
                d["artwork_url"] = CAA_250.format(mbid=d["mbid"])
            return d

        art_data = _fetch_album_art(album_name, artist_name)

        if art_data:
            db.execute(
                """INSERT OR REPLACE INTO album_art
                   (album_name, artist_name, mbid, artwork_url, release_year, release_date, last_fetched)
                   VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
                (album_name, artist_name, art_data.get("mbid"),
                 CAA_250.format(mbid=art_data["mbid"]),
                 art_data.get("release_year"), art_data.get("release_date")),
            )
            db.commit()
            return art_data

        db.execute(
            "INSERT OR REPLACE INTO album_art (album_name, artist_name, last_fetched) VALUES (?, ?, datetime('now'))",
            (album_name, artist_name),
        )
        db.commit()
        return {"album_name": album_name, "artist_name": artist_name}
    finally:
        db.close()


def _fetch_album_art(album_name: str, artist_name: str) -> Optional[dict]:
    """Search MusicBrainz for a release, return MBID + year.
    Cover Art Archive URL is constructed from MBID (no HEAD request needed)."""
    try:
        resp = requests.get(
            "https://musicbrainz.org/ws/2/release",
            params={
                "query": f'release:"{album_name}" AND artist:"{artist_name}"',
                "fmt": "json", "limit": 2,
                "inc": "genres+tags",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=5,
        )
        if resp.status_code != 200:
            return None

        releases = resp.json().get("releases", [])
        if not releases:
            return None

        release = releases[0]
        mbid = release.get("id")
        date = release.get("date") or ""
        year = _parse_year(date)

        if mbid:
            return {
                "album_name": album_name, "artist_name": artist_name,
                "mbid": mbid, "artwork_url": CAA_250.format(mbid=mbid),
                "release_year": year, "release_date": date or None,
            }
        return None
    except Exception:
        return None


# ── Album track listings (for unplayed tracks) ──

def get_album_tracklist(mbid: str) -> list[str]:
    """Fetch the full track listing for a release from MusicBrainz.
    Returns list of track titles. Best-effort, never throws."""
    try:
        url = f"https://musicbrainz.org/ws/2/release/{mbid}"
        params = {"fmt": "json", "inc": "recordings+artist-credits"}
        resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=8)
        if resp.status_code != 200:
            return []

        data = resp.json()
        tracks = []
        for medium in data.get("media", []):
            for track in medium.get("tracks", []):
                title = track.get("title", "").strip()
                if title:
                    tracks.append(track["title"])
        return tracks
    except Exception:
        return []


def get_played_track_titles(mbid: str, album_name: str, artist_name: str, db) -> set[str]:
    """Get the set of track titles actually played on the show for this album."""
    rows = db.execute(
        "SELECT DISTINCT title FROM tracks WHERE album = ? AND artist = ? AND title != ''",
        (album_name, artist_name),
    ).fetchall()
    return {r["title"] for r in rows}


# ── Helpers ──

def _parse_year(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    try:
        return int(date_str[:4])
    except (ValueError, TypeError):
        return None


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("genres", "tags"):
        if d.get(key) and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                d[key] = []
    return d
