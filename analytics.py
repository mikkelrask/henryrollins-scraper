#!/usr/bin/env python3
"""
Analytics queries for the Henry Rollins radio show database.

Usage:
    python3 analytics.py                  # Show summary
    python3 analytics.py top-artists      # Most-played artists
    python3 analytics.py top-artists --limit 20
    python3 analytics.py artist "Wire"    # Plays for a specific artist
    python3 analytics.py per-episode      # Track count per episode
"""

import argparse
import sqlite3
import sys
from pathlib import Path

DB_DIR = Path("db")
DB_PATH = DB_DIR / "henryrollins.db"


def get_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}", file=sys.stderr)
        print("Run scraper.py first to populate the database.", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def cmd_summary(conn: sqlite3.Connection) -> None:
    ep_count = conn.execute("SELECT COUNT(*) AS c FROM episodes").fetchone()["c"]
    tr_count = conn.execute("SELECT COUNT(*) AS c FROM tracks").fetchone()["c"]
    link_count = conn.execute("SELECT COUNT(*) AS c FROM links").fetchone()["c"]
    artist_count = conn.execute(
        "SELECT COUNT(DISTINCT artist) AS c FROM tracks"
    ).fetchone()["c"]

    first = conn.execute(
        "SELECT broadcast, date FROM episodes ORDER BY broadcast ASC LIMIT 1"
    ).fetchone()
    last = conn.execute(
        "SELECT broadcast, date FROM episodes ORDER BY broadcast DESC LIMIT 1"
    ).fetchone()

    print("=== Henry Rollins Radio Show Database ===")
    print(f"  Episodes:       {ep_count}")
    print(f"  Tracks:         {tr_count}")
    print(f"  Unique artists: {artist_count}")
    print(f"  Bandcamp links: {link_count}")
    if first and last:
        print(f"  Date range:     #{first['broadcast']} ({first['date']})")
        print(f"                  to #{last['broadcast']} ({last['date']})")


def cmd_top_artists(conn: sqlite3.Connection, limit: int) -> None:
    rows = conn.execute(
        """SELECT artist, COUNT(*) AS plays,
                  COUNT(DISTINCT episode_id) AS episodes
           FROM tracks
           GROUP BY artist
           ORDER BY plays DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()

    print(f"\n=== Top {limit} Artists by Play Count ===\n")
    print(f"{'Plays':>6}  {'Episodes':>9}  Artist")
    print(f"{'─'*6}  {'─'*9}  {'─'*30}")
    for r in rows:
        print(f"{r['plays']:>6}  {r['episodes']:>9}  {r['artist']}")


def cmd_artist(conn: sqlite3.Connection, name: str) -> None:
    # Search by exact or partial match
    rows = conn.execute(
        """SELECT t.artist, t.title, t.album, t.hour, t.position,
                  e.broadcast, e.date
           FROM tracks t
           JOIN episodes e ON e.id = t.episode_id
           WHERE t.artist LIKE ?
           ORDER BY e.broadcast DESC, t.hour, t.position""",
        (f"%{name}%",),
    ).fetchall()

    if not rows:
        print(f"No tracks found matching artist '{name}'")
        return

    print(f"\n=== Tracks by/with '{name}' ({len(rows)} plays) ===\n")
    for r in rows:
        print(
            f"  #{r['broadcast']} ({r['date']})  "
            f"H{r['hour']}#{r['position']:>2}  "
            f"{r['artist']} — {r['title']}  / {r['album'] or '—'}"
        )


def cmd_per_episode(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """SELECT e.broadcast, e.date, COUNT(t.id) AS track_count
           FROM episodes e
           LEFT JOIN tracks t ON t.episode_id = e.id
           GROUP BY e.id
           ORDER BY e.broadcast DESC"""
    ).fetchall()

    print(f"\n=== Tracks Per Episode ===\n")
    for r in rows:
        print(f"  #{r['broadcast']} ({r['date']}) — {r['track_count']} tracks")


def cmd_bandcamp_links(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """SELECT l.url, l.label, e.broadcast, e.date
           FROM links l
           JOIN episodes e ON e.id = l.episode_id
           ORDER BY e.broadcast DESC"""
    ).fetchall()

    print(f"\n=== Bandcamp Links ({len(rows)} total) ===\n")
    for r in rows:
        print(f"  #{r['broadcast']} ({r['date']}): {r['url']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query the Henry Rollins radio show database"
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="summary",
        choices=["summary", "top-artists", "artist", "per-episode", "bandcamp-links"],
        help="Query to run",
    )
    parser.add_argument(
        "--limit", type=int, default=20, help="Limit for top-artists (default 20)"
    )
    parser.add_argument("name", nargs="?", help="Artist name for 'artist' query")
    args = parser.parse_args()

    conn = get_conn()

    if args.command == "summary":
        cmd_summary(conn)
    elif args.command == "top-artists":
        cmd_top_artists(conn, args.limit)
    elif args.command == "artist":
        if not args.name:
            print("Error: 'artist' command requires a name argument", file=sys.stderr)
            sys.exit(1)
        cmd_artist(conn, args.name)
    elif args.command == "per-episode":
        cmd_per_episode(conn)
    elif args.command == "bandcamp-links":
        cmd_bandcamp_links(conn)

    conn.close()


if __name__ == "__main__":
    main()
