#!/usr/bin/env python3
"""
Deduplicate artists and albums in the existing DB using the same
normalization + trigram logic the scraper now uses.

Run after a scrape that produced duplicates. No rescrape needed.
"""
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "db" / "henryrollins.db"


def _normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"\(.*?\)", "", text)
    text = text.replace("&", "and")
    text = text.replace("/", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _trigram_similarity(a: str, b: str) -> float:
    def norm(s: str) -> str:
        s = s.lower().strip()
        s = re.sub(r"[^\w\s]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s
    def trigrams(s: str):
        return {s[i:i+3] for i in range(len(s) - 2)}
    na, nb = norm(a), norm(b)
    if na == nb:
        return 1.0
    ta, tb = trigrams(na), trigrams(nb)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # ── Artists ──
    rows = conn.execute("SELECT id, name, mbid FROM artists ORDER BY id").fetchall()

    # Group by normalized name
    groups: dict[str, list[dict]] = {}
    for r in rows:
        key = _normalize(r["name"])
        if not key:
            continue
        groups.setdefault(key, []).append({"id": r["id"], "name": r["name"], "mbid": r["mbid"]})

    merges = 0
    for norm_name, variants in groups.items():
        if len(variants) < 2:
            continue

        # Pick canonical: prefer the one with MBID, then most tracks
        def score(v):
            track_count = conn.execute(
                "SELECT COUNT(*) FROM tracks WHERE artist_id = ?", (v["id"],)
            ).fetchone()[0]
            has_mbid = 1 if v["mbid"] else 0
            return (has_mbid, track_count)

        variants_sorted = sorted(variants, key=score, reverse=True)
        canonical = variants_sorted[0]
        sources = variants_sorted[1:]

        print(f"Merging {len(sources)} duplicate(s) of '{canonical['name']}' (norm: '{norm_name}')")
        for src in sources:
            print(f"  → {src['name']} (id={src['id']}) into {canonical['name']} (id={canonical['id']})")

            # Reassign tracks
            conn.execute("UPDATE tracks SET artist_id = ?, artist = ? WHERE artist_id = ?",
                          (canonical["id"], canonical["name"], src["id"]))
            # Reassign albums — handle name collisions by merging
            colliding = conn.execute(
                "SELECT s.id AS src_album_id, t.id AS tgt_album_id "
                "FROM albums s JOIN albums t ON s.name = t.name "
                "WHERE s.artist_id = ? AND t.artist_id = ?",
                (src["id"], canonical["id"]),
            ).fetchall()
            for c in colliding:
                conn.execute("UPDATE tracks SET album_id = ? WHERE album_id = ?",
                             (c["tgt_album_id"], c["src_album_id"]))
                conn.execute("DELETE FROM albums WHERE id = ?", (c["src_album_id"],))
            conn.execute("UPDATE albums SET artist_id = ? WHERE artist_id = ?",
                          (canonical["id"], src["id"]))
            # Delete duplicate artist
            conn.execute("DELETE FROM artists WHERE id = ?", (src["id"],))
            merges += 1

    # ── Albums (same artist, similar name) ──
    album_rows = conn.execute(
        "SELECT id, artist_id, name, mbid FROM albums ORDER BY artist_id, name"
    ).fetchall()

    album_groups: dict[tuple[int, str], list[dict]] = {}
    for r in album_rows:
        key = (r["artist_id"], _normalize(r["name"]))
        if not key[1]:
            continue
        album_groups.setdefault(key, []).append(
            {"id": r["id"], "name": r["name"], "mbid": r["mbid"]}
        )

    for (artist_id, norm_name), variants in album_groups.items():
        if len(variants) < 2:
            continue

        def alb_score(v):
            track_count = conn.execute(
                "SELECT COUNT(*) FROM tracks WHERE album_id = ?", (v["id"],)
            ).fetchone()[0]
            has_mbid = 1 if v["mbid"] else 0
            return (has_mbid, track_count)

        variants_sorted = sorted(variants, key=alb_score, reverse=True)
        canonical = variants_sorted[0]
        sources = variants_sorted[1:]

        print(f"Merging {len(sources)} duplicate album(s) of '{canonical['name']}' (artist_id={artist_id})")
        for src in sources:
            print(f"  → {src['name']} (id={src['id']}) into {canonical['name']} (id={canonical['id']})")
            conn.execute("UPDATE tracks SET album_id = ?, album = ? WHERE album_id = ?",
                          (canonical["id"], canonical["name"], src["id"]))
            conn.execute("DELETE FROM albums WHERE id = ?", (src["id"],))
            merges += 1

    conn.commit()
    conn.close()
    print(f"\nDone. {merges} duplicate(s) merged.")


if __name__ == "__main__":
    main()
