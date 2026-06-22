#!/usr/bin/env python3
"""Backfill missing broadcast numbers from episode URLs."""

import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "db" / "henryrollins.db"

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

rows = conn.execute(
    "SELECT id, url, date FROM episodes WHERE broadcast IS NULL OR broadcast = 0"
).fetchall()

fixed = 0
for row in rows:
    if not row["url"]:
        continue
    # Extract from URL: /radio-broadcast-458-01-0718
    m = re.search(r"/radio-broadcast-(\d+)-", row["url"])
    if m:
        num = int(m.group(1))
        conn.execute("UPDATE episodes SET broadcast = ? WHERE id = ?", (num, row["id"]))
        fixed += 1
        print(f"  ID {row['id']}: {row['date']} → broadcast #{num}")
    else:
        # Assign synthetic broadcast ID (10000 + db id) for specials
        synth = 10000 + row["id"]
        conn.execute("UPDATE episodes SET broadcast = ? WHERE id = ?", (synth, row["id"]))
        fixed += 1
        print(f"  ID {row['id']}: {row['date']} → synthetic broadcast #{synth} ({row['url']})")

conn.commit()
print(f"\nFixed {fixed} episodes")
conn.close()
