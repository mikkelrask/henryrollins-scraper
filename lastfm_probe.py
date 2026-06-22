#!/usr/bin/env python3
"""
Probe Last.fm API for all artists in the DB.
Shows what data is available so the user can decide if it's worth implementing.
"""
import json
import sqlite3
import time
import urllib.request
from pathlib import Path

API_KEY = "567f2d048cd656f13ba13202a253c90e"
BASE_URL = "https://ws.audioscrobbler.com/2.0/"
DB_PATH = Path(__file__).parent / "db" / "henryrollins.db"


def lastfm_get(method: str, **params) -> dict | None:
    """Make a Last.fm API call. Best-effort, returns None on failure."""
    query = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
    url = f"{BASE_URL}?method={method}&api_key={API_KEY}&format=json&{query}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def main():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row

    # Sample: a mix of well-known and obscure artists
    artists = db.execute("""
        SELECT name FROM artists
        ORDER BY (SELECT COUNT(*) FROM tracks WHERE artist_id = artists.id) DESC
        LIMIT 150
    """).fetchall()

    db.close()

    results = {
        "artist_info": {},
        "top_tracks": {},
        "top_albums": {},
        "similar": {},
        "tags": {},
    }

    print(f"Probing Last.fm for {len(artists)} artists...\n")

    for i, row in enumerate(artists):
        name = row["name"]
        print(f"[{i+1}/{len(artists)}] {name}")

        # 1. Artist info (bio, tags, listeners, playcount)
        data = lastfm_get("artist.getinfo", artist=name)
        if data and "artist" in data:
            a = data["artist"]
            results["artist_info"][name] = {
                "listeners": a.get("stats", {}).get("listeners"),
                "playcount": a.get("stats", {}).get("playcount"),
                "bio_summary": a.get("bio", {}).get("summary", "")[:200] if a.get("bio") else None,
                "bio_content": a.get("bio", {}).get("content", "")[:400] if a.get("bio") else None,
                "tags": [t["name"] for t in a.get("tags", {}).get("tag", [])] if a.get("tags") else [],
                "url": a.get("url"),
            }
            print(f"  → listeners={a.get('stats', {}).get('listeners')}, "
                  f"playcount={a.get('stats', {}).get('playcount')}, "
                  f"tags={len(results['artist_info'][name]['tags'])}")
        else:
            print(f"  → NOT FOUND")
            results["artist_info"][name] = None

        # 2. Top tracks
        data = lastfm_get("artist.getTopTracks", artist=name, limit=5)
        if data and "toptracks" in data:
            tracks = data["toptracks"].get("track", [])
            if tracks:
                results["top_tracks"][name] = [
                    {"title": t["name"], "listeners": t.get("listeners"), "playcount": t.get("playcount")}
                    for t in (tracks if isinstance(tracks, list) else [tracks])[:5]
                ]

        # 3. Top albums
        data = lastfm_get("artist.getTopAlbums", artist=name, limit=5)
        if data and "topalbums" in data:
            albums = data["topalbums"].get("album", [])
            if albums:
                results["top_albums"][name] = [
                    {"album": a["name"], "playcount": a.get("playcount")}
                    for a in (albums if isinstance(albums, list) else [albums])[:5]
                ]

        # 4. Similar artists
        data = lastfm_get("artist.getSimilar", artist=name, limit=5)
        if data and "similarartists" in data:
            similar = data["similarartists"].get("artist", [])
            if similar:
                results["similar"][name] = [
                    {"name": s["name"], "match": s.get("match")}
                    for s in (similar if isinstance(similar, list) else [similar])[:5]
                ]

        time.sleep(0.25)  # be polite

    # ── Summary ──
    print("\n" + "=" * 60)
    print("LAST.FM PROBE SUMMARY")
    print("=" * 60)

    found = [n for n, v in results["artist_info"].items() if v is not None]
    not_found = [n for n, v in results["artist_info"].items() if v is None]

    print(f"\nTotal artists queried: {len(artists)}")
    print(f"Found on Last.fm:      {len(found)}")
    print(f"Not found:             {len(not_found)}")

    if found:
        total_listeners = sum(int(v["listeners"]) for v in results["artist_info"].values() if v and v.get("listeners"))
        total_playcount = sum(int(v["playcount"]) for v in results["artist_info"].values() if v and v.get("playcount"))
        print(f"\nAggregate listeners: {total_listeners:,}")
        print(f"Aggregate playcount: {total_playcount:,}")

        artists_with_tags = sum(1 for v in results["artist_info"].values() if v and v.get("tags"))
        artists_with_bio = sum(1 for v in results["artist_info"].values() if v and v.get("bio_summary"))
        print(f"Artists with tags:   {artists_with_tags}/{len(found)}")
        print(f"Artists with bio:    {artists_with_bio}/{len(found)}")

        artists_with_tracks = len(results["top_tracks"])
        artists_with_albums = len(results["top_albums"])
        artists_with_similar = len(results["similar"])
        print(f"Artists with top tracks:  {artists_with_tracks}/{len(found)}")
        print(f"Artists with top albums:  {artists_with_albums}/{len(found)}")
        print(f"Artists with similar:     {artists_with_similar}/{len(found)}")

    # Show a few examples
    print("\n" + "=" * 60)
    print("SAMPLE OUTPUTS")
    print("=" * 60)

    examples = ["David Bowie", "Ramones", "X‐Ray Spex", "The Fall", "Devo"]
    for name in examples:
        if name in results["artist_info"] and results["artist_info"][name]:
            info = results["artist_info"][name]
            print(f"\n{name}:")
            print(f"  listeners: {info['listeners']}, playcount: {info['playcount']}")
            print(f"  tags: {info['tags'][:6]}")
            print(f"  bio: {info['bio_summary'][:120] if info['bio_summary'] else 'N/A'}...")
            if name in results["similar"]:
                sims = ", ".join(s["name"] for s in results["similar"][name][:3])
                print(f"  similar: {sims}")
        else:
            print(f"\n{name}: NOT FOUND")

    # Write full results to file for inspection
    out_path = Path("lastfm_probe_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nFull results written to: {out_path}")


if __name__ == "__main__":
    main()
