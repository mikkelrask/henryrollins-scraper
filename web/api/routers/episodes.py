"""Episode endpoints."""

import sqlite3
import json
from fastapi import APIRouter, HTTPException, Request
from ..models.schemas import EpisodeSummary, EpisodeDetail, TrackInfo, BandcampLink, EpisodeStats

router = APIRouter()


def _db(request: Request) -> sqlite3.Connection:
    db = sqlite3.connect(request.app.state.db_path)
    db.row_factory = sqlite3.Row
    return db

def _enrichment_db(request: Request) -> sqlite3.Connection:
    db = sqlite3.connect(request.app.state.enrichment_path)
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
                broadcast=r["broadcast"] or 0,
                date=r["date"] or "",
                title=r["title"] or f"Broadcast #{r['broadcast']}",
                track_count=r["track_count"],
                unique_artists=r["unique_artists"],
                repeat_rate=repeat_rate,
            ))

        return {"items": episodes, "total": total, "page": page, "per_page": per_page}
    finally:
        db.close()


@router.get("/{ident}")
def get_episode(request: Request, ident: str):
    """Get full episode detail with track listing.
    Accepts either a broadcast number or an ISO date string (e.g. 2017-01-27)."""
    db = _db(request)
    enrich_db = _enrichment_db(request)
    try:
        # Try looking up by broadcast number first
        try:
            num = int(ident)
            ep = db.execute(
                "SELECT id, broadcast, date, title, url FROM episodes WHERE broadcast = ?",
                (num,),
            ).fetchone()
        except ValueError:
            ep = None

        # Fallback: look up by date
        if not ep:
            ep = db.execute(
                "SELECT id, broadcast, date, title, url FROM episodes WHERE date = ?",
                (ident,),
            ).fetchone()

        if not ep:
            raise HTTPException(status_code=404, detail="Episode not found")

        tracks = db.execute(
            """SELECT t.id, t.hour, t.position, art.name as artist, t.title, alb.name as album,
                      (SELECT COUNT(DISTINCT episode_id) FROM tracks WHERE artist_id = t.artist_id) as artist_total_eps,
                      (SELECT COUNT(*) FROM tracks WHERE artist_id = t.artist_id AND title = t.title) as track_total_plays
               FROM tracks t
               JOIN artists art ON t.artist_id = art.id
               LEFT JOIN albums alb ON t.album_id = alb.id
               WHERE t.episode_id = ?
               ORDER BY t.hour, t.position""",
            (ep["id"],),
        ).fetchall()

        # Fetch all corrections for this episode
        corrections = enrich_db.execute(
            "SELECT track_id, corrected_data FROM corrections WHERE episode_id = ?",
            (ep["broadcast"],),
        ).fetchall()
        
        # We need a robust way to match corrections. 
        # Since TRACK_EDITs might have NULL track_id (if not linked correctly),
        # we'll look for matches by hour/position as a fallback.
        correction_map = {}
        for c in corrections:
            data = json.loads(c["corrected_data"])
            # Match by explicit ID, or by position in the episode
            key = c["track_id"] if c["track_id"] else f"{data.get('hour')}:{data.get('position')}"
            correction_map[key] = data

        links = db.execute(
            "SELECT url, label FROM links WHERE episode_id = ?",
            (ep["id"],),
        ).fetchall()

        track_list = []
        for t in tracks:
            # Patch track if correction exists:
            # 1. Match by track ID
            # 2. Match by hour/position if ID didn't match (for manual corrections)
            data = correction_map.get(t["id"], correction_map.get(f"{t['hour']}:{t['position']}", {}))
            
            track_list.append(TrackInfo(
                hour=data.get("hour", t["hour"]), 
                position=data.get("position", t["position"]),
                artist=data.get("artist", t["artist"]), 
                title=data.get("title", t["title"]),
                album=data.get("album", t["album"]) or None,
                artist_first=(t["artist_total_eps"] <= 1),
                track_first=(t["track_total_plays"] <= 1),
            ))

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
        enrich_db.close()
