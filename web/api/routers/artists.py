"""Artist endpoints."""

import sqlite3
from fastapi import APIRouter, HTTPException, Request
from ..models.schemas import (
    ArtistSummary, ArtistDetail, TrackCount, AlbumBreakdown, TimelinePoint,
    ArtistEnrichment,
)
from ..services.enrichment import get_artist_enrichment, get_album_art

router = APIRouter()


def _db(request: Request) -> sqlite3.Connection:
    db = sqlite3.connect(request.app.state.db_path)
    db.row_factory = sqlite3.Row
    return db


PRIOR_STRENGTH = 10


def _global_avg_rli(db) -> float:
    """Compute the average RLI (plays/episode) across all well-sampled artists."""
    row = db.execute(
        """SELECT SUM(plays) * 1.0 / SUM(episodes) as avg_rli
           FROM (
               SELECT COUNT(*) as plays, COUNT(DISTINCT episode_id) as episodes
               FROM tracks
               GROUP BY artist
               HAVING episodes >= 3
           )""",
    ).fetchone()
    return row["avg_rli"] if row and row["avg_rli"] else 1.0


def _bayesian_rli(plays: int, episodes: int, prior: float) -> float:
    """Bayesian RLI: pulls low-episode artists toward the global average."""
    return round((plays + prior * PRIOR_STRENGTH) / (episodes + PRIOR_STRENGTH), 2)


@router.get("")
def list_artists(
    request: Request,
    page: int = 1,
    per_page: int = 50,
    sort: str = "-plays",
    search: str = "",
    badge: str = "",
):
    """List all artists with metrics, searchable and sortable."""
    db = _db(request)
    try:
        total_episodes = db.execute("SELECT COUNT(*) as c FROM episodes").fetchone()["c"]
        prior = _global_avg_rli(db)

        where_clauses = []
        params = []

        if search:
            where_clauses.append("t.artist LIKE ?")
            params.append(f"%{search}%")

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        order_dir = "DESC" if sort.startswith("-") else "ASC"
        order_col = sort.lstrip("-")
        allowed_cols = {"plays", "episodes", "rli", "coverage", "artist", "first_ep", "last_ep"}
        if order_col not in allowed_cols:
            order_col = "plays"

        total = db.execute(
            f"""SELECT COUNT(*) as c FROM (
                SELECT artist FROM tracks t {where_sql} GROUP BY artist
            )""",
            params,
        ).fetchone()["c"]

        rows = db.execute(
            f"""SELECT t.artist,
                       COUNT(*) as plays,
                       COUNT(DISTINCT t.episode_id) as episodes,
                       COUNT(DISTINCT t.album) as album_count,
                       MIN(e.broadcast) as first_ep,
                       MAX(e.broadcast) as last_ep
                FROM tracks t
                JOIN episodes e ON e.id = t.episode_id
                {where_sql}
                GROUP BY t.artist""",
            params,
        ).fetchall()

        all_artists = []
        for r in rows:
            badge_str = _compute_badge(r["plays"], r["episodes"], total_episodes)
            if badge and badge != badge_str:
                continue
            album_div = round(r["album_count"] / r["plays"], 2) if r["plays"] > 0 else 0
            coverage = round(r["episodes"] / total_episodes * 100, 1) if total_episodes > 0 else 0
            all_artists.append(ArtistSummary(
                artist=r["artist"],
                plays=r["plays"],
                episodes=r["episodes"],
                rli=_bayesian_rli(r["plays"], r["episodes"], prior),
                coverage=coverage,
                album_diversity=album_div,
                first_episode=str(r["first_ep"]) if r["first_ep"] else None,
                last_episode=str(r["last_ep"]) if r["last_ep"] else None,
                badge=badge_str,
            ))

        # Sort in Python to support computed metrics
        reverse = order_dir == "DESC"
        if order_col == "rli":
            all_artists.sort(key=lambda a: a.rli, reverse=reverse)
        elif order_col == "coverage":
            all_artists.sort(key=lambda a: a.coverage or 0, reverse=reverse)
        elif order_col == "artist":
            all_artists.sort(key=lambda a: a.artist.lower(), reverse=reverse)
        elif order_col == "plays":
            all_artists.sort(key=lambda a: a.plays, reverse=reverse)
        elif order_col == "episodes":
            all_artists.sort(key=lambda a: a.episodes, reverse=reverse)
        elif order_col == "first_ep":
            all_artists.sort(key=lambda a: int(a.first_episode) if a.first_episode else 0, reverse=reverse)
        elif order_col == "last_ep":
            all_artists.sort(key=lambda a: int(a.last_episode) if a.last_episode else 0, reverse=reverse)

        offset = (page - 1) * per_page
        items = all_artists[offset:offset + per_page]

        return {"items": items, "total": len(all_artists), "page": page, "per_page": per_page}
    finally:
        db.close()


