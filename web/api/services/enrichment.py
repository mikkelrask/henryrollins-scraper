"""
Enrichment service — fetches artist metadata and album artwork from external APIs,
cached locally in enrichment.db for zero-cost repeat access.
"""

import json
import re
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
        CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER,
            episode_id INTEGER,
            type TEXT NOT NULL,
            original_data TEXT,
            corrected_data TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(track_id) REFERENCES tracks(id),
            FOREIGN KEY(episode_id) REFERENCES episodes(id)
        );
    """)

    # Migration: add release_date column if missing on existing tables
    try:
        db.execute("ALTER TABLE album_art ADD COLUMN release_date TEXT")
        db.commit()
    except sqlite3.OperationalError:
        pass  # column already exists

    # Migration: add release_group_mbid column
    try:
        db.execute("ALTER TABLE album_art ADD COLUMN release_group_mbid TEXT")
        db.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: add canonical_name columns
    for table, col in (("artist_enrichment", "canonical_name"), ("album_art", "canonical_name")):
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
            db.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

    # Migration: add Last.fm columns
    for col in ("lastfm_tags", "lastfm_bio", "lastfm_listeners", "lastfm_playcount", "lastfm_url"):
        try:
            db.execute(f"ALTER TABLE artist_enrichment ADD COLUMN {col} TEXT")
            db.commit()
        except sqlite3.OperationalError:
            pass

    db.commit()


# ── Artist enrichment ──

def _is_enriched(row: dict) -> bool:
    """Check if a cached row has full metadata (not just an MBID)."""
    return bool(row.get("country")) or bool(row.get("genres")) or bool(row.get("bio_summary"))


# ── Last.fm credentials ──
LASTFM_API_KEY = "567f2d048cd656f13ba13202a253c90e"


def _fetch_artist_from_lastfm(artist_name: str) -> Optional[dict]:
    """Fetch artist info from Last.fm. Best-effort, never throws."""
    try:
        import urllib.request
        import urllib.parse
        query = urllib.parse.urlencode({
            "method": "artist.getinfo",
            "artist": artist_name,
            "api_key": LASTFM_API_KEY,
            "format": "json",
        })
        url = f"https://ws.audioscrobbler.com/2.0/?{query}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        artist = data.get("artist")
        if not artist:
            return None

        tags = []
        tag_data = artist.get("tags", {})
        if tag_data:
            tag_list = tag_data.get("tag", [])
            if isinstance(tag_list, dict):
                tag_list = [tag_list]
            tags = [t["name"] for t in tag_list if isinstance(t, dict) and "name" in t]

        stats = artist.get("stats", {})
        bio = artist.get("bio", {})
        bio_summary = bio.get("summary", "") or ""
        # Strip Last.fm "Read more" links
        bio_summary = re.sub(r'<a href="https?://www\.last\.fm[^"]*"[^>]*>.*?</a>', '', bio_summary).strip()

        return {
            "lastfm_tags": tags,
            "lastfm_bio": bio_summary[:800] if bio_summary else None,
            "lastfm_listeners": int(stats["listeners"]) if stats.get("listeners") else None,
            "lastfm_playcount": int(stats["playcount"]) if stats.get("playcount") else None,
            "lastfm_url": artist.get("url"),
        }
    except Exception:
        return None


def get_artist_enrichment(artist_name: str, mbid: Optional[str] = None) -> dict:
    """Get enriched artist data. Returns cached data if available, otherwise
    fetches from MusicBrainz. Best-effort - never throws."""
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

            # Backfill MusicBrainz core data (mbid, country, formed_year)
            # regardless of enrichment status — this ensures country is populated
            if not d.get("mbid") or not d.get("country"):
                data = _fetch_artist_from_musicbrainz(artist_name, d.get("mbid") or mbid)
                if data:
                    db.execute(
                        """UPDATE artist_enrichment SET
                           mbid=COALESCE(?, mbid), canonical_name=COALESCE(?, canonical_name),
                           country=COALESCE(?, country), formed_year=COALESCE(?, formed_year),
                           genres=COALESCE(?, genres), tags=COALESCE(?, tags),
                           bio_summary=COALESCE(?, bio_summary), wikipedia_url=COALESCE(?, wikipedia_url),
                           last_fetched=datetime('now')
                           WHERE artist_name=?""",
                        (
                            data.get("mbid"), data.get("canonical_name"),
                            data.get("country"), data.get("formed_year"),
                            json.dumps(data.get("genres", [])),
                            json.dumps(data.get("tags", [])),
                            data.get("bio_summary"), data.get("wikipedia_url"),
                            artist_name,
                        ),
                    )
                    db.commit()
                    # Merge non-None values into d
                    for k, v in data.items():
                        if v is not None and (d.get(k) is None or d.get(k) == []):
                            d[k] = v

            # Backfill bio/tags from MusicBrainz if still missing
            if not _is_enriched(d):
                data = _fetch_artist_from_musicbrainz(artist_name, d.get("mbid") or mbid)
                if data:
                    db.execute(
                        """UPDATE artist_enrichment SET
                           mbid=COALESCE(?, mbid), canonical_name=COALESCE(?, canonical_name),
                           country=COALESCE(?, country), formed_year=COALESCE(?, formed_year),
                           genres=COALESCE(?, genres), tags=COALESCE(?, tags),
                           bio_summary=COALESCE(?, bio_summary), wikipedia_url=COALESCE(?, wikipedia_url),
                           last_fetched=datetime('now')
                           WHERE artist_name=?""",
                        (
                            data.get("mbid"), data.get("canonical_name"),
                            data.get("country"), data.get("formed_year"),
                            json.dumps(data.get("genres", [])),
                            json.dumps(data.get("tags", [])),
                            data.get("bio_summary"), data.get("wikipedia_url"),
                            artist_name,
                        ),
                    )
                    db.commit()
                    for k, v in data.items():
                        if v is not None and (d.get(k) is None or d.get(k) == []):
                            d[k] = v
                else:
                    db.execute(
                        """UPDATE artist_enrichment SET genres='[]', tags='[]',
                           last_fetched=datetime('now') WHERE artist_name=?""",
                        (artist_name,),
                    )
                    db.commit()
                    d["genres"] = []
                    d["tags"] = []

            # Always try Last.fm (lightweight, good coverage)
            if not d.get("lastfm_bio") and not d.get("lastfm_tags"):
                lf_data = _fetch_artist_from_lastfm(artist_name)
                if lf_data:
                    db.execute(
                        """UPDATE artist_enrichment SET
                           lastfm_tags=?, lastfm_bio=?, lastfm_listeners=?,
                           lastfm_playcount=?, lastfm_url=?, last_fetched=datetime('now')
                           WHERE artist_name=?""",
                        (
                            json.dumps(lf_data.get("lastfm_tags", [])),
                            lf_data.get("lastfm_bio"),
                            lf_data.get("lastfm_listeners"),
                            lf_data.get("lastfm_playcount"),
                            lf_data.get("lastfm_url"),
                            artist_name,
                        ),
                    )
                    db.commit()
                    d.update(lf_data)

            return d

        # No row at all — fetch fresh
        data = _fetch_artist_from_musicbrainz(artist_name, mbid)

        if data:
            db.execute(
                """INSERT OR REPLACE INTO artist_enrichment
                   (artist_name, mbid, canonical_name, country, formed_year, genres, tags, bio_summary, wikipedia_url, last_fetched)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (
                    artist_name, data.get("mbid"), data.get("canonical_name"), data.get("country"),
                    data.get("formed_year"), json.dumps(data.get("genres", [])),
                    json.dumps(data.get("tags", [])), data.get("bio_summary"),
                    data.get("wikipedia_url"),
                ),
            )
            db.commit()
        else:
            # Still nothing — store minimal tombstone
            db.execute(
                "INSERT OR REPLACE INTO artist_enrichment (artist_name, mbid, canonical_name, genres, tags, last_fetched) VALUES (?, ?, ?, '[]', '[]', datetime('now'))",
                (artist_name, mbid, artist_name),
            )
            db.commit()
            data = {"artist_name": artist_name, "mbid": mbid, "genres": [], "tags": []}

        # Always fetch Last.fm
        lf_data = _fetch_artist_from_lastfm(artist_name)
        if lf_data:
            db.execute(
                """UPDATE artist_enrichment SET
                   lastfm_tags=?, lastfm_bio=?, lastfm_listeners=?,
                   lastfm_playcount=?, lastfm_url=?, last_fetched=datetime('now')
                   WHERE artist_name=?""",
                (
                    json.dumps(lf_data.get("lastfm_tags", [])),
                    lf_data.get("lastfm_bio"),
                    lf_data.get("lastfm_listeners"),
                    lf_data.get("lastfm_playcount"),
                    lf_data.get("lastfm_url"),
                    artist_name,
                ),
            )
            db.commit()
            data.update(lf_data)

        return data
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

        if mbid:
            artist = resp.json()
        else:
            artists = resp.json().get("artists", [])
            artist = artists[0] if artists else None
        if not artist or not artist.get("id"):
            return None

        time.sleep(API_DELAY)

        bio = _fetch_wikipedia_bio(artist.get("name", artist_name))
        if bio:
            time.sleep(API_DELAY)

        return {
            "artist_name": artist_name,
            "canonical_name": artist.get("name", artist_name),
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


def get_album_art(album_name: str, artist_name: str, force: bool = False) -> dict:
    """Get artwork URL for an album. Returns cached data immediately;
    fetches from MusicBrainz + Cover Art Archive on first request (best-effort, fast timeouts).

    When force=True, skips the cache and re-fetches from MusicBrainz —
    useful for re-seeding after search improvements.
    """
    db = get_db()
    try:
        row = db.execute(
            "SELECT * FROM album_art WHERE album_name = ? AND artist_name = ?",
            (album_name, artist_name),
        ).fetchone()

        if row and not force:
            d = _row_to_dict(row)
            # Reconstruct artwork URLs from MBID (no need to re-verify)
            if d.get("mbid"):
                d["artwork_url"] = CAA_250.format(mbid=d["mbid"])
            # Lazy backfill: if we have an mbid but no release_group_mbid, fetch it
            if d.get("mbid") and not d.get("release_group_mbid"):
                rg_mbid = _fetch_release_group_mbid(d["mbid"])
                if rg_mbid:
                    d["release_group_mbid"] = rg_mbid
                    db.execute(
                        "UPDATE album_art SET release_group_mbid = ? WHERE album_name = ? AND artist_name = ?",
                        (rg_mbid, album_name, artist_name),
                    )
                    db.commit()
            # Lazy backfill: fetch tracklist if mbid present but not cached
            if d.get("mbid") and not d.get("tracklist"):
                tracklist = get_album_tracklist(d["mbid"])
                if tracklist:
                    d["tracklist"] = tracklist
                    db.execute(
                        "UPDATE album_art SET tracklist = ? WHERE album_name = ? AND artist_name = ?",
                        (json.dumps(tracklist), album_name, artist_name),
                    )
                    db.commit()
            return d

        art_data = _fetch_album_art(album_name, artist_name)

        if art_data:
            mbid = art_data.get("mbid")
            tracklist = get_album_tracklist(mbid) if mbid else None
            if tracklist:
                art_data["tracklist"] = tracklist
            db.execute(
                """INSERT OR REPLACE INTO album_art
                   (album_name, artist_name, mbid, release_group_mbid, canonical_name, artwork_url, release_year, release_date, last_fetched, total_tracks, tracklist)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?)""",
                (album_name, artist_name, mbid,
                 art_data.get("release_group_mbid"),
                 art_data.get("canonical_name"),
                 CAA_250.format(mbid=mbid),
                 art_data.get("release_year"), art_data.get("release_date"),
                 art_data.get("total_tracks"),
                 json.dumps(tracklist) if tracklist else None),
            )
            db.commit()
            return art_data

        db.execute(
            "INSERT OR REPLACE INTO album_art (album_name, artist_name, canonical_name, last_fetched) VALUES (?, ?, ?, datetime('now'))",
            (album_name, artist_name, album_name),
        )
        db.commit()
        return {"album_name": album_name, "artist_name": artist_name}
    finally:
        db.close()


def _fetch_release_group_mbid(release_mbid: str) -> Optional[str]:
    """Given a release MBID, look up its release group MBID."""
    try:
        url = f"https://musicbrainz.org/ws/2/release/{release_mbid}"
        params = {"fmt": "json", "inc": "release-groups"}
        resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=5)
        if resp.status_code != 200:
            return None
        data = resp.json()
        rg = data.get("release-group", {})
        rg_mbid = rg.get("id")
        time.sleep(API_DELAY)
        return rg_mbid
    except Exception:
        return None


