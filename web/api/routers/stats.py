"""Dashboard / stats endpoints."""

import json
import sqlite3
from collections import Counter
from fastapi import APIRouter, Request
from ..models.schemas import OverviewStats, TopItem
from ..services.enrichment import get_album_art, get_db as enrich_db

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


# ── Insights endpoints ──

# ISO 3166-1 alpha-2 → numeric (for world-atlas map)
ISO_NUMERIC = {
    "AF": 4, "AX": 248, "AL": 8, "DZ": 12, "AS": 16, "AD": 20, "AO": 24, "AI": 660,
    "AQ": 10, "AG": 28, "AR": 32, "AM": 51, "AW": 533, "AU": 36, "AT": 40, "AZ": 31,
    "BS": 44, "BH": 48, "BD": 50, "BB": 52, "BY": 112, "BE": 56, "BZ": 84, "BJ": 204,
    "BM": 60, "BT": 64, "BO": 68, "BQ": 535, "BA": 70, "BW": 72, "BV": 74, "BR": 76,
    "IO": 86, "BN": 96, "BG": 100, "BF": 854, "BI": 108, "CV": 132, "KH": 116, "CM": 120,
    "CA": 124, "KY": 136, "CF": 140, "TD": 148, "CL": 152, "CN": 156, "CX": 162, "CC": 166,
    "CO": 170, "KM": 174, "CG": 178, "CD": 180, "CK": 184, "CR": 188, "HR": 191, "CU": 192,
    "CW": 531, "CY": 196, "CZ": 203, "DK": 208, "DJ": 262, "DM": 212, "DO": 214, "EC": 218,
    "EG": 818, "SV": 222, "GQ": 226, "ER": 232, "EE": 233, "SZ": 748, "ET": 231, "FK": 238,
    "FO": 234, "FJ": 242, "FI": 246, "FR": 250, "GF": 254, "PF": 258, "TF": 260, "GA": 266,
    "GM": 270, "GE": 268, "DE": 276, "GH": 288, "GI": 292, "GR": 300, "GL": 304, "GD": 308,
    "GP": 312, "GU": 316, "GT": 320, "GG": 831, "GN": 324, "GW": 624, "GY": 328, "HT": 332,
    "HM": 334, "VA": 336, "HN": 340, "HK": 344, "HU": 348, "IS": 352, "IN": 356, "ID": 360,
    "IR": 364, "IQ": 368, "IE": 372, "IM": 833, "IL": 376, "IT": 380, "JM": 388, "JP": 392,
    "JE": 832, "JO": 400, "KZ": 398, "KE": 404, "KI": 296, "KP": 408, "KR": 410, "KW": 414,
    "KG": 417, "LA": 418, "LV": 428, "LB": 422, "LS": 426, "LR": 430, "LY": 434, "LI": 438,
    "LT": 440, "LU": 442, "MO": 446, "MG": 450, "MW": 454, "MY": 458, "MV": 462, "ML": 466,
    "MT": 470, "MH": 584, "MQ": 474, "MR": 478, "MU": 480, "YT": 175, "MX": 484, "FM": 583,
    "MD": 498, "MC": 492, "MN": 496, "ME": 499, "MS": 500, "MA": 504, "MZ": 508, "MM": 104,
    "NA": 516, "NR": 520, "NP": 524, "NL": 528, "NC": 540, "NZ": 554, "NI": 558, "NE": 562,
    "NG": 566, "NU": 570, "NF": 574, "MK": 807, "MP": 580, "NO": 578, "OM": 512, "PK": 586,
    "PW": 585, "PS": 275, "PA": 591, "PG": 598, "PY": 600, "PE": 604, "PH": 608, "PN": 612,
    "PL": 616, "PT": 620, "PR": 630, "QA": 634, "RE": 638, "RO": 642, "RU": 643, "RW": 646,
    "BL": 652, "SH": 654, "KN": 659, "LC": 662, "MF": 663, "PM": 666, "VC": 670, "WS": 882,
    "SM": 674, "ST": 678, "SA": 682, "SN": 686, "RS": 688, "SC": 690, "SL": 694, "SG": 702,
    "SX": 534, "SK": 703, "SI": 705, "SB": 90, "SO": 706, "ZA": 710, "GS": 239, "SS": 728,
    "ES": 724, "LK": 144, "SD": 729, "SR": 740, "SJ": 744, "SE": 752, "CH": 756, "SY": 760,
    "TW": 158, "TJ": 762, "TZ": 834, "TH": 764, "TL": 626, "TG": 768, "TK": 772, "TO": 776,
    "TT": 780, "TN": 788, "TR": 792, "TM": 795, "TC": 796, "TV": 798, "UG": 800, "UA": 804,
    "AE": 784, "GB": 826, "US": 840, "UM": 581, "UY": 858, "UZ": 860, "VU": 548, "VE": 862,
    "VN": 704, "VG": 92, "VI": 850, "WF": 876, "EH": 732, "YE": 887, "ZM": 894, "ZW": 716,
}