@router.get("/top")
def top_artists(request: Request, limit: int = 20, metric: str = "plays"):
    """Get top artists by various metrics."""
    db = _db(request)
    try:
        total_eps = db.execute("SELECT COUNT(*) as c FROM episodes").fetchone()["c"]
        prior = _global_avg_rli(db)

        rows = db.execute(
            """SELECT t.artist,
                       COUNT(*) as plays,
                       COUNT(DISTINCT t.episode_id) as episodes
                FROM tracks t
                GROUP BY t.artist""",
        ).fetchall()

        items = []
        for r in rows:
            rli = _bayesian_rli(r["plays"], r["episodes"], prior)
            coverage = round(r["episodes"] / total_eps * 100, 1) if total_eps > 0 else 0
            items.append(dict(r) | {
                "rli": rli,
                "coverage": coverage,
                "badge": _compute_badge(r["plays"], r["episodes"], total_eps),
            })

        if metric == "rli":
            items.sort(key=lambda a: a["rli"], reverse=True)
        elif metric == "episodes":
            items.sort(key=lambda a: a["episodes"], reverse=True)
        elif metric == "coverage":
            items.sort(key=lambda a: a["coverage"], reverse=True)
        else:
            items.sort(key=lambda a: a["plays"], reverse=True)

        return items[:limit]
    finally:
        db.close()


@router.get("/albums/{name:path}")
def get_artist_albums(request: Request, name: str):
    """Get all albums by a specific artist with artwork (fetched for first 50, lazy for rest)."""
    print(f"DEBUG: get_artist_albums called with name='{name}'")
    db = _db(request)
    try:
        rows = db.execute(
            """SELECT album, COUNT(*) as plays, COUNT(DISTINCT title) as distinct_tracks
               FROM tracks
               WHERE artist = ? AND album != ''
               GROUP BY album
               ORDER BY plays DESC""",
            (name,),
        ).fetchall()
        print(f"DEBUG: Query found {len(rows)} rows for artist '{name}'")

        items = []
        for i, r in enumerate(rows):
            art_url = None
            release_date = None
            if i < 50:  # Fetch artwork for first 50 albums
                art = get_album_art(r["album"], name)
                art_url = art.get("artwork_url")
                release_date = art.get("release_date")
            items.append(AlbumBreakdown(
                album=r["album"],
                artist=name,
                plays=r["plays"],
                distinct_tracks=r["distinct_tracks"],
                artwork_url=art_url,
                release_date=release_date,
            ))

        return {"items": items, "total": len(items), "artist": name}
    finally:
        db.close()


@router.get("/tracks/{name:path}")
def get_artist_tracks(
    request: Request,
    name: str,
    page: int = 1,
    per_page: int = 50,
):
    """Get all tracks by a specific artist."""
    db = _db(request)
    try:
        offset = (page - 1) * per_page

        total = db.execute(
            "SELECT COUNT(*) as c FROM tracks WHERE artist = ?",
            (name,),
        ).fetchone()["c"]

        rows = db.execute(
            """SELECT t.title, t.album, e.broadcast, e.date, t.hour, t.position
               FROM tracks t
               JOIN episodes e ON e.id = t.episode_id
               WHERE t.artist = ?
               ORDER BY e.broadcast DESC, t.hour, t.position
               LIMIT ? OFFSET ?""",
            (name, per_page, offset),
        ).fetchall()

        return {
            "items": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
        }
    finally:
        db.close()


