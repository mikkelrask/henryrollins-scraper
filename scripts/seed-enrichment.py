#!/usr/bin/env python3
"""
Offline enrichment seeder.

Runs all artists and albums through MusicBrainz + Last.fm enrichment
and writes the results to the main SQLite database. This preserves
Worker runtime by doing the expensive API calls locally during a
build step.

Usage:
  python3 scripts/seed-enrichment.py            # enrich only unresolved entries
  python3 scripts/seed-enrichment.py --all      # re-enrich everything
  python3 scripts/seed-enrichment.py --force    # re-fetch even cached entries

The script imports the existing enrichment service logic so we don't
duplicate the MusicBrainz/Wikipedia/Last.fm fetch functions.
"""

import sys
import os
import json
import time
import argparse

# Ensure we can import from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from web.api.services.enrichment import (
    get_artist_enrichment,
    get_album_art,
    get_album_tracklist,
    norm_track,
    USER_AGENT,
    API_DELAY,
)
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "henryrollins.db"


def get_db() -> sqlite3.Connection:
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db


def get_unenriched_artists(db, force: bool = False) -> list[str]:
    """Get artists that are missing enrichment data (or all if --force)."""
    if force:
        rows = db.execute(
            "SELECT DISTINCT t.artist FROM tracks t ORDER BY t.artist"
        ).fetchall()
        return [r["artist"] for r in rows]

    # Artists with empty or missing enrichment
    rows = db.execute("""
        SELECT DISTINCT t.artist
        FROM tracks t
        LEFT JOIN artist_enrichment ae ON ae.artist_name = t.artist
        WHERE ae.artist_name IS NULL
           OR ae.country IS NULL
           OR (ae.genres IS NULL OR ae.genres = '[]')
        ORDER BY t.artist
    """).fetchall()
    return [r["artist"] for r in rows]


def get_unenriched_albums(db, force: bool = False) -> list[tuple[str, str]]:
    """Get album/artist pairs missing artwork (or all if --force)."""
    if force:
        rows = db.execute(
            "SELECT DISTINCT t.album, t.artist FROM tracks t WHERE t.album != '' ORDER BY t.artist, t.album"
        ).fetchall()
        return [(r["album"], r["artist"]) for r in rows]

    rows = db.execute("""
        SELECT DISTINCT t.album, t.artist
        FROM tracks t
        LEFT JOIN album_art aa ON aa.album_name = t.album AND aa.artist_name = t.artist
        WHERE t.album != ''
          AND aa.album_name IS NULL
        ORDER BY t.artist, t.album
    """).fetchall()
    return [(r["album"], r["artist"]) for r in rows]


