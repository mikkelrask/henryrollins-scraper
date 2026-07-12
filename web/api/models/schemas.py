"""Pydantic schemas for API responses."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# ── Episode ──

class EpisodeSummary(BaseModel):
    broadcast: int
    date: str
    title: str
    track_count: int
    unique_artists: int
    repeat_rate: float | None = None


class EpisodeDetail(BaseModel):
    broadcast: int
    date: str
    title: str
    url: str
    tracks: list["TrackInfo"]
    bandcamp_links: list["BandcampLink"]
    stats: Optional["EpisodeStats"] = None
    debutants: list["DebutArtist"] = []


class TrackInfo(BaseModel):
    hour: int
    position: int
    artist: str
    title: str
    album: str | None = None
    artist_first: bool = False
    track_first: bool = False


class BandcampLink(BaseModel):
    url: str
    label: str = ""


class EpisodeStats(BaseModel):
    track_count: int
    unique_artists: int
    repeat_rate: float
    debuting_artists: int = 0


class DebutArtist(BaseModel):
    artist: str
    title: str
    album: str | None = None


# ── Artist ──

class ArtistSummary(BaseModel):
    artist: str
    plays: int
    episodes: int
    rli: float  # Bayesian Rollins Love Index (shrinkage toward mean)
    coverage: float | None = None  # % of all episodes this artist appears in
    recency_index: float | None = None
    trend: str | None = None  # "heating_up" | "cooling_down" | "steady"
    streak: int | None = None
    album_diversity: float | None = None
    first_episode: str | None = None
    last_episode: str | None = None
    badge: str | None = None


class ArtistDetail(BaseModel):
    id: int | None = None
    artist: str
    plays: int
    episodes: int
    rli: float  # Bayesian Rollins Love Index
    coverage: float | None = None  # % of all episodes this artist appears in
    first_appearance: str | None = None
    last_appearance: str | None = None
    streak: int | None = None
    album_count: int | None = None
    album_diversity: float | None = None
    top_tracks: list["TrackCount"] = []
    album_breakdown: list["AlbumBreakdown"] = []
    timeline: list["TimelinePoint"] = []
    enrichment: Optional["ArtistEnrichment"] = None
    badge: str | None = None


class TrackPlay(BaseModel):
    broadcast: int | None = None
    date: str | None = None


class TrackCount(BaseModel):
    id: int | None = None
    title: str
    mbid: str | None = None
    plays: int
    last_played: str | None = None
    last_broadcast: int | None = None
    broadcasts: list[TrackPlay] = []
    episodes: int | None = None
    artist: str | None = None
    album: str | None = None


class AlbumBreakdown(BaseModel):
    album: str
    artist: str | None = None
    plays: int
    distinct_tracks: int
    artwork_url: str | None = None
    artwork_url_large: str | None = None
    release_date: str | None = None


class TimelinePoint(BaseModel):
    broadcast: int | None = None
    date: str
    plays: int


class ArtistEnrichment(BaseModel):
    mbid: str | None = None
    canonical_name: str | None = None
    country: str | None = None
    formed_year: int | None = None
    genres: list[str] | None = None
    tags: list[str] | None = None
    bio_summary: str | None = None
    lastfm_tags: list[str] | None = None
    lastfm_bio: str | None = None
    lastfm_listeners: int | None = None
    lastfm_playcount: int | None = None
    lastfm_url: str | None = None


# ── Album ──

class AlbumSummary(BaseModel):
    album: str
    artist: str
    plays: int
    distinct_tracks: int
    episodes: int
    last_played: str | None = None
    artwork_url: str | None = None


class ReleaseInfo(BaseModel):
    mbid: str | None = None
    title: str | None = None
    status: str | None = None
    date: str | None = None
    country: str | None = None
    format: str | None = None
    label: str | None = None
    track_count: int | None = None


class AlbumDetail(BaseModel):
    id: int | None = None
    artist_id: int | None = None
    album: str
    artist: str
    plays: int
    distinct_tracks: int
    total_tracks: int | None = None
    episodes: int
    tracks: list[TrackCount] = []
    timeline: list[TimelinePoint] = []
    heatmap: list[dict] = []
    artwork_url: str | None = None
    artwork_url_large: str | None = None
    mbid: str | None = None
    release_group_mbid: str | None = None
    release_date: str | None = None
    unplayed_tracks: list[str] = []
    releases: list[ReleaseInfo] = []


# ── Recommend / Bandcamp ──

class RecommendItem(BaseModel):
    url: str
    bandcamp_artist: str
    album_title: str
    episode_count: int
    first_seen: str | None = None
    last_seen: str | None = None
    episodes: list[int] = []


class RecommendArtist(BaseModel):
    bandcamp_artist: str
    unique_albums: int
    total_episodes: int
    last_seen: str | None = None


# ── Stats ──

class OverviewStats(BaseModel):
    episodes: int
    tracks: int
    unique_artists: int
    bandcamp_links: int
    date_range: tuple[str, str] | None = None


class TopItem(BaseModel):
    name: str
    value: int
    extra: dict = {}
