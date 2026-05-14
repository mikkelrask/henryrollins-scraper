"""Bandcamp 'Henry Recommends' endpoints."""

import sqlite3
from urllib.parse import urlparse
from collections import defaultdict
from fastapi import APIRouter, Request
from ..models.schemas import RecommendItem, RecommendArtist

router = APIRouter()


def _db(request: Request) -> sqlite3.Connection:
    db = sqlite3.connect(request.app.state.db_path)
    db.row_factory = sqlite3.Row
    return db


def _parse_bandcamp_url(url: str) -> tuple[str, str]:
    """Parse a bandcamp URL into (artist_name, album_title)."""
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path.strip("/")

    artist = host.replace(".bandcamp.com", "") if ".bandcamp.com" in host else host

    album = ""
    if "/album/" in path:
        album = path.split("/album/")[-1].replace("-", " ").title()
    elif "/track/" in path:
        album = path.split("/track/")[-1].replace("-", " ").title()
    elif path == "releases" or not path:
        album = "Profile / Releases"
    else:
        album = path.replace("-", " ").title()

    return artist, album


@router.get("")
def list_recommends(
    request: Request,
    page: int = 1,
    per_page: int = 30,
    sort: str = "-episode_count",
    link_type: str = "album",
):
    """List Bandcamp album links, grouped by URL, sorted by frequency."""
    db = _db(request)
    try:
        offset = (page - 1) * per_page

        where_clause = ""
        if link_type == "album":
            where_clause = "WHERE l.url LIKE '%/album/%'"
        elif link_type == "label":
            where_clause = "WHERE l.url NOT LIKE '%/album/%' AND l.url NOT LIKE '%/track/%'"

        order_dir = "DESC" if sort.startswith("-") else "ASC"
        order_col = sort.lstrip("-")
        if order_col not in ("episode_count", "last_seen", "first_seen"):
            order_col = "episode_count"

        order_sql = f"{order_col} {order_dir}"

        total = db.execute(
            f"""SELECT COUNT(*) as c FROM (
                SELECT l.url FROM links l {where_clause} GROUP BY l.url
            )"""
        ).fetchone()["c"]

        rows = db.execute(
            f"""SELECT l.url,
                       COUNT(DISTINCT e.id) as episode_count,
                       MIN(e.date) as first_seen,
                       MAX(e.date) as last_seen,
                       GROUP_CONCAT(DISTINCT e.broadcast) as episode_ids
                FROM links l
                JOIN episodes e ON e.id = l.episode_id
                {where_clause}
                GROUP BY l.url
                ORDER BY {order_sql}
                LIMIT ? OFFSET ?""",
            (per_page, offset),
        ).fetchall()

        items = []
        for r in rows:
            artist, ab = _parse_bandcamp_url(r["url"])
            ep_ids = [int(x) for x in (r["episode_ids"] or "").split(",") if x.strip()]
            items.append(RecommendItem(
                url=r["url"],
                bandcamp_artist=artist,
                album_title=ab,
                episode_count=r["episode_count"],
                first_seen=r["first_seen"],
                last_seen=r["last_seen"],
                episodes=sorted(ep_ids, reverse=True)[:10],
            ))

        return {"items": items, "total": total, "page": page, "per_page": per_page}
    finally:
        db.close()


@router.get("/artists")
def recommend_artists(request: Request):
    """Rank Bandcamp artists by how often Henry links them."""
    db = _db(request)
    try:
        rows = db.execute(
            """SELECT l.url,
                      COUNT(DISTINCT e.id) as total_episodes,
                      MAX(e.date) as last_seen
               FROM links l
               JOIN episodes e ON e.id = l.episode_id
               WHERE l.url LIKE '%/album/%'
               GROUP BY l.url
               ORDER BY total_episodes DESC
               LIMIT 50"""
        ).fetchall()

        by_artist = defaultdict(lambda: {"unique_albums": set(), "total_episodes": 0, "last_seen": ""})

        for r in rows:
            artist, _ = _parse_bandcamp_url(r["url"])
            by_artist[artist]["unique_albums"].add(r["url"])
            by_artist[artist]["total_episodes"] += r["total_episodes"]
            if r["last_seen"] and r["last_seen"] > by_artist[artist]["last_seen"]:
                by_artist[artist]["last_seen"] = r["last_seen"]

        sorted_artists = sorted(
            by_artist.items(),
            key=lambda x: x[1]["total_episodes"],
            reverse=True,
        )

        return [RecommendArtist(
            bandcamp_artist=artist,
            unique_albums=len(data["unique_albums"]),
            total_episodes=data["total_episodes"],
            last_seen=data["last_seen"],
        ) for artist, data in sorted_artists]
    finally:
        db.close()


@router.get("/by-episode/{broadcast}")
def recommends_for_episode(request: Request, broadcast: int):
    """Get all Bandcamp links for a specific episode."""
    db = _db(request)
    try:
        rows = db.execute(
            """SELECT l.url, l.label
               FROM links l
               JOIN episodes e ON e.id = l.episode_id
               WHERE e.broadcast = ?
               ORDER BY l.id""",
            (broadcast,),
        ).fetchall()
        return [{"url": r["url"], "label": r["label"] or ""} for r in rows]
    finally:
        db.close()
