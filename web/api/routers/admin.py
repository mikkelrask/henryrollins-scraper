import re
import sqlite3
from fastapi import APIRouter, Request, HTTPException

router = APIRouter(tags=["admin"])


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


# ── Cluster Detection ───────────────────────────────────────────────

@router.get("/clusters")
async def get_clusters(
    request: Request,
    type: str = "artist",
    min_size: int = 2,
    min_tracks: int = 1,
    show_lonely: bool = False,
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
async def list_entities(request: Request, type: str = "artist", q: str = ""):
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
async def reassign(request: Request, type: str, source_id: int, target_id: int):
    """Legacy single-source reassign — delegates to bulk merge."""
    return _merge_impl(request, type, [source_id], target_id, preview=False)