@router.get("/countries")
def countries(request: Request):
    """Artist count per country for the world heatmap."""
    main_db = _db(request)
    enrich = enrich_db()
    try:
        # Only count artists that actually appear in the tracklist
        track_artists = {
            r["artist"] for r in main_db.execute("SELECT DISTINCT artist FROM tracks").fetchall()
        }
        rows = enrich.execute(
            """SELECT country, artist_name
               FROM artist_enrichment
               WHERE country IS NOT NULL AND country != '' AND country != 'XW'"""
        ).fetchall()
        country_counts = Counter()
        for r in rows:
            if r["artist_name"] in track_artists:
                country_counts[r["country"]] += 1
        items = []
        for country, count in country_counts.most_common():
            num = ISO_NUMERIC.get(country)
            if num:
                items.append({"code": country, "numeric": num, "count": count})
        return {"items": items}
    finally:
        main_db.close()
        enrich.close()


@router.get("/genres")
def genres(request: Request):
    """Artist count per genre/tag for visualization."""
    main_db = _db(request)
    enrich = enrich_db()
    try:
        track_artists = {
            r["artist"] for r in main_db.execute("SELECT DISTINCT artist FROM tracks").fetchall()
        }

        genre_counter = {}
        tag_counter = {}
        artists_with_mb_genres = set()

        # MusicBrainz genres
        rows = enrich.execute(
            "SELECT artist_name, genres FROM artist_enrichment WHERE genres IS NOT NULL AND genres != '[]'"
        ).fetchall()
        for r in rows:
            if r["artist_name"] not in track_artists:
                continue
            artists_with_mb_genres.add(r["artist_name"])
            try:
                glist = json.loads(r["genres"])
                for g in glist:
                    genre_counter[g] = genre_counter.get(g, 0) + 1
            except:
                pass

        # Last.fm tags (only for artists that have no MB genres, to fill gaps)
        rows = enrich.execute(
            "SELECT artist_name, lastfm_tags FROM artist_enrichment WHERE lastfm_tags IS NOT NULL AND lastfm_tags != '[]'"
        ).fetchall()
        for r in rows:
            if r["artist_name"] not in track_artists:
                continue
            if r["artist_name"] in artists_with_mb_genres:
                continue
            try:
                tlist = json.loads(r["lastfm_tags"])
                for t in tlist:
                    tag_counter[t.lower()] = tag_counter.get(t.lower(), 0) + 1
            except:
                pass

        # Merge: MB genres win, Last.fm fills gaps
        combined = dict(genre_counter)
        for tag, count in tag_counter.items():
            if tag not in combined:
                combined[tag] = count

        items = sorted(
            [{"name": k, "count": v} for k, v in combined.items()],
            key=lambda x: x["count"],
            reverse=True,
        )
        return {"items": items}
    finally:
        main_db.close()
        enrich.close()


