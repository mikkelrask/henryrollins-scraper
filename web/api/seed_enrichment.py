"""
Seed the enrichment database with existing artist_cache.json data.

This imports all 1,871 MusicBrainz MBIDs so the enrichment DB is populated
without making fresh API calls. Album artwork is fetched on-demand.
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from web.api.services.enrichment import get_db

ARTIST_CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "artist_cache.json"


def load_artist_cache() -> dict:
    with open(ARTIST_CACHE_PATH) as f:
        return json.load(f)


def seed():
    print("Loading artist_cache.json...")
    cache = load_artist_cache()
    print(f"Total entries: {len(cache)}")

    # Extract unique artist names with MusicBrainz data (uppercase-first keys)
    seen = {}
    for key, value in cache.items():
        if value.get("source") == "musicbrainz" and key[0].isupper():
            canonical = value.get("canonical_name", key)
            mbid = value.get("mbid")
            if canonical and mbid and canonical not in seen:
                seen[canonical] = mbid

    print(f"Unique artists with MBIDs: {len(seen)}")

    # Insert into enrichment DB
    db = get_db()
    try:
        inserted = 0
        for name, mbid in sorted(seen.items()):
            existing = db.execute(
                "SELECT artist_name FROM artist_enrichment WHERE artist_name = ?",
                (name,),
            ).fetchone()

            if not existing:
                db.execute(
                    """INSERT INTO artist_enrichment
                       (artist_name, mbid, last_fetched, fetch_count)
                       VALUES (?, ?, datetime('now'), 0)""",
                    (name, mbid),
                )
                inserted += 1

        db.commit()
        print(f"Inserted {inserted} new artist enrichment records")
        print(f"Total in DB: {db.execute('SELECT COUNT(*) as c FROM artist_enrichment').fetchone()['c']}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
