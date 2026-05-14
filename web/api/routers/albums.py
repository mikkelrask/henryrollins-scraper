"""Album endpoints."""

import sqlite3
from fastapi import APIRouter, HTTPException, Request
from ..models.schemas import AlbumSummary, AlbumDetail, TrackCount, TimelinePoint
from ..services.enrichment import get_album_art, get_album_tracklist, get_played_track_titles

router = APIRouter()


def _db(request: Request) -> sqlite3.Connection:
    db = sqlite3.connect(request.app.state.db_path)
    db.row_factory = sqlite3.Row
    return db


@router.get("")
def list_albums(
    request: Request,
    page: int = 1,
    per_page: int = 50,
    sort: str = "-plays",
    search: str = "",
):
    """List all albums with play statistics."""
    db = _db(request)
    try:
        offset = (page - 1) * per_page

        where_clauses = ["t.album != ''"]
        params = []

        if search:
            where_clauses.append("(t.album LIKE ? OR t.artist LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where_sql = "WHERE " + " AND ".join(where_clauses)

        order_dir = "DESC" if sort.startswith("-") else "ASC"
        order_col = sort.lstrip("-")
        allowed_cols = {"plays", "distinct_tracks", "episodes", "album", "artist"}
        if order_col not in allowed_cols:
            order_col = "plays"

        total = db.execute(
            f"""SELECT COUNT(*) as c FROM (
                SELECT t.album, t.artist FROM tracks t {where_sql} GROUP BY t.album, t.artist
            )""",
            params,
        ).fetchone()["c"]

        rows = db.execute(
            f"""SELECT t.album, t.artist,
                       COUNT(*) as plays,
                       COUNT(DISTINCT t.title) as distinct_tracks,
                       COUNT(DISTINCT t.episode_id) as episodes,
                       MAX(e.date) as last_played
                FROM tracks t
                JOIN episodes e ON e.id = t.episode_id
                {where_sql}
                GROUP BY t.album, t.artist
                ORDER BY {order_col} {order_dir}
                LIMIT ? OFFSET ?""",
            (*params, per_page, offset),
        ).fetchall()

        # Album list: include artwork_url for grid view
        items = []
        for r in rows:
            art = get_album_art(r["album"], r["artist"])
            items.append(AlbumSummary(
                album=r["album"],
                artist=r["artist"],
                plays=r["plays"],
                distinct_tracks=r["distinct_tracks"],
                episodes=r["episodes"],
                last_played=r["last_played"],
                artwork_url=art.get("artwork_url"),
            ))

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
        }
    finally:
        db.close()


@router.get("/{album_id:path}")
def get_album(request: Request, album_id: str):
    """Get album detail by album name."""
    from urllib.parse import unquote
    album_name = unquote(album_id)

    db = _db(request)
    try:
        rows = db.execute(
            """SELECT t.album, t.artist, COUNT(*) as plays,
                      COUNT(DISTINCT t.title) as distinct_tracks,
                      COUNT(DISTINCT t.episode_id) as episodes
               FROM tracks t
               WHERE t.album = ?
               GROUP BY t.album, t.artist""",
            (album_name,),
        ).fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail="Album not found")

        r = rows[0]

        tracks = db.execute(
            """SELECT t.title, COUNT(*) as plays, MAX(e.date) as last_played
               FROM tracks t
               JOIN episodes e ON e.id = t.episode_id
               WHERE t.album = ? AND t.artist = ?
               GROUP BY t.title
               ORDER BY plays DESC""",
            (album_name, r["artist"]),
        ).fetchall()

        timeline = db.execute(
            """SELECT e.broadcast, e.date, COUNT(*) as plays
               FROM tracks t
               JOIN episodes e ON e.id = t.episode_id
               WHERE t.album = ? AND t.artist = ? AND e.broadcast IS NOT NULL
               GROUP BY e.id
               ORDER BY e.broadcast ASC""",
            (album_name, r["artist"]),
        ).fetchall()

        art = get_album_art(album_name, r["artist"])
        mbid = art.get("mbid")
        large_url = None
        if mbid:
            large_url = f"https://coverartarchive.org/release/{mbid}/front-500"

        # Unplayed tracks: fetch full tracklist from MusicBrainz, diff against played
        unplayed = []
        if mbid:
            full_tracklist = get_album_tracklist(mbid)
            played_titles = get_played_track_titles(mbid, album_name, r["artist"], db)
            unplayed = [t for t in full_tracklist if t not in played_titles]

        return AlbumDetail(
            album=r["album"],
            artist=r["artist"],
            plays=r["plays"],
            distinct_tracks=r["distinct_tracks"],
            episodes=r["episodes"],
            artwork_url=art.get("artwork_url"),
            artwork_url_large=large_url,
            mbid=mbid,
            release_date=art.get("release_date"),
            unplayed_tracks=unplayed,
            tracks=[TrackCount(
                title=t["title"],
                plays=t["plays"],
                last_played=t["last_played"],
            ) for t in tracks],
            timeline=[TimelinePoint(
                broadcast=t["broadcast"],
                date=t["date"],
                plays=t["plays"],
            ) for t in timeline],
        )
    finally:
        db.close()
