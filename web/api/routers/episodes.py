"""Episode endpoints."""

import sqlite3
from fastapi import APIRouter, HTTPException, Request
from ..models.schemas import EpisodeSummary, EpisodeDetail, TrackInfo, BandcampLink, EpisodeStats

router = APIRouter()


def _db(request: Request) -> sqlite3.Connection:
    db = sqlite3.connect(request.app.state.db_path)
    db.row_factory = sqlite3.Row
    return db


@router.get("")
def list_episodes(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    sort: str = "-broadcast",
):
    """List episodes with pagination and sorting."""
    db = _db(request)
    try:
        offset = (page - 1) * per_page

        order_dir = "DESC" if sort.startswith("-") else "ASC"
        order_col = sort.lstrip("-")

        rows = db.execute(
            f"""SELECT e.broadcast, e.date, e.title,
                       COUNT(t.id) as track_count,
                       COUNT(DISTINCT t.artist) as unique_artists
                FROM episodes e
                LEFT JOIN tracks t ON t.episode_id = e.id
                GROUP BY e.id
                ORDER BY e.{order_col} {order_dir}
                LIMIT ? OFFSET ?""",
            (per_page, offset),
        ).fetchall()

        total = db.execute("SELECT COUNT(*) as c FROM episodes").fetchone()["c"]

        episodes = []
        for r in rows:
            repeat_rate = round((r["track_count"] - r["unique_artists"]) / r["track_count"] * 100, 1) if r["track_count"] > 0 else 0
            episodes.append(EpisodeSummary(
                broadcast=r["broadcast"],
                date=r["date"] or "",
                title=r["title"] or f"Broadcast #{r['broadcast']}",
                track_count=r["track_count"],
                unique_artists=r["unique_artists"],
                repeat_rate=repeat_rate,
            ))

        return {"items": episodes, "total": total, "page": page, "per_page": per_page}
    finally:
        db.close()


@router.get("/{broadcast}")
def get_episode(request: Request, broadcast: int):
    """Get full episode detail with track listing."""
    db = _db(request)
    try:
        ep = db.execute(
            "SELECT id, broadcast, date, title, url FROM episodes WHERE broadcast = ?",
            (broadcast,),
        ).fetchone()
        if not ep:
            raise HTTPException(status_code=404, detail="Episode not found")

        tracks = db.execute(
            """SELECT hour, position, artist, title, album
               FROM tracks WHERE episode_id = ?
               ORDER BY hour, position""",
            (ep["id"],),
        ).fetchall()

        links = db.execute(
            "SELECT url, label FROM links WHERE episode_id = ?",
            (ep["id"],),
        ).fetchall()

        track_list = [TrackInfo(
            hour=t["hour"], position=t["position"],
            artist=t["artist"], title=t["title"],
            album=t["album"] or None,
        ) for t in tracks]

        bandcamp = [BandcampLink(url=l["url"], label=l["label"] or "") for l in links]

        unique_artists = len(set(t.artist for t in track_list))
        repeat_rate = round((len(track_list) - unique_artists) / len(track_list) * 100, 1) if track_list else 0

        return EpisodeDetail(
            broadcast=ep["broadcast"],
            date=ep["date"] or "",
            title=ep["title"] or f"Broadcast #{ep['broadcast']}",
            url=ep["url"] or "",
            tracks=track_list,
            bandcamp_links=bandcamp,
            stats=EpisodeStats(
                track_count=len(track_list),
                unique_artists=unique_artists,
                repeat_rate=repeat_rate,
            ),
        )
    finally:
        db.close()
