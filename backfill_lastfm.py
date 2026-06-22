#!/usr/bin/env python3
"""
Backfill Last.fm enrichment data for ALL artists in the DB.
Run once to warm the cache so insights/stats are accurate.
"""
import sqlite3
import sys
import time
from pathlib import Path
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent / "web" / "api"))
from services.enrichment import get_db, _fetch_artist_from_lastfm


def main():
    main_db = sqlite3.connect(Path(__file__).parent / "db" / "henryrollins.db")
    main_db.row_factory = sqlite3.Row

    artists = main_db.execute("SELECT name FROM artists ORDER BY id").fetchall()
    main_db.close()

    enrich_db = get_db()
    total = len(artists)
    updated = 0
    skipped = 0
    failed = 0

    print(f"Backfilling Last.fm data for {total} artists...")
    print("(Already-cached artists are skipped automatically)\n")

    for row in tqdm(artists, unit="artists", ncols=80):
        name = row["name"]

        # Check if already has Last.fm data
        cached = enrich_db.execute(
            "SELECT lastfm_bio, lastfm_tags FROM artist_enrichment WHERE artist_name = ?",
            (name,),
        ).fetchone()

        if cached and cached["lastfm_bio"] and cached["lastfm_tags"]:
            skipped += 1
            continue

        data = _fetch_artist_from_lastfm(name)
        if data:
            enrich_db.execute(
                """UPDATE artist_enrichment SET
                   lastfm_tags=?, lastfm_bio=?, lastfm_listeners=?,
                   lastfm_playcount=?, lastfm_url=?, last_fetched=datetime('now')
                   WHERE artist_name=?""",
                (
                    json.dumps(data.get("lastfm_tags", [])),
                    data.get("lastfm_bio"),
                    data.get("lastfm_listeners"),
                    data.get("lastfm_playcount"),
                    data.get("lastfm_url"),
                    name,
                ),
            )
            enrich_db.commit()
            updated += 1
        else:
            failed += 1

        time.sleep(0.25)  # Be polite to Last.fm

    enrich_db.close()
    print(f"\nDone: {updated} updated, {skipped} already cached, {failed} failed")


if __name__ == "__main__":
    import json
    main()
