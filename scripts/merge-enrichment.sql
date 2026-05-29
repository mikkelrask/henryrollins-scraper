-- Create enrichment tables in the main database.
-- Column order matches the source enrichment.db schema exactly.
-- Run after seeding: sqlite3 db/henryrollins.db < scripts/merge-enrichment.sql

CREATE TABLE IF NOT EXISTS artist_enrichment (
    artist_name TEXT PRIMARY KEY,
    mbid TEXT,
    country TEXT,
    formed_year INTEGER,
    genres TEXT,
    tags TEXT,
    bio_summary TEXT,
    wikipedia_url TEXT,
    last_fetched TEXT,
    fetch_count INTEGER DEFAULT 1,
    canonical_name TEXT,
    lastfm_tags TEXT,
    lastfm_bio TEXT,
    lastfm_listeners TEXT,
    lastfm_playcount TEXT,
    lastfm_url TEXT
);

CREATE TABLE IF NOT EXISTS album_art (
    album_name TEXT NOT NULL,
    artist_name TEXT NOT NULL,
    mbid TEXT,
    artwork_url TEXT,
    release_year INTEGER,
    release_date TEXT,
    last_fetched TEXT,
    release_group_mbid TEXT,
    canonical_name TEXT,
    PRIMARY KEY (album_name, artist_name)
);

CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER,
    episode_id INTEGER,
    type TEXT NOT NULL,
    original_data TEXT,
    corrected_data TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS release_group_cache (
    rg_mbid TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at TEXT DEFAULT (datetime('now'))
);
