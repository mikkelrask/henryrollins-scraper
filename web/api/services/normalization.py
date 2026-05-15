
import sqlite3
from typing import Literal

def _db():
    return sqlite3.connect("db/henryrollins.db")

def normalize_entity(entity_type: Literal['artist', 'album'], old_name: str, new_name: str):
    """Transactionally rename an entity across all tracks and log the change."""
    db = _db()
    try:
        db.execute("BEGIN TRANSACTION")
        
        # Calculate how many tracks will be affected
        cursor = db.execute(f"SELECT COUNT(*) FROM tracks WHERE {entity_type} = ?", (old_name,))
        count = cursor.fetchone()[0]
        
        if count == 0:
            raise ValueError(f"No tracks found for {entity_type} '{old_name}'")
            
        if entity_type == 'artist':
            # Create target artist if missing
            db.execute("INSERT OR IGNORE INTO artists (name) VALUES (?)", (new_name,))
            target_artist_id = db.execute("SELECT id FROM artists WHERE name = ?", (new_name,)).fetchone()[0]
            source_artist_id = db.execute("SELECT id FROM artists WHERE name = ?", (old_name,)).fetchone()[0]
            
            # Update albums and tracks
            db.execute("UPDATE albums SET artist_id = ? WHERE artist_id = ?", (target_artist_id, source_artist_id))
            db.execute("UPDATE tracks SET artist_id = ? WHERE artist_id = ?", (target_artist_id, source_artist_id))
            
            # Auto-merge album conflicts
            duplicates = db.execute("""
                SELECT name, GROUP_CONCAT(id) as ids 
                FROM albums 
                WHERE artist_id = ? 
                GROUP BY name HAVING COUNT(*) > 1
            """, (target_artist_id,)).fetchall()
            
            for row in duplicates:
                album_name = row['name']
                album_ids = [int(i) for i in row['ids'].split(',')]
                canonical_id = album_ids[0]
                source_ids = album_ids[1:]
                
                for sid in source_ids:
                    db.execute("UPDATE tracks SET album_id = ? WHERE album_id = ?", (canonical_id, sid))
                    db.execute("DELETE FROM albums WHERE id = ?", (sid,))
                    
        else:
            # Update album names
            db.execute("UPDATE tracks SET album = ? WHERE album = ?", (new_name, old_name))
            db.execute("UPDATE albums SET name = ? WHERE name = ?", (new_name, old_name))
        
        # Log the migration
        db.execute(
            "INSERT INTO migration_log (entity_type, old_name, new_name, affected_count) VALUES (?, ?, ?, ?)",
            (entity_type, old_name, new_name, count)
        )
        
        db.commit()
        return count
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
