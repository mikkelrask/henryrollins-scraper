"""Tracks router — list/search all tracks ever played on the show."""

from fastapi import APIRouter, Request, HTTPException, Query
from ..models.schemas import TrackCount

import sqlite3


router = APIRouter(tags=["tracks"])


def _db(request: Request) -> sqlite3.Connection:
    db = sqlite3.connect(request.app.state.db_path)
    db.row_factory = sqlite3.Row
    return db


@router.get("")
def list_tracks(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort: str = Query("-plays"),
    search: str = Query(""),
):
    """List all tracks with play statistics."""
    db = _db(request)
    try:
        offset = (page - 1) * per_page

        where_clauses = ["1=1"]
        params = []

        if search:
            where_clauses.append("(t.title LIKE ? OR t.artist LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where_sql = "WHERE " + " AND ".join(where_clauses)

        order_dir = "DESC" if sort.startswith("-") else "ASC"
        order_col = sort.lstrip("-")
        allowed_cols = {"plays", "title", "artist", "last_played", "album"}
        if order_col not in allowed_cols:
            order_col = "plays"

        # We group by title, artist, and album to ensure different versions are counted separately.
        # This accurately reflects the user's requirement that plays are per album.

        total = db.execute(
            f"""SELECT COUNT(*) as c FROM (
                SELECT t.title, t.artist_id, t.album_id FROM tracks t {where_sql}
                GROUP BY t.title, t.artist_id, t.album_id
            )""",
            params,
        ).fetchone()["c"]

        rows = db.execute(
            f"""SELECT t.title, art.name as artist, alb.name as album,
                       COUNT(*) as plays,
                       COUNT(DISTINCT t.episode_id) as episodes,
                       MAX(e.date) as last_played
                FROM tracks t
                JOIN episodes e ON e.id = t.episode_id
                JOIN artists art ON t.artist_id = art.id
                LEFT JOIN albums alb ON t.album_id = alb.id
                {where_sql}
                GROUP BY t.title, t.artist_id, t.album_id
                ORDER BY {order_col} {order_dir}
                LIMIT ? OFFSET ?""",
            (*params, per_page, offset),
        ).fetchall()

        return {
            "items": [
                TrackCount(
                    title=r["title"],
                    plays=r["plays"],
                    episodes=r["episodes"],
                    last_played=r["last_played"],
                    artist=r["artist"],
                    album=r["album"],
                )
                for r in rows
            ],
            "total": total,
            "page": page,
            "per_page": per_page,
        }
    finally:
        db.close()