@router.get("/timeline/{name:path}")
def get_artist_timeline(request: Request, name: str):
    """Get play timeline data for charts."""
    db = _db(request)
    try:
        rows = db.execute(
            """SELECT e.broadcast, e.date, COUNT(*) as plays
               FROM tracks t
               JOIN episodes e ON e.id = t.episode_id
               WHERE t.artist = ?
               GROUP BY e.id
               ORDER BY e.broadcast ASC""",
            (name,),
        ).fetchall()
        return [{"broadcast": r["broadcast"], "date": r["date"], "plays": r["plays"]} for r in rows]
    finally:
        db.close()


@router.get("/heatmap/{name:path}")
def get_artist_heatmap(request: Request, name: str):
    """Calendar heatmap data for a specific artist: year, month, play count.

    Fills in zero-play months so the trend pulse accurately shows gaps.
    """
    db = _db(request)
    try:
        # Actual plays per month
        rows = db.execute(
            """SELECT strftime('%Y', e.date) as year,
                      strftime('%m', e.date) as month,
                      COUNT(t.id) as plays
               FROM episodes e
               JOIN tracks t ON t.episode_id = e.id
               WHERE e.date != '' AND t.artist = ?
               GROUP BY year, month
               ORDER BY year, month""",
            (name,),
        ).fetchall()

        if not rows:
            return []

        # Determine full date range
        first_year = int(rows[0]["year"])
        first_month = int(rows[0]["month"])
        last_year = int(rows[-1]["year"])
        last_month = int(rows[-1]["month"])

        # Build lookup dict "YYYY-MM" -> plays
        plays_by_month = {}
        for r in rows:
            plays_by_month[f"{r['year']}-{r['month']}"] = r["plays"]

        # Generate all months in range with zero-fill
        result = []
        year, month = first_year, first_month
        while (year < last_year) or (year == last_year and month <= last_month):
            key = f"{year:04d}-{month:02d}"
            result.append({
                "year": f"{year:04d}",
                "month": f"{month:02d}",
                "plays": plays_by_month.get(key, 0),
            })
            month += 1
            if month > 12:
                month = 1
                year += 1

        return result
    finally:
        db.close()