@router.get("/genres-by-year")
def genres_by_year(request: Request):
    """Genre popularity per year — how Henry's taste evolved."""
    main_db = _db(request)
    enrich = enrich_db()
    try:
        # Get all tracks with their episode year
        rows = main_db.execute(
            """SELECT t.artist, strftime('%Y', e.date) as year
               FROM tracks t
               JOIN episodes e ON e.id = t.episode_id
               WHERE e.date != '' AND e.date IS NOT NULL"""
        ).fetchall()

        # Build artist → genres mapping (cache in-memory)
        artist_genres = {}
        for r in rows:
            name = r["artist"]
            if name not in artist_genres:
                cached = enrich.execute(
                    "SELECT genres, lastfm_tags FROM artist_enrichment WHERE artist_name = ?",
                    (name,),
                ).fetchone()
                if cached:
                    tags = set()
                    try:
                        for g in json.loads(cached["genres"] or "[]"):
                            tags.add(g.lower())
                    except:
                        pass
                    try:
                        for t in json.loads(cached["lastfm_tags"] or "[]"):
                            tags.add(t.lower())
                    except:
                        pass
                    artist_genres[name] = list(tags)
                else:
                    artist_genres[name] = []

        # Group by year
        year_genres = {}
        for r in rows:
            year = r["year"]
            if not year:
                continue
            genres = artist_genres.get(r["artist"], [])
            for g in genres:
                year_genres.setdefault(year, {}).setdefault(g, 0)
                year_genres[year][g] += 1

        result = []
        for year in sorted(year_genres.keys()):
            genres = year_genres[year]
            top = sorted(genres.items(), key=lambda x: x[1], reverse=True)[:8]
            result.append({
                "year": year,
                "total_plays": sum(genres.values()),
                "genres": [{"name": k, "count": v} for k, v in top],
            })
        return result
    finally:
        main_db.close()
        enrich.close()


@router.get("/decades")
def decades(request: Request):
    """Release decade breakdown and release-vs-broadcast scatter data."""
    main_db = _db(request)
    enrich = enrich_db()
    try:
        # Load album release years into a lookup
        album_years = {}
        rows = enrich.execute(
            "SELECT album_name, artist_name, release_year FROM album_art WHERE release_year IS NOT NULL"
        ).fetchall()
        for r in rows:
            album_years[(r["album_name"], r["artist_name"])] = r["release_year"]

        from collections import Counter, defaultdict

        decade_plays = Counter()
        decade_artists = defaultdict(set)
        decade_albums = defaultdict(set)
        scatter_cells = Counter()
        unknown_tracks = 0
        total_tracks = 0

        tracks = main_db.execute("""
            SELECT t.artist, t.album, strftime('%Y', e.date) as broadcast_year
            FROM tracks t
            JOIN episodes e ON e.id = t.episode_id
            WHERE t.album != '' AND e.date != ''
        """).fetchall()

        for t in tracks:
            total_tracks += 1
            year = album_years.get((t["album"], t["artist"]))
            if year:
                decade = (year // 10) * 10
                decade_plays[decade] += 1
                decade_artists[decade].add(t["artist"])
                decade_albums[decade].add((t["artist"], t["album"]))
                if t["broadcast_year"]:
                    scatter_cells[(year, int(t["broadcast_year"]))] += 1
            else:
                unknown_tracks += 1

        items = []
        for decade in sorted(decade_plays.keys()):
            items.append({
                "decade": decade,
                "plays": decade_plays[decade],
                "artists": len(decade_artists[decade]),
                "albums": len(decade_albums[decade]),
            })

        scatter = []
        for (release_year, broadcast_year), count in sorted(scatter_cells.items()):
            scatter.append({
                "release_year": release_year,
                "broadcast_year": broadcast_year,
                "plays": count,
            })

        return {
            "items": items,
            "scatter": scatter,
            "total_tracks": total_tracks,
            "unknown_tracks": unknown_tracks,
        }
    finally:
        main_db.close()
        enrich.close()