def _fetch_album_art(album_name: str, artist_name: str) -> Optional[dict]:
    """Search MusicBrainz for a release, return MBID + year.
    Tries exact release match first, then broader fuzzy search
    with name normalization scoring."""
    try:
        # Phase 1 — exact quoted release search
        resp = requests.get(
            "https://musicbrainz.org/ws/2/release",
            params={
                "query": f'release:"{album_name}" AND artist:"{artist_name}"',
                "fmt": "json", "limit": 5,
                "inc": "genres+tags",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=5,
        )
        releases = resp.json().get("releases", []) if resp.status_code == 200 else []

        # Phase 2 — broader Lucene search if exact didn't match
        if not releases:
            time.sleep(API_DELAY)
            resp = requests.get(
                "https://musicbrainz.org/ws/2/release",
                params={
                    "query": f'{album_name} AND artist:"{artist_name}"',
                    "fmt": "json", "limit": 15,
                    "inc": "genres+tags+artist-credits",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=5,
            )
            if resp.status_code == 200:
                all_r = resp.json().get("releases", [])
                art_norm = norm_track(artist_name)
                alb_norm = norm_track(album_name)
                scored = []
                for r in all_r:
                    r_artist = " ".join(
                        c.get("name", "") for c in r.get("artist-credit", [])
                        if isinstance(c, dict)
                    )
                    if art_norm not in norm_track(r_artist):
                        continue  # wrong artist
                    r_title_norm = norm_track(r.get("title", ""))
                    # Score by name similarity
                    if r_title_norm == alb_norm:
                        score = 1.0
                    elif alb_norm in r_title_norm or r_title_norm in alb_norm:
                        score = 0.8
                    else:
                        continue  # name too different
                    scored.append((score, r))
                scored.sort(key=lambda x: -x[0])
                releases = [r for _, r in scored] if scored else []

        if not releases:
            return None

        release = releases[0]
        mbid = release.get("id")
        rg_mbid = release.get("release-group", {}).get("id")
        date = release.get("date") or ""
        year = _parse_year(date)

        if mbid:
            total_tracks = release.get("track-count", None) or None
            return {
                "album_name": album_name, "artist_name": artist_name,
                "canonical_name": release.get("title", album_name),
                "mbid": mbid, "release_group_mbid": rg_mbid,
                "artwork_url": CAA_250.format(mbid=mbid),
                "release_year": year, "release_date": date or None,
                "total_tracks": total_tracks,
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


# ── Release group ──

RG_CACHE_TTL = 86400  # 24 hours


def _init_release_group_cache(db: sqlite3.Connection):
    db.execute("""
        CREATE TABLE IF NOT EXISTS release_group_cache (
            rg_mbid TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            fetched_at TEXT DEFAULT (datetime('now'))
        )
    """)
    # Purge stale entries
    db.execute(
        "DELETE FROM release_group_cache WHERE fetched_at < datetime('now', ?)",
        (f"-{RG_CACHE_TTL} seconds",),
    )
    db.commit()


def get_release_group(rg_mbid: str) -> Optional[dict]:
    """Fetch release group info (all releases in the group) from MusicBrainz,
    cached locally for RG_CACHE_TTL seconds."""
    if not rg_mbid:
        return None
    db = get_db()
    _init_release_group_cache(db)
    try:
        row = db.execute(
            "SELECT data FROM release_group_cache WHERE rg_mbid = ?", (rg_mbid,)
        ).fetchone()
        if row:
            return json.loads(row["data"])

        # Search releases by release group ID — this includes media/label detail
        resp = requests.get(
            "https://musicbrainz.org/ws/2/release",
            params={
                "query": f"rgid:{rg_mbid}",
                "fmt": "json", "limit": 100,
                "inc": "media+labels",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=8,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        releases = data.get("releases", [])
        result = {
            "rg_mbid": rg_mbid,
            "title": "",
            "releases": [
                {
                    "mbid": r.get("id"),
                    "title": r.get("title"),
                    "status": r.get("status"),
                    "date": r.get("date"),
                    "country": r.get("country"),
                    "format": r.get("media", [{}])[0].get("format") if r.get("media") else None,
                    "label": r.get("label-info", [{}])[0].get("label", {}).get("name") if r.get("label-info") else None,
                    "track_count": r.get("media", [{}])[0].get("track-count") if r.get("media") else None,
                }
                for r in releases
            ],
        }

        db.execute(
            "INSERT OR REPLACE INTO release_group_cache (rg_mbid, data, fetched_at) VALUES (?, ?, datetime('now'))",
            (rg_mbid, json.dumps(result)),
        )
        db.commit()

        time.sleep(API_DELAY)
        return result
    except Exception:
        return None
    finally:
        db.close()


# ── Helpers ──


def norm_track(title: str) -> str:
    """Normalize a track title for fuzzy matching — lowercase,
    strip parentheticals, replace punctuation with spaces."""
    t = title.lower().strip()
    t = re.sub(r'\([^)]*\)', ' ', t)     # (live), (remastered), etc. → space
    t = re.sub(r'[^\w\s]', ' ', t)        # punctuation → space
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _parse_year(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    try:
        return int(date_str[:4])
    except (ValueError, TypeError):
        return None


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("genres", "tags", "lastfm_tags", "tracklist"):
        if d.get(key) and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                d[key] = [] if key == "tracklist" else d[key]
    return d
