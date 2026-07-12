/**
 * MusicBrainz / Wikipedia / Last.fm lookups for the admin "edit artist"
 * flow — a TypeScript port of the relevant parts of
 * web/api/services/enrichment.py's get_artist_enrichment(), scoped to what
 * /admin/edit-artist needs (no album-art or scrape-time enrichment here).
 */

const USER_AGENT = 'HenryRollinsListensTo/1.0 (music analytics project)'
// Same key as web/api/services/enrichment.py (LASTFM_API_KEY) — already
// public in that tracked source file, so reusing it here isn't a new leak.
const LASTFM_API_KEY = '567f2d048cd656f13ba13202a253c90e'

function parseYear(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null
  const year = parseInt(dateStr.slice(0, 4), 10)
  return Number.isNaN(year) ? null : year
}

export interface MBArtistData {
  canonical_name: string | null
  mbid: string | null
  country: string | null
  formed_year: number | null
  genres: string[]
  tags: string[]
  bio_summary: string | null
  wikipedia_url: string | null
}

async function fetchWikipediaBio(artistName: string): Promise<string | null> {
  try {
    const params = new URLSearchParams({
      action: 'query', format: 'json', titles: artistName,
      prop: 'extracts', exintro: '1', explaintext: '1', redirects: '1',
    })
    const resp = await fetch(`https://en.wikipedia.org/w/api.php?${params}`, {
      headers: { 'User-Agent': USER_AGENT },
    })
    if (!resp.ok) return null
    const data = await resp.json<any>()
    const pages = data?.query?.pages ?? {}
    for (const page of Object.values(pages) as any[]) {
      if (page.extract) {
        const text = page.extract.trim()
        const para = text.includes('\n') ? text.split('\n')[0] : text.slice(0, 500)
        return para.slice(0, 500)
      }
    }
    return null
  } catch {
    return null
  }
}

async function fetchArtistFromMusicBrainz(artistName: string, mbid: string | null): Promise<MBArtistData | null> {
  try {
    let url: string
    if (mbid) {
      url = `https://musicbrainz.org/ws/2/artist/${mbid}?fmt=json&inc=genres+tags+aliases`
    } else {
      const params = new URLSearchParams({
        query: artistName, fmt: 'json', limit: '1', inc: 'genres+tags+aliases',
      })
      url = `https://musicbrainz.org/ws/2/artist?${params}`
    }
    const resp = await fetch(url, { headers: { 'User-Agent': USER_AGENT } })
    if (!resp.ok) return null
    const data = await resp.json<any>()
    const artist = mbid ? data : (data.artists ?? [])[0]
    if (!artist?.id) return null

    const name = artist.name ?? artistName
    const bio = await fetchWikipediaBio(name)

    return {
      canonical_name: name,
      mbid: artist.id,
      country: artist.country ?? null,
      formed_year: parseYear(artist['life-span']?.begin),
      genres: (artist.genres ?? []).map((g: any) => g.name),
      tags: (artist.tags ?? []).map((t: any) => t.name),
      bio_summary: bio,
      wikipedia_url: bio ? `https://en.wikipedia.org/wiki/${name.replace(/ /g, '_')}` : null,
    }
  } catch {
    return null
  }
}

interface LastfmData {
  tags: string[]
  bio: string | null
  listeners: number | null
  playcount: number | null
  url: string | null
}

async function fetchArtistFromLastfm(artistName: string): Promise<LastfmData | null> {
  try {
    const params = new URLSearchParams({
      method: 'artist.getinfo', artist: artistName, api_key: LASTFM_API_KEY, format: 'json',
    })
    const resp = await fetch(`https://ws.audioscrobbler.com/2.0/?${params}`, {
      headers: { 'User-Agent': USER_AGENT },
    })
    if (!resp.ok) return null
    const data = await resp.json<any>()
    const artist = data?.artist
    if (!artist) return null

    let tagList = artist.tags?.tag ?? []
    if (!Array.isArray(tagList)) tagList = [tagList]
    const tags = tagList.filter((t: any) => t?.name).map((t: any) => t.name)

    let bioSummary: string | null = artist.bio?.summary ?? null
    if (bioSummary) {
      bioSummary = bioSummary.replace(/<a href="https?:\/\/www\.last\.fm[^"]*"[^>]*>.*?<\/a>/g, '').trim()
      bioSummary = bioSummary.slice(0, 800) || null
    }

    return {
      tags,
      bio: bioSummary,
      listeners: artist.stats?.listeners ? Number(artist.stats.listeners) : null,
      playcount: artist.stats?.playcount ? Number(artist.stats.playcount) : null,
      url: artist.url ?? null,
    }
  } catch {
    return null
  }
}

export interface ArtistEnrichmentResult {
  mbid: string | null
  canonical_name: string | null
  country: string | null
  formed_year: number | null
  genres: string[]
  tags: string[]
  bio_summary: string | null
  wikipedia_url: string | null
  lastfm_tags: string[]
  lastfm_bio: string | null
  lastfm_listeners: number | null
  lastfm_playcount: number | null
  lastfm_url: string | null
}

/**
 * Fetch fresh MusicBrainz + Last.fm data for an artist. Always hits both
 * APIs — callers decide (by checking their own cache first) whether a fresh
 * fetch is actually warranted, same division of responsibility as
 * /admin/edit-artist keeps in the Python version.
 */
export async function fetchArtistEnrichment(artistName: string, mbid: string | null): Promise<ArtistEnrichmentResult> {
  const mb = await fetchArtistFromMusicBrainz(artistName, mbid)
  const lf = await fetchArtistFromLastfm(mb?.canonical_name ?? artistName)

  return {
    mbid: mb?.mbid ?? mbid ?? null,
    canonical_name: mb?.canonical_name ?? null,
    country: mb?.country ?? null,
    formed_year: mb?.formed_year ?? null,
    genres: mb?.genres ?? [],
    tags: mb?.tags ?? [],
    bio_summary: mb?.bio_summary ?? null,
    wikipedia_url: mb?.wikipedia_url ?? null,
    lastfm_tags: lf?.tags ?? [],
    lastfm_bio: lf?.bio ?? null,
    lastfm_listeners: lf?.listeners ?? null,
    lastfm_playcount: lf?.playcount ?? null,
    lastfm_url: lf?.url ?? null,
  }
}
