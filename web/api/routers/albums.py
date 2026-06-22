"""Album endpoints."""

import sqlite3
from fastapi import APIRouter, HTTPException, Request
from ..models.schemas import AlbumSummary, AlbumDetail, TrackCount, TimelinePoint
from ..services.enrichment import get_album_art, get_album_tracklist, get_played_track_titles, get_release_group, norm_track

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


@router.get("/tracks-by-id/{album_id}")
def get_album_tracks_by_id(request: Request, album_id: int):
    """Get all tracks for an album by ID."""
    db = _db(request)
    try:
        rows = db.execute(
            """SELECT t.id, t.title, art.name as artist, alb.name as album
               FROM tracks t
               JOIN artists art ON t.artist_id = art.id
               JOIN albums alb ON t.album_id = alb.id
               WHERE t.album_id = ?""",
            (album_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def _fill_heatmap(db, table: str, field: str, value: str, artist: str = ""):
    """Build monthly heatmap with zero-fill for an artist or album."""
    if table == "tracks":
        if artist:
            rows = db.execute(
                """SELECT strftime('%Y', e.date) as year,
                          strftime('%m', e.date) as month,
                          COUNT(t.id) as plays
                   FROM episodes e
                   JOIN tracks t ON t.episode_id = e.id
                   WHERE e.date != '' AND t.album = ? AND t.artist = ?
                   GROUP BY year, month
                   ORDER BY year, month""",
                (value, artist),
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT strftime('%Y', e.date) as year,
                          strftime('%m', e.date) as month,
                          COUNT(t.id) as plays
                   FROM episodes e
                   JOIN tracks t ON t.episode_id = e.id
                   WHERE e.date != '' AND t.artist = ?
                   GROUP BY year, month
                   ORDER BY year, month""",
                (value,),
            ).fetchall()
    else:
        return []

    if not rows:
        return []

    first_year = int(rows[0]["year"])
    first_month = int(rows[0]["month"])
    last_year = int(rows[-1]["year"])
    last_month = int(rows[-1]["month"])

    plays_by_month = {}
    for r in rows:
        plays_by_month[f"{r['year']}-{r['month']}"] = r["plays"]

    result = []
    y, m = first_year, first_month
    while (y < last_year) or (y == last_year and m <= last_month):
        key = f"{y:04d}-{m:02d}"
        result.append({
            "year": f"{y:04d}",
            "month": f"{m:02d}",
            "plays": plays_by_month.get(key, 0),
        })
        m += 1
        if m > 12:
            m = 1
            y += 1

    return result


@router.get("/heatmap/{album_name:path}")
def get_album_heatmap(request: Request, album_name: str):
    """Calendar heatmap data for a specific album: year, month, play count."""
    from urllib.parse import unquote
    name = unquote(album_name)
    db = _db(request)
    try:
        # Get artist for this album
        artist_row = db.execute(
            "SELECT artist FROM tracks WHERE album = ? AND artist != '' LIMIT 1",
            (name,),
        ).fetchone()
        artist = artist_row["artist"] if artist_row else ""
        return _fill_heatmap(db, "tracks", "album", name, artist=artist)
    finally:
        db.close()


@router.get("/{album_id:path}")
def get_album(request: Request, album_id: str, artist: str = ""):
    """Get album detail by album name (and optionally artist)."""
    from urllib.parse import unquote
    album_name = unquote(album_id)

    db = _db(request)
    try:
        if artist:
            rows = db.execute(
                """SELECT t.album, t.artist, COUNT(*) as plays,
                          COUNT(DISTINCT t.title) as distinct_tracks,
                          COUNT(DISTINCT t.episode_id) as episodes
                   FROM tracks t
                   WHERE t.album = ? AND t.artist = ?
                   GROUP BY t.album, t.artist
                   ORDER BY plays DESC""",
                (album_name, artist),
            ).fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail="Album not found")
            r = rows[0]
        else:
            rows = db.execute(
                """SELECT t.album, t.artist, COUNT(*) as plays,
                          COUNT(DISTINCT t.title) as distinct_tracks,
                          COUNT(DISTINCT t.episode_id) as episodes
                   FROM tracks t
                   WHERE t.album = ?
                   GROUP BY t.album, t.artist
                   ORDER BY plays DESC""",
                (album_name,),
            ).fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail="Album not found")
            r = rows[0]

        track_plays_raw = db.execute(
            """SELECT t.title, e.broadcast, e.date
               FROM tracks t
               JOIN episodes e ON e.id = t.episode_id
               WHERE t.album = ? AND t.artist = ?
               ORDER BY t.title, e.broadcast""",
            (album_name, r["artist"]),
        ).fetchall()

        from collections import defaultdict
        track_groups = defaultdict(list)
        for row in track_plays_raw:
            track_groups[row["title"]].append({
                "broadcast": row["broadcast"],
                "date": row["date"],
            })

        from ..models.schemas import TrackPlay
        tracks = []
        for title, plays in track_groups.items():
            last = plays[-1]
            tracks.append({
                "title": title,
                "plays": len(plays),
                "last_played": last["date"],
                "last_broadcast": last["broadcast"],
                "broadcasts": [TrackPlay(broadcast=p["broadcast"], date=p["date"]) for p in plays],
            })
        # Sort by plays descending
        tracks.sort(key=lambda t: -t["plays"])

        timeline = db.execute(
            """SELECT e.broadcast, e.date, COUNT(*) as plays
               FROM tracks t
               JOIN episodes e ON e.id = t.episode_id
               WHERE t.album = ? AND t.artist = ?
               GROUP BY e.id
               ORDER BY e.broadcast ASC""",
            (album_name, r["artist"]),
        ).fetchall()

        heatmap = _fill_heatmap(db, "tracks", "album", album_name, artist=r["artist"])

        art = get_album_art(album_name, r["artist"])
        mbid = art.get("mbid")
        rg_mbid = art.get("release_group_mbid")
        large_url = None
        if mbid:
            large_url = f"https://coverartarchive.org/release/{mbid}/front-500"

        releases = []
        if rg_mbid:
            rg_data = get_release_group(rg_mbid)
            if rg_data:
                releases = rg_data.get("releases", [])

        # Unplayed tracks: fetch full tracklist from MusicBrainz, diff against played
        unplayed = []
        if mbid:
            full_tracklist = get_album_tracklist(mbid)
            played_titles = get_played_track_titles(mbid, album_name, r["artist"], db)
            # Normalize both sides so casing/punctuation differences don't cause false unplayed
            played_norm = {norm_track(t) for t in played_titles}
            unplayed = [t for t in full_tracklist if norm_track(t) not in played_norm]

        # Look up the album's DB id for merge operations
        album_row = db.execute(
            "SELECT a.id, a.artist_id FROM albums a WHERE a.name = ? AND a.artist_id = (SELECT id FROM artists WHERE name = ?)",
            (album_name, r["artist"]),
        ).fetchone()
        album_id = album_row["id"] if album_row else None
        artist_id = album_row["artist_id"] if album_row else None

        from ..models.schemas import ReleaseInfo

        return AlbumDetail(
            id=album_id,
            artist_id=artist_id,
            album=r["album"],
            artist=r["artist"],
            plays=r["plays"],
            distinct_tracks=r["distinct_tracks"],
            episodes=r["episodes"],
            heatmap=heatmap,
            artwork_url=art.get("artwork_url"),
            artwork_url_large=large_url,
            mbid=mbid,
            release_group_mbid=rg_mbid,
            release_date=art.get("release_date"),
            unplayed_tracks=unplayed,
            releases=[ReleaseInfo(**r) for r in releases],
            tracks=[TrackCount(
                title=t["title"],
                plays=t["plays"],
                last_played=t["last_played"],
                last_broadcast=t["last_broadcast"],
                broadcasts=t["broadcasts"],
            ) for t in tracks],
            timeline=[TimelinePoint(
                broadcast=t["broadcast"],
                date=t["date"],
                plays=t["plays"],
            ) for t in timeline],
        )
    finally:
        db.close()
