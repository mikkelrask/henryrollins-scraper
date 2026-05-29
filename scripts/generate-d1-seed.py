#!/usr/bin/env python3
"""
Generate a clean D1-compatible SQL seed from the unified local SQLite database.

This avoids fragile post-processing of .dump output by writing clean SQL directly.

Usage:
  python3 scripts/generate-d1-seed.py              # writes to seed.sql
  python3 scripts/generate-d1-seed.py seed-out.sql  # writes to named file
"""

import sqlite3
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "henryrollins.db"


def quote(val):
    """SQL-escape a value. Handles nulls, numbers, and strings."""
    if val is None:
        return "NULL"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        return str(val)
    s = str(val)
    # Escape single quotes for SQL
    s = s.replace("'", "''")
    # Replace newlines with space — these are Last.fm bios and display text;
    # losing the newline vs keeping unistr() is the right tradeoff for D1 compat
    s = s.replace('\n', ' ').replace('\r', '')
    return f"'{s}'"


def generate_schema(db):
    """Generate CREATE TABLE statements from database schema."""
    tables = db.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    
    schemas = []
    for name, sql in tables:
        if not sql:
            continue
        # Add IF NOT EXISTS
        sql = sql.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ")
        schemas.append(sql.rstrip() + ";")
    
    return schemas


def generate_indexes(db):
    """Generate CREATE INDEX statements."""
    indexes = db.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%_autoindex_%'"
    ).fetchall()
    
    stmts = []
    for name, sql in indexes:
        sql = sql.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ")
        stmts.append(sql.rstrip() + ";")
    
    return stmts


def generate_inserts(db, table):
    """Generate INSERT OR IGNORE statements for a table."""
    columns = [col[1] for col in db.execute(f"PRAGMA table_info({table})").fetchall()]
    col_names = ', '.join(f'"{c}"' for c in columns)
    
    rows = db.execute(f"SELECT * FROM \"{table}\"").fetchall()
    
    stmts = []
    for row in rows:
        values = ', '.join(quote(v) for v in row)
        stmts.append(f"INSERT OR IGNORE INTO \"{table}\" VALUES({values});")
    
    return stmts


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else str(PROJECT_ROOT / "seed.sql")
    
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        sys.exit(1)
    
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    
    print(f"📦 Generating seed from {DB_PATH} → {out_path}")
    
    lines = []
    
    # Schema
    tables_to_export = [
        "episodes", "artists", "albums", "tracks", "links",
        "artist_enrichment", "album_art", "corrections", "release_group_cache",
        "migration_log", "ignored_clusters",
    ]
    
    existing_tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    
    for table in tables_to_export:
        if table not in existing_tables:
            print(f"  ⏭️  {table}: table not found, skipping")
            continue
        
        # Get schema
        row = db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if row and row[0]:
            sql = row[0].replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ")
            if not sql.endswith(";"):
                sql += ";"
            lines.append(sql)
            print(f"  📋 {table}: schema created")
        
        # Get data
        count = db.execute(f"SELECT COUNT(*) FROM \"{table}\"").fetchone()[0]
        if count > 0:
            inserts = generate_inserts(db, table)
            lines.extend(inserts)
            print(f"  💾 {table}: {count} rows")
        else:
            print(f"  📭 {table}: empty")
    
    # Indexes
    idx_lines = generate_indexes(db)
    if idx_lines:
        lines.extend(idx_lines)
        print(f"  🔍 {len(idx_lines)} indexes")
    
    # Write output
    with open(out_path, 'w') as f:
        f.write('\n'.join(lines))
    
    line_count = len(lines)
    size = os.path.getsize(out_path)
    print(f"\n✅ Wrote {line_count} lines, {size/1024:.1f} KB to {out_path}")


if __name__ == "__main__":
    main()
