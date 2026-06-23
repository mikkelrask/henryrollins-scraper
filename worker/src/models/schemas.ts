/**
 * TypeScript types mirroring the Pydantic schemas from web/api/models/schemas.py.
 * These are used for response serialization and internal type safety.
 */

// ── Episode ──

export interface EpisodeSummary {
  broadcast: number
  date: string
  title: string
  track_count: number
  unique_artists: number
  repeat_rate: number | null
}

export interface EpisodeDetail {
  broadcast: number
  date: string
  title: string
  url: string
  tracks: TrackInfo[]
  bandcamp_links: BandcampLink[]
  stats: EpisodeStats | null
}

export interface TrackInfo {
  hour: number
  position: number
  artist: string
  title: string
  album: string | null
}

export interface BandcampLink {
  url: string
  label: string
}

export interface EpisodeStats {
  track_count: number
  unique_artists: number
  repeat_rate: number
}

// ── Artist ──

export interface ArtistSummary {
  artist: string
  plays: number
  episodes: number
  rli: number
  coverage: number | null
  recency_index: number | null
  trend: string | null
  streak: number | null
  album_diversity: number | null
  first_episode: string | null
  last_episode: string | null
  badge: string | null
}

export interface ArtistDetail {
  id: number | null
  artist: string
  plays: number
  episodes: number
  rli: number
  coverage: number | null
  first_appearance: string | null
  last_appearance: string | null
  streak: number | null
  album_count: number | null
  album_diversity: number | null
  top_tracks: TrackCount[]
  album_breakdown: AlbumBreakdown[]
  timeline: TimelinePoint[]
  enrichment: ArtistEnrichment | null
  badge: string | null
}

export interface TrackPlay {
  broadcast: number | null
  date: string | null
}

export interface TrackCount {
  title: string
  plays: number
  last_played: string | null
  last_broadcast: number | null
  broadcasts: TrackPlay[]
  episodes: number | null
  artist: string | null
  album: string | null
}

export interface AlbumBreakdown {
  album: string
  artist: string | null
  plays: number
  distinct_tracks: number
  artwork_url: string | null
  artwork_url_large: string | null
  release_date: string | null
}

export interface TimelinePoint {
  broadcast: number | null
  date: string
  plays: number
}

export interface ArtistEnrichment {
  mbid: string | null
  canonical_name: string | null
  country: string | null
  formed_year: number | null
  genres: string[] | null
  tags: string[] | null
  bio_summary: string | null
  lastfm_tags: string[] | null
  lastfm_bio: string | null
  lastfm_listeners: number | null
  lastfm_playcount: number | null
  lastfm_url: string | null
}

// ── Album ──

export interface AlbumSummary {
  album: string
  artist: string
  plays: number
  distinct_tracks: number
  episodes: number
  last_played: string | null
  artwork_url: string | null
}

export interface ReleaseInfo {
  mbid: string | null
  title: string | null
  status: string | null
  date: string | null
  country: string | null
  format: string | null
  label: string | null
  track_count: number | null
}

export interface AlbumDetail {
  id: number | null
  artist_id: number | null
  album: string
  artist: string
  plays: number
  distinct_tracks: number
  total_tracks: number | null
  episodes: number
  tracks: TrackCount[]
  timeline: TimelinePoint[]
  heatmap: Array<{ year: string; month: string; plays: number }>
  artwork_url: string | null
  artwork_url_large: string | null
  mbid: string | null
  release_group_mbid: string | null
  release_date: string | null
  unplayed_tracks: string[]
  releases: ReleaseInfo[]
}

// ── Recommend / Bandcamp ──

export interface RecommendItem {
  url: string
  bandcamp_artist: string
  album_title: string
  episode_count: number
  first_seen: string | null
  last_seen: string | null
  episodes: number[]
}

export interface RecommendArtist {
  bandcamp_artist: string
  unique_albums: number
  total_episodes: number
  last_seen: string | null
}

// ── Stats ──

export interface OverviewStats {
  episodes: number
  tracks: number
  unique_artists: number
  bandcamp_links: number
  date_range: [string, string] | null
}

export interface TopItem {
  name: string
  value: number
  extra: Record<string, unknown>
}

// ── Admin ──

export interface Cluster {
  base_name: string
  total_tracks: number
  variant_count: number
  variants: Array<{ id: number; name: string; tracks: number; albums: number }>
}

export interface MergePreview {
  preview: boolean
  target_id: number
  target_name: string
  total_affected_tracks: number
  total_affected_albums: number
  details: Array<{
    source_id: number
    source_name: string
    affected_tracks: number
    affected_albums: number
  }>
}