@router.get("/{name:path}")
def get_artist(request: Request, name: str):
    """Get full artist detail with tracks, albums, timeline."""
    db = _db(request)
    try:
        total_eps = db.execute("SELECT COUNT(*) as c FROM episodes").fetchone()["c"]

        stats = db.execute(
            """SELECT t.artist,
                      COUNT(*) as plays,
                      COUNT(DISTINCT t.episode_id) as episodes,
                      COUNT(DISTINCT t.album) as album_count,
                      MIN(e.date) as first_date,
                      MAX(e.date) as last_date,
                      MIN(e.broadcast) as first_ep,
                      MAX(e.broadcast) as last_ep
               FROM tracks t
               JOIN episodes e ON e.id = t.episode_id
               WHERE t.artist = ?
               GROUP BY t.artist""",
            (name,),
        ).fetchall()

        if not stats:
            raise HTTPException(status_code=404, detail="Artist not found")
        s = stats[0]

        top_tracks_rows = db.execute(
            """SELECT t.title, COUNT(*) as plays, MAX(e.date) as last_played
               FROM tracks t
               JOIN episodes e ON e.id = t.episode_id
               WHERE t.artist = ?
               GROUP BY t.title
               ORDER BY plays DESC
               LIMIT 10""",
            (name,),
        ).fetchall()

        top_tracks = []
        for r in top_tracks_rows:
            # Find the most common album for this track
            alb_row = db.execute(
                "SELECT album FROM tracks WHERE artist = ? AND title = ? AND album != '' GROUP BY album ORDER BY COUNT(*) DESC LIMIT 1",
                (name, r["title"]),
            ).fetchone()
            top_tracks.append(TrackCount(
                title=r["title"],
                plays=r["plays"],
                last_played=r["last_played"],
                album=alb_row["album"] if alb_row else None,
            ))

        albums = db.execute(
            """SELECT album, COUNT(*) as plays, COUNT(DISTINCT title) as distinct_tracks
               FROM tracks
               WHERE artist = ? AND album != ''
               GROUP BY album
               ORDER BY plays DESC""",
            (name,),
        ).fetchall()

        timeline = db.execute(
            """SELECT e.broadcast, e.date, COUNT(*) as plays
               FROM tracks t
               JOIN episodes e ON e.id = t.episode_id
               WHERE t.artist = ?
               GROUP BY e.id
               ORDER BY e.broadcast ASC""",
            (name,),
        ).fetchall()

        streak = _calc_streak([r["broadcast"] for r in timeline])
        prior = _global_avg_rli(db)
        rli = _bayesian_rli(s["plays"], s["episodes"], prior)
        coverage = round(s["episodes"] / total_eps * 100, 1) if total_eps > 0 else 0
        album_div = round(s["album_count"] / s["plays"], 2) if s["plays"] > 0 else 0
        badge = _compute_badge(s["plays"], s["episodes"], total_eps)

        # Enrichment: fetch artist metadata (cached)
        enrichment_data = get_artist_enrichment(s["artist"])
        enrichment = ArtistEnrichment(
            mbid=enrichment_data.get("mbid"),
            country=enrichment_data.get("country"),
            formed_year=enrichment_data.get("formed_year"),
            genres=enrichment_data.get("genres", []),
            tags=enrichment_data.get("tags", []),
            bio_summary=enrichment_data.get("bio_summary"),
        )

        # Album artwork enrichment (top 8 albums only to keep response fast)
        album_breakdowns = []
        for i, a in enumerate(albums):
            art_url = None
            art_url_large = None
            release_date = None
            if i < 8:  # Only fetch artwork for top 8 albums
                art = get_album_art(a["album"], s["artist"])
                art_url = art.get("artwork_url")
                mbid = art.get("mbid")
                if mbid:
                    art_url_large = f"https://coverartarchive.org/release/{mbid}/front-500"
                release_date = art.get("release_date")
            album_breakdowns.append(AlbumBreakdown(
                album=a["album"],
                artist=s["artist"],
                plays=a["plays"],
                distinct_tracks=a["distinct_tracks"],
                artwork_url=art_url,
                artwork_url_large=art_url_large,
                release_date=release_date,
            ))

        # Look up the artist's DB id for merge operations
        artist_row = db.execute(
            "SELECT id FROM artists WHERE name = ?", (name,)
        ).fetchone()
        artist_id = artist_row["id"] if artist_row else None

        return ArtistDetail(
            id=artist_id,
            artist=s["artist"],
            plays=s["plays"],
            episodes=s["episodes"],
            rli=rli,
            coverage=coverage,
            first_appearance=s["first_date"],
            last_appearance=s["last_date"],
            streak=streak,
            album_count=s["album_count"],
            album_diversity=album_div,
            enrichment=enrichment,
            top_tracks=top_tracks,
            album_breakdown=album_breakdowns,
            timeline=[TimelinePoint(
                broadcast=t["broadcast"],
                date=t["date"],
                plays=t["plays"],
            ) for t in timeline],
            badge=badge,
        )
    finally:
        db.close()


def _compute_badge(plays: int, episodes: int, total_episodes: int) -> str:
    coverage = episodes / total_episodes if total_episodes > 0 else 0
    if plays > 100:
        return "fanatic_favorite"
    if plays > 50 and coverage > 0.3:
        return "signature_artist"
    if plays <= 5:
        return "deep_cut"
    return "regular"


@router.get("/tracks-by-id/{artist_id}")
def get_artist_tracks_by_id(request: Request, artist_id: int):
    """Get all tracks for an artist by ID."""
    db = _db(request)
    try:
        rows = db.execute(
            """SELECT t.id, t.title, art.name as artist, alb.name as album
               FROM tracks t
               JOIN artists art ON t.artist_id = art.id
               LEFT JOIN albums alb ON t.album_id = alb.id
               WHERE t.artist_id = ?""",
            (artist_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()

def _calc_streak(broadcasts: list[int | None]) -> int:
    valid = [b for b in broadcasts if b is not None]
    if not valid:
        return 0
    eps_set = set(valid)
    longest = 0
    current = 0
    for ep in range(min(valid), max(valid) + 1):
        if ep in eps_set:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest
