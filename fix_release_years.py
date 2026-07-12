#!/usr/bin/env python3
"""
Backfill release_year/release_date in album_art using each release group's
first-release-date, instead of whichever specific release we happened to
match (often a later reissue/remaster). Fixes cases like a 1979 album
showing as "released" in 2024 because that's the edition MusicBrainz
returned first.

Safe to interrupt and re-run — pass --start to resume from a given row
offset (printed on interrupt).
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent / "web" / "api"))
from services.enrichment import get_db, _fetch_release_group_first_date, _parse_year


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=0, help="Row offset to resume from")
    args = parser.parse_args()

    db = get_db()
    rows = db.execute(
        """SELECT rowid, album_name, artist_name, release_group_mbid, release_year, release_date
           FROM album_art
           WHERE release_group_mbid IS NOT NULL
           ORDER BY rowid"""
    ).fetchall()

    total = len(rows)
    rows = rows[args.start:]
    print(f"{total} albums have a release group; resuming from offset {args.start} ({len(rows)} to check)\n")

    # Cache first-release-date per release group so albums sharing one
    # (compilations, splits) only cost a single MusicBrainz call.
    group_date_cache = {}
    updated = 0
    unchanged = 0
    failed = 0

    try:
        for i, row in enumerate(tqdm(rows, unit="album", ncols=80)):
            rg_mbid = row["release_group_mbid"]

            if rg_mbid in group_date_cache:
                group_date = group_date_cache[rg_mbid]
            else:
                group_date = _fetch_release_group_first_date(rg_mbid)
                group_date_cache[rg_mbid] = group_date

            if not group_date:
                failed += 1
                continue

            new_year = _parse_year(group_date)
            if group_date == row["release_date"] and new_year == row["release_year"]:
                unchanged += 1
                continue

            db.execute(
                "UPDATE album_art SET release_year = ?, release_date = ? WHERE album_name = ? AND artist_name = ?",
                (new_year, group_date, row["album_name"], row["artist_name"]),
            )
            db.commit()
            updated += 1
    except KeyboardInterrupt:
        print(f"\nInterrupted at offset {args.start + i}. Resume with --start {args.start + i}")
        db.close()
        sys.exit(1)

    db.close()
    print(f"\nDone: {updated} corrected, {unchanged} already accurate, {failed} lookup failures")


if __name__ == "__main__":
    main()
