import sqlite3
from fastapi import APIRouter, Request, HTTPException

router = APIRouter(tags=["admin"])

def _db(request: Request) -> sqlite3.Connection:
    db = sqlite3.connect(request.app.state.db_path)
    db.row_factory = sqlite3.Row
    return db

@router.get("/entities")
async def list_entities(request: Request, type: str = "artist", q: str = ""):
    db = _db(request)
    try:
        if type == "artist":
            query = "SELECT id, name, (SELECT COUNT(*) FROM tracks WHERE artist_id = artists.id) as track_count FROM artists WHERE name LIKE ? ORDER BY track_count DESC LIMIT 50"
        else:
            query = "SELECT id, name, (SELECT COUNT(*) FROM tracks WHERE album_id = albums.id) as track_count FROM albums WHERE name LIKE ? ORDER BY track_count DESC LIMIT 50"
        
        rows = db.execute(query, (f"%{q}%",)).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()

@router.post("/reassign")
async def reassign(request: Request, type: str, source_id: int, target_id: int):
    db = _db(request)
    try:
        db.execute("BEGIN TRANSACTION")
        if type == "artist":
            # 1. First, merge albums that have the same name under the target artist
            # Find albums under source artist that collide with target artist's albums
            conflicts = db.execute("""
                SELECT s.id as source_album_id, t.id as target_album_id
                FROM albums s
                JOIN albums t ON s.name = t.name
                WHERE s.artist_id = ? AND t.artist_id = ?
            """, (source_id, target_id)).fetchall()

            for c in conflicts:
                # Point tracks to target album, delete source album
                db.execute("UPDATE tracks SET album_id = ? WHERE album_id = ?", (c['target_album_id'], c['source_album_id']))
                db.execute("DELETE FROM albums WHERE id = ?", (c['source_album_id'],))

            # 2. Reassign remaining albums and tracks
            db.execute("UPDATE albums SET artist_id = ? WHERE artist_id = ?", (target_id, source_id))
            db.execute("UPDATE tracks SET artist_id = ? WHERE artist_id = ?", (target_id, source_id))
            
            # Delete orphaned source artist
            db.execute("DELETE FROM artists WHERE id = ?", (source_id,))
        else:
            # Reassign tracks from source album to target
            db.execute("UPDATE tracks SET album_id = ? WHERE album_id = ?", (target_id, source_id))
            # Delete orphaned source album
            db.execute("DELETE FROM albums WHERE id = ?", (source_id,))
            
        db.commit()
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
