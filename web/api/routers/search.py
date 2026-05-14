"""Search endpoint — search across artists, albums, and tracks."""

import sqlite3
from fastapi import APIRouter, Request, Query

router = APIRouter()


def _db(request: Request) -> sqlite3.Connection:
    db = sqlite3.connect(request.app.state.db_path)
    db.row_factory = sqlite3.Row
    return db


@router.get("")
def search(request: Request, q: str = Query("", min_length=1)):
    """Fuzzy search across artists, albums, and tracks."""
    db = _db(request)
    try:
        results = {"artists": [], "albums": [], "tracks": []}

        if not q:
            return results

        term = f"%{q}%"

        artists = db.execute(
            """SELECT artist, COUNT(*) as plays
               FROM tracks
               WHERE artist LIKE ?
               GROUP BY artist
               ORDER BY plays DESC
               LIMIT 10""",
            (term,),
        ).fetchall()
        results["artists"] = [{"name": r["artist"], "plays": r["plays"]} for r in artists]

        albums = db.execute(
            """SELECT album, artist, COUNT(*) as plays
               FROM tracks
               WHERE album LIKE ?
               GROUP BY album, artist
               ORDER BY plays DESC
               LIMIT 10""",
            (term,),
        ).fetchall()
        results["albums"] = [{"name": r["album"], "artist": r["artist"], "plays": r["plays"]} for r in albums]

        tracks = db.execute(
            """SELECT title, artist, COUNT(*) as plays
               FROM tracks
               WHERE title LIKE ?
               GROUP BY artist, title
               ORDER BY plays DESC
               LIMIT 10""",
            (term,),
        ).fetchall()
        results["tracks"] = [{"name": r["title"], "artist": r["artist"], "plays": r["plays"]} for r in tracks]

        return results
    finally:
        db.close()
