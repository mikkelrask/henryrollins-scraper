import json
import re
import sqlite3
from fastapi import APIRouter, Request, HTTPException, Depends
from ..services.enrichment import _fetch_artist_from_musicbrainz

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
                    (SELECT COUNT(*) FROM tracks WHERE artist_id = a.id) AS track_count,
                    (SELECT COUNT(*) FROM albums WHERE artist_id = a.id) AS album_count
                FROM artists a
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
                        }
                        if type == "album":
                            variant_data["artist_name"] = v.get("artist_name", "")
                        cluster_variants.append(variant_data)
                        seen_ids.add(v["id"])

            if len(cluster_variants) >= min_size:
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
        db.execute("""
            CREATE TABLE IF NOT EXISTS ignored_clusters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_ids TEXT NOT NULL,
                display_name TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
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


def _merge_impl(
    request: Request,
    entity_type: str,
    source_ids: list[int],
    target_id: int,
    preview: bool = False,
):
    db = _db(request)
    try:
        # Ensure migration_log table exists
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
                # Count what would be affected
                track_count = db.execute(
                    "SELECT COUNT(*) FROM tracks WHERE artist_id = ?", (source_id,)
                ).fetchone()[0]
                album_count = db.execute(
                    "SELECT COUNT(*) FROM albums WHERE artist_id = ?", (source_id,)
                ).fetchone()[0]

                if preview:
                    affected_tracks = track_count
                    affected_albums = album_count
                else:
                    # Merge albums that collide by name
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

                    # Reassign remaining albums & tracks
                    db.execute("UPDATE albums SET artist_id = ? WHERE artist_id = ?",
                               (target_id, source_id))
                    db.execute("UPDATE tracks SET artist_id = ? WHERE artist_id = ?",
                               (target_id, source_id))
                    # Also update the text column so searches by name still work
                    db.execute("UPDATE tracks SET artist = ? WHERE artist_id = ? AND artist != ?",
                               (target_name, target_id, target_name))
                    db.execute("DELETE FROM artists WHERE id = ?", (source_id,))

                    db.execute(
                        "INSERT INTO migration_log (entity_type, old_name, new_name, affected_count) VALUES (?, ?, ?, ?)",
                        ("artist", source_name, target_name, track_count),
                    )

                    affected_tracks = track_count
                    affected_albums = album_count

            else:  # album
                track_count = db.execute(
                    "SELECT COUNT(*) FROM tracks WHERE album_id = ?", (source_id,)
                ).fetchone()[0]

                if preview:
                    affected_tracks = track_count
                    affected_albums = 1
                else:
                    db.execute("UPDATE tracks SET album_id = ? WHERE album_id = ?",
                               (target_id, source_id))
                    # Also update the text column
                    db.execute("UPDATE tracks SET album = ? WHERE album_id = ? AND album != ?",
                               (target_name, target_id, target_name))
                    db.execute("DELETE FROM albums WHERE id = ?", (source_id,))

                    db.execute(
                        "INSERT INTO migration_log (entity_type, old_name, new_name, affected_count) VALUES (?, ?, ?, ?)",
                        ("album", source_name, target_name, track_count),
                    )

                    affected_tracks = track_count
                    affected_albums = 1

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
async def list_entities(request: Request, type: str = "artist", q: str = "", _=Depends(require_admin)):
    db = _db(request)
    try:
        if type == "artist":
            query = "SELECT id, name, (SELECT COUNT(*) FROM tracks WHERE artist_id = artists.id) as track_count FROM artists WHERE name LIKE ? ORDER BY track_count DESC LIMIT 50"
        else:
            query = """SELECT a.id, a.name,
                             (SELECT ar.name FROM artists ar WHERE ar.id = a.artist_id) as artist_name,
                             (SELECT COUNT(*) FROM tracks WHERE album_id = a.id) as track_count
                      FROM albums a
                      WHERE a.name LIKE ?
                      ORDER BY track_count DESC LIMIT 50"""

        rows = db.execute(query, (f"%{q}%",)).fetchall()
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

    if not episode_id or not corrected:
        raise HTTPException(status_code=400, detail="episode_id and corrected_data are required")

    enrich_db = sqlite3.connect(request.app.state.enrichment_path)
    enrich_db.row_factory = sqlite3.Row
    try:
        enrich_db.execute("""
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
        enrich_db.execute("""
            INSERT INTO corrections (track_id, episode_id, type, original_data, corrected_data)
            VALUES (?, ?, ?, ?, ?)
        """, (
            track_id,
            episode_id,
            correction_type,
            json.dumps(original) if original else None,
            json.dumps(corrected),
        ))
        enrich_db.commit()
    finally:
        enrich_db.close()

    # Also update the actual track(s) in the main database
    if correction_type == "TRACK_EDIT":
        main_db = sqlite3.connect(request.app.state.db_path)
        try:
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
            if track_mbid and track_id:
                try:
                    main_db.execute("ALTER TABLE tracks ADD COLUMN mbid TEXT")
                except sqlite3.OperationalError:
                    pass
                main_db.execute("UPDATE tracks SET mbid = ? WHERE id = ?", (track_mbid, track_id))

            # ── Album MBID + enrichment DB ──
            release_group_mbid = corrected.get("album_release_group_mbid")
            if album_mbid or release_group_mbid:
                album_name = corrected.get("album") or (original.get("album") if original else None)
                artist_name = corrected.get("artist") or (original.get("artist") if original else None)
                if album_name and artist_name:
                    main_db.execute("""
                        UPDATE albums SET mbid = COALESCE(?, mbid)
                        WHERE name = ? AND artist_id = (SELECT id FROM artists WHERE name = ?)
                    """, (album_mbid, album_name, artist_name))
                    # Also keep main DB's album_art in sync (seeder reads from here)
                    main_db.execute("""
                        INSERT INTO album_art (album_name, artist_name, mbid, release_group_mbid, last_fetched)
                        VALUES (?, ?, ?, ?, datetime('now'))
                        ON CONFLICT(album_name, artist_name) DO UPDATE SET
                            mbid = COALESCE(excluded.mbid, mbid),
                            release_group_mbid = COALESCE(excluded.release_group_mbid, release_group_mbid),
                            last_fetched = datetime('now')
                    """, (album_name, artist_name, album_mbid, release_group_mbid))
                    enrich2 = sqlite3.connect(request.app.state.enrichment_path)
                    try:
                        enrich2.execute("""
                            UPDATE album_art SET
                                mbid = COALESCE(?, mbid),
                                release_group_mbid = COALESCE(?, release_group_mbid)
                            WHERE album_name = ? AND artist_name = ?
                        """, (album_mbid, release_group_mbid, album_name, artist_name))
                        enrich2.commit()
                    finally:
                        enrich2.close()

            main_db.commit()
        finally:
            main_db.close()

    return {"status": "saved"}


# ── Album level editing ────────────────────────────────────────────

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

    main_db = sqlite3.connect(request.app.state.db_path)
    main_db.row_factory = sqlite3.Row
    try:
        # Propagate name change to tracks table
        if new_name != old_name:
            main_db.execute(
                "UPDATE tracks SET album = ? WHERE album = ? AND artist = ?",
                (new_name, old_name, artist),
            )

        # Update albums table
        album = main_db.execute(
            """SELECT a.id FROM albums a
               WHERE a.name = ? AND a.artist_id = (SELECT id FROM artists WHERE name = ?)""",
            (old_name, artist),
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
            # Keep main DB's album_art in sync for the dedup seeder
            main_db.execute("""
                INSERT INTO album_art (album_name, artist_name, mbid, release_group_mbid, last_fetched)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(album_name, artist_name) DO UPDATE SET
                    mbid = COALESCE(excluded.mbid, mbid),
                    release_group_mbid = COALESCE(excluded.release_group_mbid, release_group_mbid),
                    last_fetched = datetime('now')
            """, (new_name, artist, mbid, release_group_mbid))

        elif mbid and new_name:
            # Album row may not exist yet — create it or update by name
            artist_row = main_db.execute(
                "SELECT id FROM artists WHERE name = ?", (artist,)
            ).fetchone()
            if artist_row:
                main_db.execute(
                    "INSERT OR REPLACE INTO albums (artist_id, name, mbid) VALUES (?, ?, ?)",
                    (artist_row["id"], new_name, mbid),
                )

        main_db.commit()
    finally:
        main_db.close()

    # Update enrichment DB (by new_name since tracks were already updated)
    enrich_db = sqlite3.connect(request.app.state.enrichment_path)
    try:
        enrich_db.execute("""
            UPDATE album_art SET
                mbid = COALESCE(?, mbid),
                release_group_mbid = COALESCE(?, release_group_mbid)
            WHERE album_name = ? AND artist_name = ?
        """, (mbid, release_group_mbid, new_name, artist))
        # If no row existed, insert one so next page load picks it up
        if enrich_db.execute("SELECT changes()").fetchone()[0] == 0 and mbid:
            enrich_db.execute("""
                INSERT OR IGNORE INTO album_art (album_name, artist_name, mbid, release_group_mbid, last_fetched)
                VALUES (?, ?, ?, ?, datetime('now'))
            """, (new_name, artist, mbid, release_group_mbid))
        enrich_db.commit()
    finally:
        enrich_db.close()

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
    If target artist already exists, merges tracks/albums into it and deletes the old one."""
    body = await request.json()
    old_name = body.get("old_name", "")
    new_name = body.get("new_name", "")

    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="old_name and new_name are required")

    main_db = sqlite3.connect(request.app.state.db_path)
    main_db.row_factory = sqlite3.Row
    try:
        # Find old artist
        old_artist = main_db.execute(
            "SELECT id FROM artists WHERE name = ?",
            (old_name,),
        ).fetchone()

        if not old_artist:
            raise HTTPException(status_code=404, detail=f"Artist '{old_name}' not found")

        # Check if target artist already exists
        target_artist = main_db.execute(
            "SELECT id FROM artists WHERE name = ?",
            (new_name,),
        ).fetchone()

        if target_artist:
            # Merge: move albums and tracks from old artist to target, then delete old
            main_db.execute(
                "UPDATE albums SET artist_id = ? WHERE artist_id = ?",
                (target_artist["id"], old_artist["id"]),
            )
            main_db.execute(
                "UPDATE tracks SET artist_id = ? WHERE artist_id = ?",
                (target_artist["id"], old_artist["id"]),
            )
            main_db.execute("DELETE FROM artists WHERE id = ?", (old_artist["id"],))
            artist_affected = 1  # deleted one artist
        else:
            # Simple rename
            main_db.execute("UPDATE artists SET name = ? WHERE id = ?", (new_name, old_artist["id"]))
            artist_affected = 1

        # Update tracks table (text column) regardless
        cur = main_db.execute("UPDATE tracks SET artist = ? WHERE artist = ?", (new_name, old_name))
        track_affected = cur.rowcount

        main_db.commit()
        return {"status": "ok", "artists_updated": artist_affected, "tracks_updated": track_affected}
    finally:
        main_db.close()


@router.post("/rename-album")
async def rename_album(request: Request, _=Depends(require_admin)):
    """Rename an album everywhere: albums table + tracks table.
    If target album already exists, merges tracks into it and deletes the old one."""
    body = await request.json()
    old_name = body.get("old_name", "")
    new_name = body.get("new_name", "")
    artist = body.get("artist", "")

    if not old_name or not new_name or not artist:
        raise HTTPException(status_code=400, detail="old_name, new_name, and artist are required")

    main_db = sqlite3.connect(request.app.state.db_path)
    main_db.row_factory = sqlite3.Row
    try:
        # Find old album
        old_album = main_db.execute(
            "SELECT a.id, a.artist_id FROM albums a WHERE a.name = ? AND a.artist_id = (SELECT id FROM artists WHERE name = ?)",
            (old_name, artist),
        ).fetchone()

        if not old_album:
            raise HTTPException(status_code=404, detail=f"Album '{old_name}' by '{artist}' not found")

        # Check if target album already exists
        target_album = main_db.execute(
            "SELECT id FROM albums WHERE name = ? AND artist_id = ?",
            (new_name, old_album["artist_id"]),
        ).fetchone()

        if target_album:
            # Merge: move tracks from old album to target, then delete old album
            main_db.execute(
                "UPDATE tracks SET album_id = ? WHERE album_id = ?",
                (target_album["id"], old_album["id"]),
            )
            main_db.execute("DELETE FROM albums WHERE id = ?", (old_album["id"],))
            album_affected = 1  # deleted one album
        else:
            # Simple rename
            main_db.execute(
                "UPDATE albums SET name = ? WHERE id = ?",
                (new_name, old_album["id"]),
            )
            album_affected = 1

        # Update tracks table (text column) regardless
        cur = main_db.execute(
            "UPDATE tracks SET album = ? WHERE album = ? AND artist = ?",
            (new_name, old_name, artist),
        )
        track_affected = cur.rowcount

        main_db.commit()
        return {"status": "ok", "albums_updated": album_affected, "tracks_updated": track_affected}
    finally:
        main_db.close()


@router.post("/corrections/apply-all")
async def apply_all_corrections(request: Request, _=Depends(require_admin)):
    """Re-apply all existing corrections to the main tracks table.
    Useful for backfilling after propagation logic was added."""
    enrich_db = sqlite3.connect(request.app.state.enrichment_path)
    enrich_db.row_factory = sqlite3.Row
    main_db = sqlite3.connect(request.app.state.db_path)
    try:
        rows = enrich_db.execute(
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
        enrich_db.close()
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
    """List all corrections from the enrichment database."""
    enrich_db = sqlite3.connect(request.app.state.enrichment_path)
    enrich_db.row_factory = sqlite3.Row
    try:
        # Ensure corrections table exists (enrichment.db may be fresh)
        enrich_db.execute("""
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

        conditions = []
        params = []
        if episode:
            conditions.append("episode_id = ?")
            params.append(episode)
        if type:
            conditions.append("type = ?")
            params.append(type)

        where = " AND ".join(conditions) if conditions else "1"

        rows = enrich_db.execute(f"""
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
        enrich_db.close()


@router.post("/corrections/{correction_id}/revert")
async def revert_correction(
    request: Request,
    correction_id: int,
    _=Depends(require_admin),
):
    """Delete a correction from the enrichment database."""
    enrich_db = sqlite3.connect(request.app.state.enrichment_path)
    try:
        enrich_db.execute("""
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
        cur = enrich_db.execute("DELETE FROM corrections WHERE id = ?", (correction_id,))
        enrich_db.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Correction not found")
        return {"status": "ok", "deleted": correction_id}
    finally:
        enrich_db.close()


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
        db.execute("""
            CREATE TABLE IF NOT EXISTS ignored_clusters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_ids TEXT NOT NULL,
                display_name TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
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
        db.execute("""
            CREATE TABLE IF NOT EXISTS ignored_clusters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_ids TEXT NOT NULL,
                display_name TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
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

    # Auto-resolve canonical name + all enrichment data from MusicBrainz
    fetched = None
    if mbid:
        fetched = _fetch_artist_from_musicbrainz(name, mbid)
        if not fetched:
            raise HTTPException(status_code=502, detail="Failed to fetch artist from MusicBrainz")
        if not new_name:
            new_name = fetched.get("canonical_name")

    resolved_name = new_name or name

    main_db = sqlite3.connect(request.app.state.db_path)
    main_db.row_factory = sqlite3.Row
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
                main_db.execute("UPDATE tracks SET artist_id = ?, artist = ? WHERE artist_id = ?",
                    (target_id, resolved_name, old_id))
                main_db.execute("UPDATE albums SET artist_id = ? WHERE artist_id = ?",
                    (target_id, old_id))
                main_db.execute("DELETE FROM artists WHERE id = ?", (old_id,))
            else:
                if resolved_name != name:
                    main_db.execute("UPDATE artists SET name = ? WHERE id = ?",
                        (resolved_name, old_id))
                if resolved_name != name:
                    main_db.execute("UPDATE tracks SET artist = ? WHERE artist = ?",
                        (resolved_name, name))

            # Update albums.mbid for all albums by this artist
            if mbid:
                main_db.execute(
                    "UPDATE albums SET mbid = ? WHERE artist_id = ? AND mbid IS NULL",
                    (mbid, target["id"] if target else old_id),
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

        # Keep enrichment DB in sync
        enrich_db = sqlite3.connect(request.app.state.enrichment_path)
        try:
            if fetched:
                enrich_db.execute("""
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
                        fetch_count = 1
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
            enrich_db.commit()
        finally:
            enrich_db.close()

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
