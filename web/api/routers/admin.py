import json
import re
import sqlite3
from fastapi import APIRouter, Request, HTTPException, Depends
from ..services.enrichment import get_artist_enrichment

router = APIRouter(tags=["admin"])


# ── Auth ─────────────────────────────────────────────────────────────

async def require_admin(request: Request):
    """Gate admin endpoints. In dev (no ADMIN_API_KEY set) all requests pass."""
    key = request.app.state.admin_key
    if not key:
        return
    provided = request.headers.get("x-admin-key", "")
    if provided != key:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/check")
async def check_admin(request: Request):
    """Verify admin credentials. Returns 200 if key is valid or not configured."""
    key = request.app.state.admin_key
    if not key:
        return {"ok": True, "mode": "dev"}
    provided = request.headers.get("x-admin-key", "")
    if provided == key:
        return {"ok": True, "mode": "prod"}
    raise HTTPException(status_code=401, detail="Unauthorized")


# ── Helpers ──────────────────────────────────────────────────────────

def _db(request: Request) -> sqlite3.Connection:
    db = sqlite3.connect(request.app.state.db_path)
    db.row_factory = sqlite3.Row
    return db



def _base_name(name: str) -> str:
    """Extract the base/canonical part of a collaboration-style name.

    Splits on separators BEFORE stripping punctuation so that
    "Charles M. Bogert + frogs" correctly yields "charles m bogert".
    Also handles parenthetical cross-references like
    "Frogs (+ Charles M. Bogert)" → "charles m bogert".
    """
    n = name.strip()

    # Handle parenthetical cross-references first:
    # "X (+ Y)" or "X (feat. Y)" — use the parenthetical if the outer
    # part looks like a category word (short, no proper name structure).
    m = re.match(r'^([\w\s]{1,15}?)\s*\([^)]*?([+&/])\s*([\w\s.]{5,})\s*\)$', n)
    if m:
        outer = m.group(1).strip()
        inner = m.group(3).strip()
        if len(outer.split()) <= 2 or outer.lower() in ('various', 'misc', 'plus', 'and', 'feat', 'with'):
            n = inner

    # Split on collaboration separators case-insensitively
    n_lower = n.lower()
    for sep in [
        ' & ', ' w/ ', ' + ', ' feat ', ' vs ', ' / ',
        ' with ', ' and ', ' x ', ' con ', ' y ', ' mit ',
        ' avec ', ' plus ', ' en ', ' et ',
    ]:
        parts = n_lower.split(sep)
        if len(parts) > 1:
            # Find the actual split position in the original-cased string
            idx = n.lower().find(sep)
            if idx != -1:
                n = n[:idx]
                break

    # Normalize
    n = n.lower().strip()
    n = re.sub(r'[^\w\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def _trigram_similarity(a: str, b: str) -> float:
    """Simple trigram overlap similarity."""
    def trigrams(s: str):
        return {s[i:i+3] for i in range(len(s) - 2)}
    if not a or not b:
        return 0.0
    a = a.lower().strip()
    b = b.lower().strip()
    ta = trigrams(a)
    tb = trigrams(b)
    if not ta and not tb:
        return 1.0
    intersection = ta & tb
    union = ta | tb
    return len(intersection) / len(union) if union else 0.0


# ── MusicBrainz helpers ────────────────────────────────────────────

_UA = "HenryRollinsListensTo/1.0 (music analytics project)"


def _fetch_recording(mbid: str) -> dict | None:
    """Fetch recording (track) info from MusicBrainz by MBID.
    Returns title and credited artist, or None on failure."""
    try:
        import requests
        resp = requests.get(
            f"https://musicbrainz.org/ws/2/recording/{mbid}",
            params={"fmt": "json", "inc": "artist-credits"},
            headers={"User-Agent": _UA},
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        title = data.get("title")
        artist = None
        for credit in data.get("artist-credit") or []:
            if isinstance(credit, dict) and credit.get("name"):
                artist = credit["name"]
                break
        if title:
            return {"title": title, "artist": artist}
        return None
    except Exception:
        return None


@router.get("/resolve-recording/{mbid}")
async def resolve_recording(mbid: str, _=Depends(require_admin)):
    """Resolve a recording MBID to title + artist from MusicBrainz."""
    result = _fetch_recording(mbid)
    if not result:
        raise HTTPException(status_code=404, detail="Recording not found")
    return result


def _fetch_release(mbid: str) -> dict | None:
    """Fetch release info from MusicBrainz by MBID (release).
    Returns title and credited artist, or None on failure."""
    try:
        import requests
        resp = requests.get(
            f"https://musicbrainz.org/ws/2/release/{mbid}",
            params={"fmt": "json", "inc": "artist-credits"},
            headers={"User-Agent": _UA},
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        title = data.get("title")
        artist = None
        for credit in data.get("artist-credit") or []:
            if isinstance(credit, dict) and credit.get("name"):
                artist = credit["name"]
                break
        if title:
            return {"title": title, "artist": artist}
        return None
    except Exception:
        return None


# ── Cluster Detection ───────────────────────────────────────────────

@router.get("/clusters")
async def get_clusters(
    request: Request,
    type: str = "artist",
    min_size: int = 2,
    min_tracks: int = 1,
    show_lonely: bool = False,
    _=Depends(require_admin),
):
    """Detect duplicate clusters using fuzzy name matching.

    Groups entities by a normalised "base name", then uses trigram
    similarity within each base group to catch typos & case variants.
    Returns clusters ranked by total track impact (largest first).

    When show_lonely=True, also returns "lonely" entities — ones that
    contain collaboration separators (&, +, w/, etc.) but didn't form
    a cluster because no similar entity was found.
    """
    db = _db(request)
    try:
        if type == "artist":
            rows = db.execute("""
                SELECT
                    a.id,
                    a.name,
                    COALESCE(a.mbid, ae.mbid) AS mbid,
                    (SELECT COUNT(*) FROM tracks WHERE artist_id = a.id) AS track_count,
                    (SELECT COUNT(*) FROM albums WHERE artist_id = a.id) AS album_count
                FROM artists a
                LEFT JOIN artist_enrichment ae ON ae.artist_name = a.name
                ORDER BY a.name
            """).fetchall()
        else:
            rows = db.execute("""
                SELECT
                    al.id,
                    al.name,
                    al.artist_id,
                    COALESCE(ar.name, '(orphaned)') AS artist_name,
                    (SELECT COUNT(*) FROM tracks WHERE album_id = al.id) AS track_count,
                    0 AS album_count
                FROM albums al
                LEFT JOIN artists ar ON al.artist_id = ar.id
                ORDER BY ar.name, al.name
            """).fetchall()

        # Build entities list
        entities = [dict(r) for r in rows]

        # Group by (artist_id, base_name) for albums, base_name alone for artists
        groups: dict[str, list[dict]] = {}
        for ent in entities:
            base = _base_name(ent["name"])
            key = base
            if type == "album":
                key = f"{ent['artist_id']}||{base}"
            groups.setdefault(key, []).append(ent)

        # Build clusters from groups with enough variants
        clusters = []
        seen_ids = set()

        for key, variants in groups.items():
            if len(variants) < min_size:
                continue
            total_tracks = sum(v["track_count"] for v in variants)
            if total_tracks < min_tracks:
                continue

            # Extract the actual base name (for albums the key is "artist_id||base")
            base_name_raw = key.split("||", 1)[-1] if "||" in key else key
            artist_for_cluster = variants[0].get("artist_name", "") if type == "album" else ""

            # Further split: within this base group, check trigram similarity
            # to avoid false groupings from very short base names
            cluster_variants = []
            for v in variants:
                sim = _trigram_similarity(base_name_raw, v["name"])
                # Accept if base is a strong trigram match OR
                # if the normalized name contains the base
                normalized = v["name"].lower().strip()
                normalized = re.sub(r'[^\w\s]', ' ', normalized)
                normalized = re.sub(r'\s+', ' ', normalized).strip()
                if sim > 0.3 or base_name_raw in normalized:
                    if v["id"] not in seen_ids:
                        variant_data = {
                            "id": v["id"],
                            "name": v["name"],
                            "tracks": v["track_count"],
                            "albums": v.get("album_count", 0),
                            "mbid": v.get("mbid"),
                        }
                        if type == "album":
                            variant_data["artist_name"] = v.get("artist_name", "")
                        cluster_variants.append(variant_data)
                        seen_ids.add(v["id"])

            if len(cluster_variants) >= min_size:
                # Skip clusters where ALL variants already have MBIDs
                if type == "artist" and all(v.get("mbid") for v in cluster_variants):
                    continue
                cluster_variants.sort(key=lambda x: x["tracks"], reverse=True)
                total = sum(v["tracks"] for v in cluster_variants)
                display_name = base_name_raw.title().strip()
                if artist_for_cluster:
                    display_name = f"{display_name} ({artist_for_cluster})"
                clusters.append({
                    "base_name": display_name,
                    "total_tracks": total,
                    "variant_count": len(cluster_variants),
                    "variants": cluster_variants,
                })

        # ── Secondary merge: absorb satellite clusters where one base
        #    name is a word-subset of another (e.g.
        #    "Charles Bogert" → "Charles M Bogert").
        merged_keys = set()
        for i, big in enumerate(clusters):
            if i in merged_keys:
                continue
            big_words = set(big["base_name"].lower().split())
            for j, small in enumerate(clusters):
                if i == j or j in merged_keys:
                    continue
                small_words = set(small["base_name"].lower().split())
                # Absorb if all words of the smaller base appear in the
                # larger base AND the smaller name is at least 4 chars
                # (avoids false merges like "Tom" → "Tom Waits" when
                #  there's a real 1-word artist called "Tom")
                if len(small["base_name"]) >= 4 and small_words.issubset(big_words):
                    big["variants"].extend(small["variants"])
                    big["variants"].sort(key=lambda v: v["tracks"], reverse=True)
                    big["total_tracks"] += small["total_tracks"]
                    big["variant_count"] = len(big["variants"])
                    merged_keys.add(j)

        # Keep only un-merged clusters (and the ones that absorbed others)
        clusters = [c for i, c in enumerate(clusters) if i not in merged_keys]
        clusters.sort(key=lambda c: c["total_tracks"], reverse=True)

        # ── Filter out ignored clusters ──
        _ensure_ignored_clusters(db)
        ignored_rows = db.execute(
            "SELECT entity_ids FROM ignored_clusters WHERE entity_type = ?", (type,)
        ).fetchall()
        ignored_sets = set()
        for row in ignored_rows:
            ids = tuple(sorted(int(x) for x in row["entity_ids"].split(",") if x.strip().isdigit()))
            if ids:
                ignored_sets.add(ids)

        clusters = [
            c for c in clusters
            if tuple(sorted(v["id"] for v in c["variants"])) not in ignored_sets
        ]

        # ── Lonely variants: entities with collaboration separators
        #    that didn't form a cluster. These are easy-to-miss orphans.
        lonely = []
        if show_lonely:
            collab_seps = [' & ', ' + ', ' w/', ' feat ', ' vs ', ' / ']
            for ent in entities:
                if ent["id"] not in seen_ids:
                    # Skip entities that already have an MBID — they're legitimate
                    if ent.get("mbid"):
                        continue
                    name_lower = ent["name"].lower()
                    if not any(sep in name_lower for sep in collab_seps):
                        continue
                    # Skip legitimate band names: starts with "The" and has
                    # significant plays, or has more than 20 tracks (not a variant)
                    if (name_lower.startswith("the ") or name_lower.startswith("a ")) and ent["track_count"] >= 5:
                        continue
                    if ent["track_count"] >= 15:
                        continue
                    lonely.append({
                        "id": ent["id"],
                        "name": ent["name"],
                        "tracks": ent["track_count"],
                        "albums": ent.get("album_count", 0),
                    })
            lonely.sort(key=lambda x: x["tracks"], reverse=True)

        return {"clusters": clusters, "lonely": lonely}

    finally:
        db.close()


# ── Merge (bulk, with preview) ──────────────────────────────────────

@router.post("/merge/preview")
async def merge_preview(
    request: Request,
    type: str = "artist",
    source_ids: str = "",
    target_id: int = 0,
    _=Depends(require_admin),
):
    """Preview what a merge would do without executing it.

    source_ids: comma-separated list of entity IDs to merge INTO target_id.
    """
    ids = _parse_ids(source_ids)
    if not ids or not target_id:
        raise HTTPException(status_code=400, detail="source_ids and target_id are required")
    return _merge_impl(request, type, ids, target_id, preview=True)


@router.post("/merge")
async def merge(
    request: Request,
    type: str = "artist",
    source_ids: str = "",
    target_id: int = 0,
    _=Depends(require_admin),
):
    """Merge multiple source entities into a single target entity.

    source_ids: comma-separated list of entity IDs to merge INTO target_id.
    """
    ids = _parse_ids(source_ids)
    if not ids or not target_id:
        raise HTTPException(status_code=400, detail="source_ids and target_id are required")
    return _merge_impl(request, type, ids, target_id, preview=False)


def _parse_ids(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]


def _ensure_migration_log(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS migration_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            old_name TEXT NOT NULL,
            new_name TEXT NOT NULL,
            affected_count INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)


def _ensure_corrections(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER,
            episode_id INTEGER,
            type TEXT NOT NULL,
            original_data TEXT,
            corrected_data TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _ensure_ignored_clusters(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS ignored_clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_ids TEXT NOT NULL,
            display_name TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)


def _merge_artist_rows(db: sqlite3.Connection, source_id: int, target_id: int, target_name: str) -> tuple[int, int]:
    """Reassign every track/album from source_id to target_id, resolving album-name
    collisions, rewrite the tracks.artist text column for the WHOLE target (not just
    the newly-reassigned rows, so any pre-existing text drift under target_id gets
    self-healed too), and delete the source artist row.

    This is the one and only way an artist identity gets merged — used by the bulk
    /merge endpoint and by /rename-artist when the rename target already exists, so
    there's exactly one code path that can leave tracks.artist out of sync with
    artist_id.

    Returns (tracks_affected, albums_affected).
    """
    track_count = db.execute("SELECT COUNT(*) FROM tracks WHERE artist_id = ?", (source_id,)).fetchone()[0]
    album_count = db.execute("SELECT COUNT(*) FROM albums WHERE artist_id = ?", (source_id,)).fetchone()[0]

    conflicts = db.execute("""
        SELECT s.id AS source_album_id, t.id AS target_album_id
        FROM albums s
        JOIN albums t ON s.name = t.name
        WHERE s.artist_id = ? AND t.artist_id = ?
    """, (source_id, target_id)).fetchall()
    for c in conflicts:
        db.execute("UPDATE tracks SET album_id = ? WHERE album_id = ?",
                   (c["target_album_id"], c["source_album_id"]))
        db.execute("DELETE FROM albums WHERE id = ?", (c["source_album_id"],))

    db.execute("UPDATE albums SET artist_id = ? WHERE artist_id = ?", (target_id, source_id))
    db.execute("UPDATE tracks SET artist_id = ? WHERE artist_id = ?", (target_id, source_id))
    db.execute("UPDATE tracks SET artist = ? WHERE artist_id = ? AND artist != ?",
               (target_name, target_id, target_name))
    db.execute("DELETE FROM artists WHERE id = ?", (source_id,))

    return track_count, album_count


def _merge_album_rows(db: sqlite3.Connection, source_id: int, target_id: int, target_name: str) -> int:
    """Reassign every track from source_id to target_id, rewrite tracks.album for the
    whole target (self-healing any pre-existing drift), and delete the source album row.
    Returns tracks_affected."""
    track_count = db.execute("SELECT COUNT(*) FROM tracks WHERE album_id = ?", (source_id,)).fetchone()[0]

    db.execute("UPDATE tracks SET album_id = ? WHERE album_id = ?", (target_id, source_id))
    db.execute("UPDATE tracks SET album = ? WHERE album_id = ? AND album != ?",
               (target_name, target_id, target_name))
    db.execute("DELETE FROM albums WHERE id = ?", (source_id,))

    return track_count


def _sync_enrichment_cache(db: sqlite3.Connection, entity_type: str, stale_name: str) -> None:
    """Delete a now-stale enrichment cache row after a rename/merge — the next
    lookup under the surviving name will fetch and cache fresh data.

    artist_enrichment/album_art are keyed by raw name text, independent of
    artists.id/albums.id, so merging or renaming an artist/album doesn't
    automatically clean up its old cache entry — this does that, in the
    same transaction as the rest of the merge/rename (one connection, one
    database, since the consolidation in docs/plan-single-source-of-truth.md).
    """
    if entity_type == "artist":
        db.execute("DELETE FROM artist_enrichment WHERE artist_name = ?", (stale_name,))
    else:
        db.execute("DELETE FROM album_art WHERE album_name = ?", (stale_name,))


def _merge_impl(
    request: Request,
    entity_type: str,
    source_ids: list[int],
    target_id: int,
    preview: bool = False,
):
    db = _db(request)
    try:
        _ensure_migration_log(db)
        db.execute("BEGIN TRANSACTION")

        # Fetch names for logging
        target_row = db.execute(
            "SELECT name FROM {} WHERE id = ?".format(
                "artists" if entity_type == "artist" else "albums"
            ),
            (target_id,),
        ).fetchone()
        if not target_row:
            raise HTTPException(status_code=404, detail=f"Target {entity_type} id={target_id} not found")
        target_name = target_row["name"]

        total_affected_tracks = 0
        total_affected_albums = 0
        details = []

        for source_id in source_ids:
            source_row = db.execute(
                "SELECT name FROM {} WHERE id = ?".format(
                    "artists" if entity_type == "artist" else "albums"
                ),
                (source_id,),
            ).fetchone()
            if not source_row:
                continue  # skip already-deleted
            source_name = source_row["name"]

            affected_tracks = 0
            affected_albums = 0

            if entity_type == "artist":
                if preview:
                    affected_tracks = db.execute(
                        "SELECT COUNT(*) FROM tracks WHERE artist_id = ?", (source_id,)
                    ).fetchone()[0]
                    affected_albums = db.execute(
                        "SELECT COUNT(*) FROM albums WHERE artist_id = ?", (source_id,)
                    ).fetchone()[0]
                else:
                    affected_tracks, affected_albums = _merge_artist_rows(db, source_id, target_id, target_name)
                    db.execute(
                        "INSERT INTO migration_log (entity_type, old_name, new_name, affected_count) VALUES (?, ?, ?, ?)",
                        ("artist", source_name, target_name, affected_tracks),
                    )

            else:  # album
                if preview:
                    affected_tracks = db.execute(
                        "SELECT COUNT(*) FROM tracks WHERE album_id = ?", (source_id,)
                    ).fetchone()[0]
                    affected_albums = 1
                else:
                    affected_tracks = _merge_album_rows(db, source_id, target_id, target_name)
                    affected_albums = 1
                    db.execute(
                        "INSERT INTO migration_log (entity_type, old_name, new_name, affected_count) VALUES (?, ?, ?, ?)",
                        ("album", source_name, target_name, affected_tracks),
                    )

            total_affected_tracks += affected_tracks
            total_affected_albums += affected_albums
            details.append({
                "source_id": source_id,
                "source_name": source_name,
                "affected_tracks": affected_tracks,
                "affected_albums": affected_albums,
            })

        if preview:
            db.rollback()
            return {
                "preview": True,
                "target_id": target_id,
                "target_name": target_name,
                "total_affected_tracks": total_affected_tracks,
                "total_affected_albums": total_affected_albums,
                "details": details,
            }
        else:
            # Clean up stale enrichment-cache rows for merged source entities,
            # in the same transaction as the merge itself.
            for detail in details:
                _sync_enrichment_cache(db, entity_type, detail["source_name"])
            db.commit()

            return {
                "status": "success",
                "target_id": target_id,
                "target_name": target_name,
                "total_affected_tracks": total_affected_tracks,
                "total_affected_albums": total_affected_albums,
                "details": details,
            }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


# ── Original Endpoints (kept for backward compat) ───────────────────

@router.get("/entities")
async def list_entities(request: Request, type: str = "artist", q: str = "", artist_id: int = 0, _=Depends(require_admin)):
    db = _db(request)
    try:
        if type == "artist":
            query = "SELECT id, name, (SELECT COUNT(*) FROM tracks WHERE artist_id = artists.id) as track_count FROM artists WHERE name LIKE ? ORDER BY track_count DESC LIMIT 20"
            rows = db.execute(query, (f"%{q}%",)).fetchall()
        else:
            # Query tracks for actual album names + join album_art for enrichment
            query = """SELECT t.album AS name, t.artist AS artist_name,
                             ar.id AS artist_id,
                             COUNT(*) AS track_count,
                             aa.mbid, aa.release_group_mbid, aa.release_year
                      FROM tracks t
                      JOIN artists ar ON ar.name = t.artist
                      LEFT JOIN album_art aa ON aa.album_name = t.album AND aa.artist_name = t.artist
                      WHERE t.album LIKE ?"""
            params = [f"%{q}%"]
            if artist_id:
                query += " AND ar.id = ?"
                params.append(artist_id)
            query += " GROUP BY t.album, t.artist ORDER BY track_count DESC LIMIT 20"
            rows = db.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


@router.post("/reassign")
async def reassign(request: Request, type: str, source_id: int, target_id: int, _=Depends(require_admin)):
    """Legacy single-source reassign — delegates to bulk merge."""
    return _merge_impl(request, type, [source_id], target_id, preview=False)


# ── Track corrections ───────────────────────────────────────────────

@router.post("/correction")
async def submit_correction(request: Request, _=Depends(require_admin)):
    """Save a track correction (edit or add) to the enrichment database.

    Payload:
        type: "TRACK_EDIT" | "TRACK_ADD"
        track_id: int | null
        episode_id: int
        original_data: dict | null
        corrected_data: dict
    """
    body = await request.json()
    correction_type = body.get("type", "TRACK_EDIT")
    track_id = body.get("track_id")
    episode_id = body.get("episode_id")
    original = body.get("original_data")
    corrected = body.get("corrected_data")

    if not corrected:
        raise HTTPException(status_code=400, detail="corrected_data is required")
    if correction_type == "TRACK_ADD" and not episode_id:
        raise HTTPException(status_code=400, detail="episode_id is required for TRACK_ADD")

    main_db = _db(request)
    _ensure_corrections(main_db)
    main_db.execute("""
        INSERT INTO corrections (track_id, episode_id, type, original_data, corrected_data)
        VALUES (?, ?, ?, ?, ?)
    """, (
        track_id,
        episode_id,
        correction_type,
        json.dumps(original) if original else None,
        json.dumps(corrected),
    ))
    main_db.commit()

    # Also update the actual track(s)
    try:
        if correction_type == "TRACK_ADD":
            ep_row = main_db.execute("SELECT id FROM episodes WHERE broadcast = ?", (episode_id,)).fetchone()
            if not ep_row:
                raise HTTPException(status_code=400, detail="Episode not found")
            resolved_episode_id = ep_row["id"]

            title = corrected.get("title") or ""
            artist = corrected.get("artist") or ""
            album = corrected.get("album") or ""
            hour = corrected.get("hour") or 0
            position = corrected.get("position") or 0

            # Resolve artist_id: exact match first, then case-insensitive
            artist_id = None
            canonical_artist = artist
            if artist:
                row = main_db.execute("SELECT id, name FROM artists WHERE name = ?", (artist,)).fetchone()
                if row:
                    artist_id = row["id"]
                else:
                    row = main_db.execute("SELECT id, name FROM artists WHERE LOWER(name) = LOWER(?)", (artist,)).fetchone()
                    if row:
                        artist_id = row["id"]
                        canonical_artist = row["name"]
                if not artist_id:
                    main_db.execute("INSERT INTO artists (name) VALUES (?)", (artist,))
                    artist_id = main_db.execute("SELECT last_insert_rowid()").fetchone()[0]

            # Resolve album_id: exact match first, then case-insensitive
            album_id = None
            canonical_album = album
            if album and artist_id:
                row = main_db.execute(
                    "SELECT id, name FROM albums WHERE name = ? AND artist_id = ?", (album, artist_id)
                ).fetchone()
                if row:
                    album_id = row["id"]
                else:
                    row = main_db.execute(
                        "SELECT id, name FROM albums WHERE LOWER(name) = LOWER(?) AND artist_id = ?", (album, artist_id)
                    ).fetchone()
                    if row:
                        album_id = row["id"]
                        canonical_album = row["name"]
                if not album_id:
                    main_db.execute(
                        "INSERT INTO albums (name, artist_id) VALUES (?, ?)", (album, artist_id)
                    )
                    album_id = main_db.execute("SELECT last_insert_rowid()").fetchone()[0]

            track_mbid = corrected.get("track_mbid")
            if track_mbid:
                try:
                    main_db.execute("ALTER TABLE tracks ADD COLUMN mbid TEXT")
                except Exception:
                    pass

            main_db.execute(
                """INSERT INTO tracks (episode_id, hour, position, artist, title, album, artist_id, album_id, mbid)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (resolved_episode_id, hour, position, canonical_artist, title, canonical_album, artist_id, album_id, track_mbid),
            )
            main_db.commit()
            return {"status": "ok"}

        if correction_type == "TRACK_EDIT":
            # ── Auto-resolve names from MBIDs before propagation ──
            album_mbid = corrected.get("album_mbid")
            if album_mbid and not corrected.get("album"):
                release = _fetch_release(album_mbid)
                if release and release.get("title"):
                    corrected["album"] = release["title"]

            track_mbid = corrected.get("track_mbid")
            if track_mbid:
                rc = _fetch_recording(track_mbid)
                if rc:
                    if rc.get("title") and not corrected.get("title"):
                        corrected["title"] = rc["title"]
                    if rc.get("artist") and not corrected.get("artist"):
                        corrected["artist"] = rc["artist"]

            # ── Tracks: update specific row + propagate ──
            if track_id:
                fields = []
                params = []
                for col in ("title", "artist", "album"):
                    if col in corrected:
                        fields.append(f"{col} = ?")
                        params.append(corrected[col])
                if fields:
                    params.append(track_id)
                    main_db.execute(f"UPDATE tracks SET {', '.join(fields)} WHERE id = ?", params)

            if original and corrected:
                orig_title = original.get("title")
                new_title = corrected.get("title")
                orig_artist = original.get("artist")
                new_artist = corrected.get("artist")
                album = original.get("album") or corrected.get("album")

                if album:
                    orig_album = original.get("album")
                    new_album = corrected.get("album")
                    if new_album and orig_album and new_album != orig_album:
                        main_db.execute(
                            "UPDATE tracks SET album = ? WHERE album = ? AND artist = ?",
                            (new_album, orig_album, orig_artist or new_artist),
                        )
                if new_title and orig_title and new_title != orig_title:
                    main_db.execute(
                        "UPDATE tracks SET title = ? WHERE title = ? AND album = ? AND artist = ?",
                        (new_title, orig_title, album, orig_artist or new_artist),
                    )
                if new_artist and orig_artist and new_artist != orig_artist:
                    main_db.execute(
                        "UPDATE tracks SET artist = ? WHERE artist = ? AND album = ?",
                        (new_artist, orig_artist, album),
                    )

            # ── Track MBID column (per-track, after title resolution) ──
            if track_mbid:
                try:
                    main_db.execute("ALTER TABLE tracks ADD COLUMN mbid TEXT")
                except sqlite3.OperationalError:
                    pass
            if track_mbid and track_id:
                main_db.execute("UPDATE tracks SET mbid = ? WHERE id = ?", (track_mbid, track_id))
            elif track_mbid:
                # No track_id (album/artist view) — apply to all matching tracks
                title_val = corrected.get("title") or (original.get("title") if original else None)
                artist_val = corrected.get("artist") or (original.get("artist") if original else None)
                album_val = corrected.get("album") or (original.get("album") if original else None)
                if title_val and artist_val:
                    where = ["title = ?", "artist = ?"]
                    params = [title_val, artist_val]
                    if album_val:
                        where.append("album = ?")
                        params.append(album_val)
                    main_db.execute(
                        f"UPDATE tracks SET mbid = ? WHERE {' AND '.join(where)}",
                        [track_mbid] + params,
                    )

            # ── Album MBID + enrichment cache ──
            release_group_mbid = corrected.get("album_release_group_mbid")
            if album_mbid or release_group_mbid:
                album_name = corrected.get("album") or (original.get("album") if original else None)
                artist_name = corrected.get("artist") or (original.get("artist") if original else None)
                if album_name and artist_name:
                    main_db.execute("""
                        UPDATE albums SET mbid = COALESCE(?, mbid)
                        WHERE name = ? AND artist_id = (SELECT id FROM artists WHERE name = ?)
                    """, (album_mbid, album_name, artist_name))
                    main_db.execute("""
                        INSERT INTO album_art (album_name, artist_name, mbid, release_group_mbid, last_fetched)
                        VALUES (?, ?, ?, ?, datetime('now'))
                        ON CONFLICT(album_name, artist_name) DO UPDATE SET
                            mbid = COALESCE(excluded.mbid, mbid),
                            release_group_mbid = COALESCE(excluded.release_group_mbid, release_group_mbid),
                            last_fetched = datetime('now')
                    """, (album_name, artist_name, album_mbid, release_group_mbid))

            main_db.commit()
    finally:
        main_db.close()

    return {"status": "saved"}


# ── Album level editing ────────────────────────────────────────────

@router.post("/merge-ensure-row")
async def merge_ensure_row(request: Request, _=Depends(require_admin)):
    """Ensure an album has a row in the albums table, creating one if missing."""
    body = await request.json()
    artist = body.get("artist", "")
    name = body.get("name", "")
    if not artist or not name:
        raise HTTPException(status_code=400, detail="artist and name are required")

    main_db = sqlite3.connect(request.app.state.db_path)
    main_db.row_factory = sqlite3.Row
    try:
        artist_row = main_db.execute(
            "SELECT id FROM artists WHERE name = ?", (artist,)
        ).fetchone()
        if not artist_row:
            raise HTTPException(status_code=404, detail="Artist not found")

        album = main_db.execute(
            "SELECT id FROM albums WHERE name = ? AND artist_id = ?",
            (name, artist_row["id"]),
        ).fetchone()
        if album:
            return {"id": album["id"]}

        main_db.execute(
            "INSERT INTO albums (artist_id, name) VALUES (?, ?)",
            (artist_row["id"], name),
        )
        main_db.commit()
        return {"id": main_db.lastrowid}
    finally:
        main_db.close()


@router.post("/edit-album")
async def edit_album(request: Request, _=Depends(require_admin)):
    """Edit album name and/or MBIDs. Rename propagates to all tracks.

    Body:
        artist: str (required)
        old_name: str (required — current album name)
        name: str | None (new album name, omit to keep)
        mbid: str | None
        release_group_mbid: str | None
    """
    body = await request.json()
    artist = body.get("artist", "")
    old_name = body.get("old_name", "")
    new_name = body.get("name") or old_name
    mbid = body.get("mbid")
    release_group_mbid = body.get("release_group_mbid")

    # Auto-resolve album name from MBID if no custom name given
    if mbid and not body.get("name"):
        release = _fetch_release(mbid)
        if release and release.get("title"):
            new_name = release["title"]

    if not artist or not old_name:
        raise HTTPException(status_code=400, detail="artist and old_name are required")

    main_db = _db(request)
    try:
        # Propagate name change to tracks table
        if new_name != old_name:
            main_db.execute(
                "UPDATE tracks SET album = ? WHERE album = ? AND artist = ?",
                (new_name, old_name, artist),
            )

        # Update albums table
        # Try exact artist match first, then case-insensitive, then by track artist
        artist_id_row = main_db.execute("SELECT id FROM artists WHERE name = ?", (artist,)).fetchone()
        if not artist_id_row:
            artist_id_row = main_db.execute("SELECT id FROM artists WHERE LOWER(name) = LOWER(?)", (artist,)).fetchone()
        album = None
        if artist_id_row:
            album = main_db.execute(
                "SELECT id, artist_id FROM albums WHERE name = ? AND artist_id = ?",
                (old_name, artist_id_row["id"]),
            ).fetchone()
        if not album:
            # Last resort: find album by name alone
            album = main_db.execute(
                "SELECT id, artist_id FROM albums WHERE LOWER(name) = LOWER(?)", (old_name,)
            ).fetchone()

        if album:
            if new_name != old_name:
                # Check for target collision
                target = main_db.execute(
                    """SELECT id FROM albums
                       WHERE name = ? AND artist_id = ?""",
                    (new_name, album["artist_id"]),
                ).fetchone()
                if target:
                    main_db.execute("UPDATE tracks SET album_id = ? WHERE album_id = ?",
                                    (target["id"], album["id"]))
                    main_db.execute("DELETE FROM albums WHERE id = ?", (album["id"],))
                    album = target
                else:
                    main_db.execute("UPDATE albums SET name = ? WHERE id = ?",
                                    (new_name, album["id"]))

            if mbid:
                main_db.execute("UPDATE albums SET mbid = ? WHERE id = ?", (mbid, album["id"]))

        elif mbid and new_name:
            # Album row may not exist yet — create it or update by name
            artist_row = main_db.execute(
                "SELECT id FROM artists WHERE name = ?", (artist,)
            ).fetchone()
            if not artist_row:
                artist_row = main_db.execute(
                    "SELECT id FROM artists WHERE LOWER(name) = LOWER(?)", (artist,)
                ).fetchone()
            if artist_row:
                main_db.execute(
                    "INSERT OR REPLACE INTO albums (artist_id, name, mbid) VALUES (?, ?, ?)",
                    (artist_row["id"], new_name, mbid),
                )

        # Keep album_art in sync under the new name, regardless of which
        # branch above fired.
        main_db.execute("""
            INSERT INTO album_art (album_name, artist_name, mbid, release_group_mbid, last_fetched)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(album_name, artist_name) DO UPDATE SET
                mbid = COALESCE(excluded.mbid, mbid),
                release_group_mbid = COALESCE(excluded.release_group_mbid, release_group_mbid),
                last_fetched = datetime('now')
        """, (new_name, artist, mbid, release_group_mbid))

        # Renaming leaves the old name's cache row orphaned (album_art is
        # keyed by raw name text, not album id) — clean it up.
        if new_name != old_name:
            main_db.execute(
                "DELETE FROM album_art WHERE album_name = ? AND artist_name = ?",
                (old_name, artist),
            )

        main_db.commit()
    finally:
        main_db.close()

    return {"status": "ok", "artist": artist, "name": new_name, "mbid": mbid}


@router.post("/rename-track")
async def rename_track(request: Request, _=Depends(require_admin)):
    """Rename a track title across an entire album+artist combination.
    Useful for fixing case inconsistencies without per-episode editing.

    Body:
        album: str (required)
        artist: str (required)
        old_title: str (required)
        new_title: str (required)
    """
    body = await request.json()
    album = body.get("album")
    artist = body.get("artist")
    old_title = body.get("old_title")
    new_title = body.get("new_title")

    if not all([album, artist, old_title, new_title]):
        raise HTTPException(status_code=400, detail="album, artist, old_title, and new_title are required")

    main_db = sqlite3.connect(request.app.state.db_path)
    try:
        affected = main_db.execute(
            "UPDATE tracks SET title = ? WHERE title = ? AND album = ? AND artist = ?",
            (new_title, old_title, album, artist),
        ).rowcount
        main_db.commit()
        return {"status": "ok", "renamed": affected}
    finally:
        main_db.close()


@router.post("/rename-artist")
async def rename_artist(request: Request, _=Depends(require_admin)):
    """Rename an artist everywhere: artists table + tracks table.
    If target artist already exists, merges into it via the same _merge_artist_rows
    path /merge uses. Either way, the tracks.artist rewrite is scoped by artist_id
    (not by matching the old text), so it also self-heals any pre-existing text
    drift under that artist — not just the rows that literally said old_name."""
    body = await request.json()
    old_name = body.get("old_name", "")
    new_name = body.get("new_name", "")

    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="old_name and new_name are required")

    db = _db(request)
    try:
        _ensure_migration_log(db)
        db.execute("BEGIN TRANSACTION")

        old_artist = db.execute("SELECT id FROM artists WHERE name = ?", (old_name,)).fetchone()
        if not old_artist:
            raise HTTPException(status_code=404, detail=f"Artist '{old_name}' not found")

        target_artist = db.execute("SELECT id FROM artists WHERE name = ?", (new_name,)).fetchone()

        if target_artist:
            track_affected, _ = _merge_artist_rows(db, old_artist["id"], target_artist["id"], new_name)
        else:
            db.execute("UPDATE artists SET name = ? WHERE id = ?", (new_name, old_artist["id"]))
            cur = db.execute(
                "UPDATE tracks SET artist = ? WHERE artist_id = ? AND artist != ?",
                (new_name, old_artist["id"], new_name),
            )
            track_affected = cur.rowcount

        db.execute(
            "INSERT INTO migration_log (entity_type, old_name, new_name, affected_count) VALUES (?, ?, ?, ?)",
            ("artist", old_name, new_name, track_affected),
        )
        _sync_enrichment_cache(db, "artist", old_name)
        db.commit()

        return {"status": "ok", "artists_updated": 1, "tracks_updated": track_affected}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.post("/rename-album")
async def rename_album(request: Request, _=Depends(require_admin)):
    """Rename an album everywhere: albums table + tracks table.
    If target album already exists, merges into it via the same _merge_album_rows
    path /merge uses. The tracks.album rewrite is scoped by album_id, so it also
    self-heals any pre-existing text drift under that album."""
    body = await request.json()
    old_name = body.get("old_name", "")
    new_name = body.get("new_name", "")
    artist = body.get("artist", "")

    if not old_name or not new_name or not artist:
        raise HTTPException(status_code=400, detail="old_name, new_name, and artist are required")

    db = _db(request)
    try:
        _ensure_migration_log(db)
        db.execute("BEGIN TRANSACTION")

        old_album = db.execute(
            "SELECT a.id, a.artist_id FROM albums a WHERE a.name = ? AND a.artist_id = (SELECT id FROM artists WHERE name = ?)",
            (old_name, artist),
        ).fetchone()
        if not old_album:
            raise HTTPException(status_code=404, detail=f"Album '{old_name}' by '{artist}' not found")

        target_album = db.execute(
            "SELECT id FROM albums WHERE name = ? AND artist_id = ?",
            (new_name, old_album["artist_id"]),
        ).fetchone()

        if target_album:
            track_affected = _merge_album_rows(db, old_album["id"], target_album["id"], new_name)
        else:
            db.execute("UPDATE albums SET name = ? WHERE id = ?", (new_name, old_album["id"]))
            cur = db.execute(
                "UPDATE tracks SET album = ? WHERE album_id = ? AND album != ?",
                (new_name, old_album["id"], new_name),
            )
            track_affected = cur.rowcount

        db.execute(
            "INSERT INTO migration_log (entity_type, old_name, new_name, affected_count) VALUES (?, ?, ?, ?)",
            ("album", old_name, new_name, track_affected),
        )
        _sync_enrichment_cache(db, "album", old_name)
        db.commit()

        return {"status": "ok", "albums_updated": 1, "tracks_updated": track_affected}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.post("/corrections/apply-all")
async def apply_all_corrections(request: Request, _=Depends(require_admin)):
    """Re-apply all existing corrections to the main tracks table.
    Useful for backfilling after propagation logic was added."""
    main_db = _db(request)
    try:
        rows = main_db.execute(
            "SELECT * FROM corrections WHERE type = 'TRACK_EDIT' ORDER BY id"
        ).fetchall()
        applied = 0
        for row in rows:
            try:
                corrected = json.loads(row["corrected_data"])
                original = json.loads(row["original_data"]) if row["original_data"] else {}
            except (json.JSONDecodeError, TypeError):
                continue

            new_title = corrected.get("title")
            orig_title = original.get("title")
            orig_artist = original.get("artist")
            new_artist = corrected.get("artist")
            album = original.get("album") or corrected.get("album")
            track_id = row["track_id"]

            if track_id:
                fields = []
                params = []
                for col in ("title", "artist", "album"):
                    if col in corrected:
                        fields.append(f"{col} = ?")
                        params.append(corrected[col])
                if fields:
                    params.append(track_id)
                    main_db.execute(f"UPDATE tracks SET {', '.join(fields)} WHERE id = ?", params)

            orig_album = original.get("album")
            new_album = corrected.get("album")
            if new_album and orig_album and new_album != orig_album:
                main_db.execute(
                    "UPDATE tracks SET album = ? WHERE album = ? AND artist = ?",
                    (new_album, orig_album, orig_artist or new_artist),
                )
            if new_title and orig_title and new_title != orig_title:
                main_db.execute(
                    "UPDATE tracks SET title = ? WHERE title = ? AND album = ? AND artist = ?",
                    (new_title, orig_title, album, orig_artist or new_artist),
                )
            if new_artist and orig_artist and new_artist != orig_artist:
                main_db.execute(
                    "UPDATE tracks SET artist = ? WHERE artist = ? AND album = ?",
                    (new_artist, orig_artist, album),
                )
            applied += 1

        main_db.commit()
        return {"status": "ok", "applied": applied}
    finally:
        main_db.close()


# ── Track Browser ───────────────────────────────────────────────────

@router.get("/tracks")
async def search_tracks(
    request: Request,
    q: str = "",
    artist: str = "",
    album: str = "",
    limit: int = 100,
    _=Depends(require_admin),
):
    """Search across all tracks, grouped by (title, artist, album) combo."""
    db = _db(request)
    try:
        conditions = []
        params = []
        if q:
            conditions.append("(t.title LIKE ? OR t.artist LIKE ? OR t.album LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
        if artist:
            conditions.append("t.artist LIKE ?")
            params.append(f"%{artist}%")
        if album:
            conditions.append("t.album LIKE ?")
            params.append(f"%{album}%")

        where = " AND ".join(conditions) if conditions else "1"

        rows = db.execute(f"""
            SELECT t.title, t.artist, t.album,
                   COUNT(*) as total_plays,
                   COUNT(DISTINCT t.episode_id) as episode_count,
                   GROUP_CONCAT(DISTINCT e.broadcast || '|' || e.date) as episodes
            FROM tracks t
            JOIN episodes e ON e.id = t.episode_id
            WHERE {where}
            GROUP BY t.title, t.artist, t.album
            ORDER BY total_plays DESC
            LIMIT ?
        """, params + [limit]).fetchall()

        results = []
        for r in rows:
            ep_list = []
            if r["episodes"]:
                for ep_str in r["episodes"].split(","):
                    parts = ep_str.split("|", 1)
                    ep_list.append({
                        "broadcast": int(parts[0]) if parts[0] and parts[0] != "None" else None,
                        "date": parts[1] if len(parts) > 1 else None,
                    })
            results.append({
                "title": r["title"],
                "artist": r["artist"],
                "album": r["album"] or "",
                "total_plays": r["total_plays"],
                "episode_count": r["episode_count"],
                "episodes": ep_list,
            })

        return {"items": results, "total": len(results)}
    finally:
        db.close()


# ── Correction History ──────────────────────────────────────────────

@router.get("/corrections")
async def list_corrections(
    request: Request,
    episode: int = 0,
    type: str = "",
    _=Depends(require_admin),
):
    """List all corrections."""
    db = _db(request)
    try:
        _ensure_corrections(db)

        conditions = []
        params = []
        if episode:
            conditions.append("episode_id = ?")
            params.append(episode)
        if type:
            conditions.append("type = ?")
            params.append(type)

        where = " AND ".join(conditions) if conditions else "1"

        rows = db.execute(f"""
            SELECT id, track_id, episode_id, type, original_data, corrected_data, created_at
            FROM corrections
            WHERE {where}
            ORDER BY created_at DESC
        """, params).fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "track_id": r["track_id"],
                "episode_id": r["episode_id"],
                "type": r["type"],
                "original_data": json.loads(r["original_data"]) if r["original_data"] else None,
                "corrected_data": json.loads(r["corrected_data"]),
                "created_at": r["created_at"],
            })

        return {"items": results, "total": len(results)}
    finally:
        db.close()


@router.post("/corrections/{correction_id}/revert")
async def revert_correction(
    request: Request,
    correction_id: int,
    _=Depends(require_admin),
):
    """Delete a correction."""
    db = _db(request)
    try:
        _ensure_corrections(db)
        cur = db.execute("DELETE FROM corrections WHERE id = ?", (correction_id,))
        db.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Correction not found")
        return {"status": "ok", "deleted": correction_id}
    finally:
        db.close()


# ── Ignored Clusters ────────────────────────────────────────────────

@router.post("/clusters/ignore")
async def ignore_cluster(request: Request, _=Depends(require_admin)):
    """Mark a cluster as "not duplicates" so it stops appearing in the merge tab."""
    body = await request.json()
    entity_type = body.get("type", "artist")
    entity_ids_raw = body.get("entity_ids", "")
    display_name = body.get("display_name", "")

    ids = sorted(_parse_ids(entity_ids_raw))
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 entity_ids required")

    db = _db(request)
    try:
        _ensure_ignored_clusters(db)
        db.execute("""
            INSERT INTO ignored_clusters (entity_type, entity_ids, display_name)
            VALUES (?, ?, ?)
        """, (entity_type, ",".join(str(i) for i in ids), display_name))
        db.commit()
        return {"status": "ignored", "entity_ids": ids, "display_name": display_name}
    finally:
        db.close()


@router.get("/clusters/ignored")
async def list_ignored_clusters(request: Request, type: str = "artist", _=Depends(require_admin)):
    """List clusters that have been marked as ignored."""
    db = _db(request)
    try:
        _ensure_ignored_clusters(db)
        rows = db.execute("""
            SELECT id, entity_type, entity_ids, display_name, created_at
            FROM ignored_clusters
            WHERE entity_type = ?
            ORDER BY created_at DESC
        """, (type,)).fetchall()
        return {
            "items": [
                {
                    "id": r["id"],
                    "entity_type": r["entity_type"],
                    "entity_ids": [int(x) for x in r["entity_ids"].split(",") if x.strip()],
                    "display_name": r["display_name"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        }
    finally:
        db.close()


@router.post("/edit-artist")
async def edit_artist(request: Request, _=Depends(require_admin)):
    """Edit artist name and/or set MBID. Auto-resolves canonical name and
    pulls all enrichment data (genres, country, bio, etc.) from MusicBrainz
    when an MBID is provided.

    Body:
        name: str (required — current artist name)
        mbid: str | None (MusicBrainz artist ID)
        new_name: str | None (rename, omit to use auto-resolved or keep)
    """
    body = await request.json()
    name = body.get("name", "")
    mbid = body.get("mbid")
    new_name = body.get("new_name")

    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    # Auto-resolve canonical name + all enrichment data (MB + Last.fm)
    fetched = get_artist_enrichment(name, mbid=mbid)
    if not new_name and fetched:
        new_name = fetched.get("canonical_name")

    resolved_name = new_name or name

    main_db = _db(request)
    try:
        old_row = main_db.execute(
            "SELECT id FROM artists WHERE name = ?", (name,)
        ).fetchone()

        if old_row:
            old_id = old_row["id"]
            target = main_db.execute(
                "SELECT id FROM artists WHERE name = ?", (resolved_name,)
            ).fetchone()

            if target and target["id"] != old_id:
                # Merge into existing canonical artist
                target_id = target["id"]
                # Move tracks first
                main_db.execute("UPDATE tracks SET artist_id = ?, artist = ? WHERE artist_id = ?",
                    (target_id, resolved_name, old_id))
                # Move albums, handling name collisions
                old_albums = main_db.execute(
                    "SELECT id, name FROM albums WHERE artist_id = ?", (old_id,)
                ).fetchall()
                for alb in old_albums:
                    collision = main_db.execute(
                        "SELECT id FROM albums WHERE artist_id = ? AND name = ?",
                        (target_id, alb["name"]),
                    ).fetchone()
                    if collision:
                        main_db.execute("UPDATE tracks SET album_id = ? WHERE album_id = ?",
                            (collision["id"], alb["id"]))
                        main_db.execute("DELETE FROM albums WHERE id = ?", (alb["id"],))
                    else:
                        main_db.execute("UPDATE albums SET artist_id = ? WHERE id = ?",
                            (target_id, alb["id"]))
                main_db.execute("DELETE FROM artists WHERE id = ?", (old_id,))
                _sync_enrichment_cache(main_db, "artist", name)
            else:
                if resolved_name != name:
                    main_db.execute("UPDATE artists SET name = ? WHERE id = ?",
                        (resolved_name, old_id))
                if resolved_name != name:
                    main_db.execute("UPDATE tracks SET artist = ? WHERE artist = ?",
                        (resolved_name, name))
                    _sync_enrichment_cache(main_db, "artist", name)

        # Write the MBID to artists.mbid for merge detection
        if mbid:
            artist_row = main_db.execute(
                "SELECT id FROM artists WHERE name = ?", (resolved_name,)
            ).fetchone()
            if artist_row:
                main_db.execute(
                    "UPDATE artists SET mbid = ? WHERE id = ?", (mbid, artist_row["id"])
                )

        # Write/update enrichment data in main DB's artist_enrichment
        if fetched:
            genres = json.dumps(fetched.get("genres", []))
            tags = json.dumps(fetched.get("tags", []))
            main_db.execute("""
                INSERT INTO artist_enrichment
                    (artist_name, mbid, canonical_name, country, formed_year,
                     genres, tags, bio_summary, wikipedia_url, last_fetched, fetch_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), 1)
                ON CONFLICT(artist_name) DO UPDATE SET
                    mbid = COALESCE(excluded.mbid, mbid),
                    canonical_name = COALESCE(excluded.canonical_name, canonical_name),
                    country = COALESCE(excluded.country, country),
                    formed_year = COALESCE(excluded.formed_year, formed_year),
                    genres = COALESCE(excluded.genres, genres),
                    tags = COALESCE(excluded.tags, tags),
                    bio_summary = COALESCE(excluded.bio_summary, bio_summary),
                    wikipedia_url = COALESCE(excluded.wikipedia_url, wikipedia_url),
                    last_fetched = datetime('now'),
                    fetch_count = fetch_count + 1
            """, (
                resolved_name,
                fetched.get("mbid"),
                fetched.get("canonical_name"),
                fetched.get("country"),
                fetched.get("formed_year"),
                genres,
                tags,
                fetched.get("bio_summary"),
                fetched.get("wikipedia_url"),
            ))

        main_db.commit()
    finally:
        main_db.close()

    return {
        "status": "ok",
        "name": resolved_name,
        "mbid": mbid,
        "canonical_name": fetched.get("canonical_name") if fetched else None,
        "country": fetched.get("country") if fetched else None,
        "formed_year": fetched.get("formed_year") if fetched else None,
        "bio_summary": fetched.get("bio_summary") if fetched else None,
    }


@router.delete("/clusters/ignore/{ignore_id}")
async def unignore_cluster(request: Request, ignore_id: int, _=Depends(require_admin)):
    """Restore an ignored cluster so it appears in the merge tab again."""
    db = _db(request)
    try:
        cur = db.execute("DELETE FROM ignored_clusters WHERE id = ?", (ignore_id,))
        db.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Ignored cluster not found")
        return {"status": "ok", "deleted": ignore_id}
    finally:
        db.close()