def main():
    parser = argparse.ArgumentParser(description="Pre-bake enrichment data into local SQLite")
    parser.add_argument("--all", action="store_true", help="Re-enrich every artist and album")
    parser.add_argument("--force", action="store_true", help="Re-fetch even cached entries")
    parser.add_argument("--artists-only", action="store_true", help="Only enrich artists")
    parser.add_argument("--albums-only", action="store_true", help="Only enrich albums")
    parser.add_argument("--no-dedup", action="store_true", help="Skip track title deduplication")
    args = parser.parse_args()

    force = args.all or args.force

    db = get_db()

    # Ensure enrichment tables exist in main DB
    db.executescript("""
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
    """)
    db.commit()

    # ── Step 1: Enrich artists ──
    if not args.albums_only:
        artists = get_unenriched_artists(db, force=force)
        total = len(artists)
        print(f"🎤 Enriching {total} artists...")

        for i, artist_name in enumerate(artists, 1):
            try:
                result = get_artist_enrichment(artist_name)
                # The enrichment service already writes to its own DB.
                # Copy the result into the main DB.
                genres_json = result.get("genres", [])
                tags_json = result.get("tags", [])
                lastfm_json = result.get("lastfm_tags", [])

                if isinstance(genres_json, list):
                    genres_json = __import__("json").dumps(genres_json)
                if isinstance(tags_json, list):
                    tags_json = __import__("json").dumps(tags_json)
                if isinstance(lastfm_json, list):
                    lastfm_json = __import__("json").dumps(lastfm_json)

                db.execute(
                    """INSERT OR REPLACE INTO artist_enrichment
                       (artist_name, mbid, canonical_name, country, formed_year,
                        genres, tags, bio_summary, wikipedia_url,
                        lastfm_tags, lastfm_bio, lastfm_listeners, lastfm_playcount, lastfm_url,
                        last_fetched, fetch_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), 1)""",
                    (
                        artist_name,
                        result.get("mbid"),
                        result.get("canonical_name"),
                        result.get("country"),
                        result.get("formed_year"),
                        genres_json,
                        tags_json,
                        result.get("bio_summary"),
                        result.get("wikipedia_url"),
                        lastfm_json,
                        result.get("lastfm_bio"),
                        result.get("lastfm_listeners"),
                        result.get("lastfm_playcount"),
                        result.get("lastfm_url"),
                    ),
                )
                # Keep artists.mbid in sync so merge detection can find it
                if result.get("mbid"):
                    db.execute(
                        "UPDATE artists SET mbid = ? WHERE name = ? AND mbid IS NULL",
                        (result["mbid"], artist_name),
                    )
                db.commit()

                status = "✅" if result.get("country") or result.get("genres") else "⚠️"
                print(f"  [{i}/{total}] {status} {artist_name}")
            except Exception as e:
                print(f"  [{i}/{total}] ❌ {artist_name}: {e}")

            time.sleep(API_DELAY)

    # ── Step 2: Enrich albums ──
    if not args.artists_only:
        albums = get_unenriched_albums(db, force=force)
        total = len(albums)
        print(f"💿 Enriching {total} albums...")

        for i, (album_name, artist_name) in enumerate(albums, 1):
            try:
                result = get_album_art(album_name, artist_name, force=force)
                if result and result.get("mbid"):
                    tracklist = result.get("tracklist")
                    mb_artist = result.get("canonical_artist")

                    db.execute(
                        """INSERT OR REPLACE INTO album_art
                           (album_name, artist_name, mbid, release_group_mbid, canonical_name,
                            artwork_url, release_year, release_date, last_fetched, total_tracks, tracklist)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?)""",
                        (
                            album_name,
                            artist_name,
                            result.get("mbid"),
                            result.get("release_group_mbid"),
                            result.get("canonical_name"),
                            result.get("artwork_url"),
                            result.get("release_year"),
                            result.get("release_date"),
                            result.get("total_tracks"),
                            json.dumps(tracklist) if tracklist else None,
                        ),
                    )

                    # Merge artist: rename or merge the old artist into the canonical one
                    if mb_artist and mb_artist != artist_name:
                        old_row = db.execute(
                            "SELECT id FROM artists WHERE name = ?", (artist_name,)
                        ).fetchone()
                        if old_row:
                            old_id = old_row["id"]
                            new_row = db.execute(
                                "SELECT id FROM artists WHERE name = ?", (mb_artist,)
                            ).fetchone()
                            if new_row:
                                new_id = new_row["id"]
                                db.execute("UPDATE tracks SET artist_id = ?, artist = ? WHERE artist_id = ?",
                                    (new_id, mb_artist, old_id))
                                db.execute("UPDATE albums SET artist_id = ? WHERE artist_id = ?", (new_id, old_id))
                                db.execute("DELETE FROM artists WHERE id = ?", (old_id,))
                            else:
                                db.execute("UPDATE artists SET name = ? WHERE id = ?", (mb_artist, old_id))
                                db.execute("UPDATE tracks SET artist = ? WHERE artist = ?", (mb_artist, artist_name))
                            # Update album_art PK to new artist name
                            db.execute(
                                "UPDATE album_art SET artist_name = ? WHERE album_name = ? AND artist_name = ?",
                                (mb_artist, album_name, artist_name),
                            )

                    db.commit()
                    name_change = f" → {mb_artist}" if mb_artist and mb_artist != artist_name else ""
                    print(f"  [{i}/{total}] ✅ {album_name} by {artist_name}{name_change}")
                else:
                    # Store tombstone so we don't re-try every time
                    db.execute(
                        "INSERT OR IGNORE INTO album_art (album_name, artist_name, last_fetched) VALUES (?, ?, datetime('now'))",
                        (album_name, artist_name),
                    )
                    db.commit()
                    print(f"  [{i}/{total}] ⚠️ {album_name} by {artist_name} (no match)")
            except Exception as e:
                print(f"  [{i}/{total}] ❌ {album_name}: {e}")

            time.sleep(API_DELAY * 0.5)  # Albums are cheaper (one MB call)

    # ── Step 3: Deduplicate track titles ──
    if not args.no_dedup:
        deduped = _dedup_tracks(db)
        if deduped:
            print(f"🔀 Matched {deduped} tracks to canonical MusicBrainz titles")
        else:
            print("🔀 No tracks needed deduplication")

    print("\n✨ Done!")


def _dedup_tracks(db: sqlite3.Connection) -> int:
    """Match played track titles against each album's MusicBrainz tracklist
    and update variant titles to the canonical MusicBrainz name."""
    rows = db.execute("""
        SELECT DISTINCT t.album AS album_name, t.artist AS artist_name,
               COALESCE(aa.mbid, al.mbid) AS mbid
        FROM tracks t
        LEFT JOIN album_art aa ON aa.album_name = t.album AND aa.artist_name = t.artist
        LEFT JOIN albums al ON al.name = t.album
            AND al.artist_id = (SELECT ar.id FROM artists ar WHERE ar.name = t.artist LIMIT 1)
        WHERE t.album != ''
          AND COALESCE(aa.mbid, al.mbid) IS NOT NULL
        ORDER BY t.artist, t.album
    """).fetchall()

    if not rows:
        return 0

    total = len(rows)
    updated = 0
    print(f"🔀 Matching {total} albums against MusicBrainz tracklists...")

    for i, row in enumerate(rows, 1):
        album = row["album_name"]
        artist = row["artist_name"]
        mbid = row["mbid"]

        mb_tracks = get_album_tracklist(mbid)
        if not mb_tracks:
            continue

        # Get unique played track titles for this album
        played = db.execute(
            "SELECT DISTINCT title FROM tracks WHERE album = ? AND artist = ? AND title != ''",
            (album, artist),
        ).fetchall()

        # Build normalised lookup: normalised MB title → canonical MB title
        mb_norm = {}
        for t in mb_tracks:
            n = norm_track(t)
            if n not in mb_norm:
                mb_norm[n] = t

        for pt in played:
            p_title = pt["title"]
            pn = norm_track(p_title)
            if pn in mb_norm:
                canonical = mb_norm[pn]
                if canonical != p_title:
                    db.execute(
                        "UPDATE tracks SET title = ? WHERE title = ? AND album = ? AND artist = ?",
                        (canonical, p_title, album, artist),
                    )
                    updated += db.execute("SELECT changes()").fetchone()[0]

        db.commit()

        if i % 20 == 0 or i == total:
            print(f"  [{i}/{total}] {updated} titles updated so far")

        time.sleep(API_DELAY * 0.3)

    return updated


if __name__ == "__main__":
    main()
