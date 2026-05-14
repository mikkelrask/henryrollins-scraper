"""Dashboard / stats endpoints."""

import sqlite3
from fastapi import APIRouter, Request
from ..models.schemas import OverviewStats, TopItem
from ..services.enrichment import get_album_art

router = APIRouter()


def _db(request: Request) -> sqlite3.Connection:
    db = sqlite3.connect(request.app.state.db_path)
    db.row_factory = sqlite3.Row
    return db


@router.get("/overview")
def overview(request: Request):
    """Top-line aggregate statistics."""
    db = _db(request)
    try:
        ep_count = db.execute("SELECT COUNT(*) as c FROM episodes").fetchone()["c"]
        tr_count = db.execute("SELECT COUNT(*) as c FROM tracks").fetchone()["c"]
        art_count = db.execute("SELECT COUNT(DISTINCT artist) as c FROM tracks").fetchone()["c"]
        link_count = db.execute("SELECT COUNT(*) as c FROM links").fetchone()["c"]

        first = db.execute(
            "SELECT MIN(broadcast) as first, MIN(date) as first_date FROM episodes"
        ).fetchone()
        last = db.execute(
            "SELECT MAX(broadcast) as last, MAX(date) as last_date FROM episodes"
        ).fetchone()

        date_range = None
        if first and last and first["first_date"] and last["last_date"]:
            date_range = (first["first_date"], last["last_date"])

        return OverviewStats(
            episodes=ep_count,
            tracks=tr_count,
            unique_artists=art_count,
            bandcamp_links=link_count,
            date_range=date_range,
        )
    finally:
        db.close()


@router.get("/top-artists")
def top_artists(request: Request, limit: int = 10, metric: str = "plays"):
    """Top N artists by plays (default) or episode coverage."""
    db = _db(request)
    try:
        if metric == "coverage":
            total_eps = db.execute("SELECT COUNT(*) as c FROM episodes").fetchone()["c"]
            rows = db.execute(
                """SELECT artist, COUNT(*) as plays,
                          COUNT(DISTINCT episode_id) as episodes
                   FROM tracks
                   GROUP BY artist
                   ORDER BY episodes DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            return [TopItem(
                name=r["artist"],
                value=r["episodes"],
                extra={"plays": r["plays"], "pct": round(r["episodes"] / total_eps * 100, 1)},
            ) for r in rows]
        else:
            rows = db.execute(
                """SELECT artist, COUNT(*) as plays,
                          COUNT(DISTINCT episode_id) as episodes
                   FROM tracks
                   GROUP BY artist
                   ORDER BY plays DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            return [TopItem(
                name=r["artist"],
                value=r["plays"],
                extra={"episodes": r["episodes"]},
            ) for r in rows]
    finally:
        db.close()


@router.get("/top-albums")
def top_albums(request: Request, limit: int = 10):
    """Top N most-played albums."""
    db = _db(request)
    try:
        rows = db.execute(
            """SELECT album, artist, COUNT(*) as plays
               FROM tracks
               WHERE album != ''
               GROUP BY album, artist
               ORDER BY plays DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

        result = []
        for r in rows:
            art = get_album_art(r["album"], r["artist"])
            result.append(TopItem(
                name=r["album"],
                value=r["plays"],
                extra={"artist": r["artist"], "artwork_url": art.get("artwork_url")},
            ))
        return result
    finally:
        db.close()


@router.get("/top-tracks")
def top_tracks(request: Request, limit: int = 10):
    """Top N most-played tracks (per album), with album info."""
    db = _db(request)
    try:
        rows = db.execute(
            """SELECT t.title, t.artist, t.album, COUNT(*) as plays
               FROM tracks t
               WHERE t.album != ''
               GROUP BY t.artist, t.title, t.album
               ORDER BY plays DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

        return [TopItem(
            name=r["title"],
            value=r["plays"],
            extra={"artist": r["artist"], "album": r["album"]},
        ) for r in rows]
    finally:
        db.close()


@router.get("/heatmap")
def heatmap(request: Request):
    """Calendar heatmap data: year, month, play count."""
    db = _db(request)
    try:
        rows = db.execute(
            """SELECT strftime('%Y', e.date) as year,
                      strftime('%m', e.date) as month,
                      COUNT(t.id) as plays
               FROM episodes e
               JOIN tracks t ON t.episode_id = e.id
               WHERE e.date != ''
               GROUP BY year, month
               ORDER BY year, month"""
        ).fetchall()
        return [{"year": r["year"], "month": r["month"], "plays": r["plays"]} for r in rows]
    finally:
        db.close()


@router.get("/recent-episodes")
def recent_episodes(request: Request, limit: int = 5):
    """Most recent episodes with track counts."""
    db = _db(request)
    try:
        rows = db.execute(
            """SELECT e.broadcast, e.date, e.title, COUNT(t.id) as track_count
               FROM episodes e
               LEFT JOIN tracks t ON t.episode_id = e.id
               GROUP BY e.id
               ORDER BY e.broadcast DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()
