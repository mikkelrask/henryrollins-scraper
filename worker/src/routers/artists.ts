/**
 * Artist endpoints — list, detail, top, timeline, heatmap, album breakdown.
 */

import { Hono } from 'hono'
import type { Env } from '../db'
import { DB } from '../db'

export const artistsRouter = new Hono<{ Bindings: Env }>()

const PRIOR_STRENGTH = 10

function bayesianRli(plays: number, episodes: number, prior: number): number {
  return Math.round(((plays + prior * PRIOR_STRENGTH) / (episodes + PRIOR_STRENGTH)) * 100) / 100
}

function computeBadge(plays: number, episodes: number, totalEpisodes: number): string {
  const coverage = totalEpisodes > 0 ? episodes / totalEpisodes : 0
  if (plays > 100) return 'fanatic_favorite'
  if (plays > 50 && coverage > 0.3) return 'signature_artist'
  if (plays <= 5) return 'deep_cut'
  return 'regular'
}

function calcStreak(broadcasts: (number | null)[]): number {
  const valid = broadcasts.filter((b): b is number => b !== null)
  if (valid.length === 0) return 0
  const epsSet = new Set(valid)
  let longest = 0
  let current = 0
  const min = Math.min(...valid)
  const max = Math.max(...valid)
  for (let ep = min; ep <= max; ep++) {
    if (epsSet.has(ep)) {
      current++
      longest = Math.max(longest, current)
    } else {
      current = 0
    }
  }
  return longest
}

// ── List artists ──

artistsRouter.get('/', async (c) => {
  const db = DB(c.env)
  const page = Math.max(1, Number(c.req.query('page')) || 1)
  const perPage = Math.max(1, Math.min(200, Number(c.req.query('per_page')) || 50))
  const sort = c.req.query('sort') || '-plays'
  const search = c.req.query('search') || ''
  const badge = c.req.query('badge') || ''
  const country = c.req.query('country') || ''
  const genre = c.req.query('genre') || ''

  const totalEpisodes = (await db.one<{ c: number }>('SELECT COUNT(*) as c FROM episodes'))?.c ?? 1

  // Compute global average RLI
  const priorRow = await db.one<{ avg_rli: number }>(
    `SELECT SUM(plays) * 1.0 / SUM(episodes) as avg_rli
     FROM (
       SELECT COUNT(*) as plays, COUNT(DISTINCT episode_id) as episodes
       FROM tracks
       GROUP BY artist
       HAVING episodes >= 3
     )`,
  )
  const prior = priorRow?.avg_rli ?? 1.0

  // Base query
  const whereClauses: string[] = []
  const params: unknown[] = []

  if (search) {
    whereClauses.push('t.artist LIKE ?')
    params.push(`%${search}%`)
  }

  const whereSQL = whereClauses.length > 0 ? 'WHERE ' + whereClauses.join(' AND ') : ''

  const { results: rows } = await db.all<{
    artist: string; plays: number; episodes: number
    album_count: number; first_ep: number | null; last_ep: number | null
  }>(
    `SELECT t.artist,
            COUNT(*) as plays,
            COUNT(DISTINCT t.episode_id) as episodes,
            COUNT(DISTINCT t.album) as album_count,
            MIN(e.broadcast) as first_ep,
            MAX(e.broadcast) as last_ep
     FROM tracks t
     JOIN episodes e ON e.id = t.episode_id
     ${whereSQL}
     GROUP BY t.artist`,
    ...params,
  )

  // Country filter
  let allowedArtists: Set<string> | null = null
  if (country) {
    const { results: countryRows } = await db.all<{ artist_name: string }>(
      'SELECT artist_name FROM artist_enrichment WHERE country = ?',
      country,
    )
    allowedArtists = new Set((countryRows ?? []).map((r) => r.artist_name))
  }

  // Genre filter
  if (genre) {
    const genreLC = genre.toLowerCase()
    const { results: genreRows } = await db.all<{ artist_name: string; genres: string | null; lastfm_tags: string | null }>(
      `SELECT artist_name, genres, lastfm_tags
       FROM artist_enrichment
       WHERE genres IS NOT NULL OR lastfm_tags IS NOT NULL`,
    )
    const matched = new Set<string>()
    for (const row of genreRows ?? []) {
      const tags: string[] = []
      try { tags.push(...JSON.parse(row.genres ?? '[]')) } catch { /* ignore */ }
      try { tags.push(...JSON.parse(row.lastfm_tags ?? '[]')) } catch { /* ignore */ }
      if (tags.some((t) => t.toLowerCase() === genreLC)) {
        matched.add(row.artist_name)
      }
    }
    if (allowedArtists !== null) {
      allowedArtists = allowedArtists.intersection(matched)
    } else {
      allowedArtists = matched
    }
  }

  // Build + filter in-memory
  let allArtists = (rows ?? [])
    .filter((r) => !allowedArtists || allowedArtists!.has(r.artist))
    .map((r) => {
      const coverage = totalEpisodes > 0 ? Math.round((r.episodes / totalEpisodes) * 1000) / 10 : 0
      const albumDiv = r.plays > 0 ? Math.round((r.album_count / r.plays) * 100) / 100 : 0
      return {
        artist: r.artist,
        plays: r.plays,
        episodes: r.episodes,
        rli: bayesianRli(r.plays, r.episodes, prior),
        coverage,
        album_diversity: albumDiv,
        first_episode: r.first_ep != null ? String(r.first_ep) : null,
        last_episode: r.last_ep != null ? String(r.last_ep) : null,
        badge: computeBadge(r.plays, r.episodes, totalEpisodes),
      }
    })

  // Badge filter (after computation)
  if (badge) {
    allArtists = allArtists.filter((a) => a.badge === badge)
  }

  // Sort
  const orderDir = sort.startsWith('-') ? -1 : 1
  const orderCol = sort.replace(/^-/, '') as keyof typeof allArtists[0]
  allArtists.sort((a, b) => {
    const aVal = a[orderCol] ?? 0
    const bVal = b[orderCol] ?? 0
    if (typeof aVal === 'string' && typeof bVal === 'string') {
      return aVal.localeCompare(bVal) * orderDir
    }
    return ((aVal as number) - (bVal as number)) * orderDir
  })

  // Paginate
  const offset = (page - 1) * perPage
  const items = allArtists.slice(offset, offset + perPage)

  return c.json({ items, total: allArtists.length, page, per_page: perPage })
})

// ── Top artists ──

artistsRouter.get('/top', async (c) => {
  const db = DB(c.env)
  const limit = Math.min(100, Math.max(1, Number(c.req.query('limit')) || 20))
  const metric = c.req.query('metric') || 'plays'
  const totalEpisodes = (await db.one<{ c: number }>('SELECT COUNT(*) as c FROM episodes'))?.c ?? 1

  const priorRow = await db.one<{ avg_rli: number }>(
    `SELECT SUM(plays) * 1.0 / SUM(episodes) as avg_rli
     FROM (SELECT COUNT(*) as plays, COUNT(DISTINCT episode_id) as episodes FROM tracks GROUP BY artist HAVING episodes >= 3)`,
  )
  const prior = priorRow?.avg_rli ?? 1.0

  const { results: rows } = await db.all<{ artist: string; plays: number; episodes: number }>(
    'SELECT artist, COUNT(*) as plays, COUNT(DISTINCT episode_id) as episodes FROM tracks GROUP BY artist',
  )

  let items = (rows ?? []).map((r) => ({
    artist: r.artist,
    plays: r.plays,
    episodes: r.episodes,
    rli: bayesianRli(r.plays, r.episodes, prior),
    coverage: Math.round((r.episodes / totalEpisodes) * 1000) / 10,
    badge: computeBadge(r.plays, r.episodes, totalEpisodes),
  }))

  if (metric === 'rli') items.sort((a, b) => b.rli - a.rli)
  else if (metric === 'episodes') items.sort((a, b) => b.episodes - a.episodes)
  else if (metric === 'coverage') items.sort((a, b) => b.coverage - a.coverage)
  else items.sort((a, b) => b.plays - a.plays)

  return c.json(items.slice(0, limit))
})

// ── Artist albums ──

artistsRouter.get('/albums/:name{.+}', async (c) => {
  const db = DB(c.env)
  const name = decodeURIComponent(c.req.param('name'))

  const { results: rows } = await db.all<{
    album: string; plays: number; distinct_tracks: number
  }>(
    `SELECT album, COUNT(*) as plays, COUNT(DISTINCT title) as distinct_tracks
     FROM tracks WHERE artist = ? AND album != ''
     GROUP BY album ORDER BY plays DESC`,
    name,
  )

  // Artwork for first 50 albums
  const items: Array<{
    album: string; artist: string; plays: number
    distinct_tracks: number; artwork_url: string | null; release_date: string | null
  }> = []

  for (let i = 0; i < (rows ?? []).length; i++) {
    const r = rows![i]
    let artworkUrl: string | null = null
    let releaseDate: string | null = null
    if (i < 50) {
      const art = await db.one<{ artwork_url: string | null; release_date: string | null }>(
        'SELECT artwork_url, release_date FROM album_art WHERE album_name = ? AND artist_name = ?',
        r.album, name,
      )
      artworkUrl = art?.artwork_url ?? null
      releaseDate = art?.release_date ?? null
    }
    items.push({
      album: r.album,
      artist: name,
      plays: r.plays,
      distinct_tracks: r.distinct_tracks,
      artwork_url: artworkUrl,
      release_date: releaseDate,
    })
  }

  return c.json({ items, total: items.length, artist: name })
})

// ── Artist tracks ──

artistsRouter.get('/tracks/:name{.+}', async (c) => {
  const db = DB(c.env)
  const name = decodeURIComponent(c.req.param('name'))
  const page = Math.max(1, Number(c.req.query('page')) || 1)
  const perPage = Math.max(1, Math.min(200, Number(c.req.query('per_page')) || 50))
  const offset = (page - 1) * perPage

  const total = (await db.one<{ c: number }>(
    'SELECT COUNT(*) as c FROM tracks WHERE artist = ?', name,
  ))?.c ?? 0

  const { results: rows } = await db.all<{
    title: string; album: string | null; broadcast: number; date: string
    hour: number; position: number
  }>(
    `SELECT t.title, t.album, e.broadcast, e.date, t.hour, t.position
     FROM tracks t
     JOIN episodes e ON e.id = t.episode_id
     WHERE t.artist = ?
     ORDER BY e.broadcast DESC, t.hour, t.position
     LIMIT ? OFFSET ?`,
    name, perPage, offset,
  )

  return c.json({
    items: (rows ?? []).map((r) => ({ ...r, album: r.album ?? null })),
    total, page, per_page: perPage,
  })
})

// ── Artist timeline ──

artistsRouter.get('/timeline/:name{.+}', async (c) => {
  const db = DB(c.env)
  const name = decodeURIComponent(c.req.param('name'))

  const { results: rows } = await db.all<{ broadcast: number | null; date: string; plays: number }>(
    `SELECT e.broadcast, e.date, COUNT(*) as plays
     FROM tracks t
     JOIN episodes e ON e.id = t.episode_id
     WHERE t.artist = ?
     GROUP BY e.id
     ORDER BY e.broadcast ASC`,
    name,
  )

  return c.json(rows ?? [])
})

// ── Artist heatmap (monthly, zero-filled) ──

artistsRouter.get('/heatmap/:name{.+}', async (c) => {
  const db = DB(c.env)
  const name = decodeURIComponent(c.req.param('name'))

  const { results: rows } = await db.all<{ year: string; month: string; plays: number }>(
    `SELECT strftime('%Y', e.date) as year,
            strftime('%m', e.date) as month,
            COUNT(t.id) as plays
     FROM episodes e
     JOIN tracks t ON t.episode_id = e.id
     WHERE e.date != '' AND t.artist = ?
     GROUP BY year, month
     ORDER BY year, month`,
    name,
  )

  if (!rows || rows.length === 0) return c.json([])

  const firstYear = Number(rows[0].year)
  const firstMonth = Number(rows[0].month)
  const lastYear = Number(rows[rows.length - 1].year)
  const lastMonth = Number(rows[rows.length - 1].month)

  const byMonth = new Map<string, number>()
  for (const r of rows) byMonth.set(`${r.year}-${r.month}`, r.plays)

  const result: Array<{ year: string; month: string; plays: number }> = []
  let y = firstYear
  let m = firstMonth
  while (y < lastYear || (y === lastYear && m <= lastMonth)) {
    const key = `${String(y).padStart(4, '0')}-${String(m).padStart(2, '0')}`
    result.push({ year: String(y).padStart(4, '0'), month: String(m).padStart(2, '0'), plays: byMonth.get(key) ?? 0 })
    m++
    if (m > 12) { m = 1; y++ }
  }

  return c.json(result)
})

// ── Artist detail ──

artistsRouter.get('/:name{.+}', async (c) => {
  const db = DB(c.env)
  const name = decodeURIComponent(c.req.param('name'))
  const totalEpisodes = (await db.one<{ c: number }>('SELECT COUNT(*) as c FROM episodes'))?.c ?? 1

  const stats = await db.one<{
    artist: string; plays: number; episodes: number; album_count: number
    first_date: string | null; last_date: string | null
    first_ep: number | null; last_ep: number | null
  }>(
    `SELECT t.artist,
            COUNT(*) as plays,
            COUNT(DISTINCT t.episode_id) as episodes,
            COUNT(DISTINCT t.album) as album_count,
            MIN(e.date) as first_date,
            MAX(e.date) as last_date,
            MIN(e.broadcast) as first_ep,
            MAX(e.broadcast) as last_ep
     FROM tracks t
     JOIN episodes e ON e.id = t.episode_id
     WHERE t.artist = ?
     GROUP BY t.artist`,
    name,
  )

  if (!stats) return c.json({ error: 'Artist not found' }, 404)

  // Top 10 tracks
  const { results: topTrackRows } = await db.all<{ title: string; plays: number; last_played: string | null }>(
    `SELECT t.title, COUNT(*) as plays, MAX(e.date) as last_played
     FROM tracks t
     JOIN episodes e ON e.id = t.episode_id
     WHERE t.artist = ?
     GROUP BY t.title
     ORDER BY plays DESC
     LIMIT 10`,
    name,
  )

  const topTracks = []
  for (const r of topTrackRows ?? []) {
    const albRow = await db.one<{ album: string }>(
      "SELECT album FROM tracks WHERE artist = ? AND title = ? AND album != '' GROUP BY album ORDER BY COUNT(*) DESC LIMIT 1",
      name, r.title,
    )
    topTracks.push({
      title: r.title,
      plays: r.plays,
      last_played: r.last_played,
      album: albRow?.album ?? null,
    })
  }

  // Album breakdown
  const { results: albumRows } = await db.all<{ album: string; plays: number; distinct_tracks: number }>(
    `SELECT album, COUNT(*) as plays, COUNT(DISTINCT title) as distinct_tracks
     FROM tracks WHERE artist = ? AND album != ''
     GROUP BY album ORDER BY plays DESC`,
    name,
  )

  // Timeline
  const { results: timelineRows } = await db.all<{ broadcast: number | null; date: string; plays: number }>(
    `SELECT e.broadcast, e.date, COUNT(*) as plays
     FROM tracks t JOIN episodes e ON e.id = t.episode_id
     WHERE t.artist = ?
     GROUP BY e.id ORDER BY e.broadcast ASC`,
    name,
  )

  const streak = calcStreak((timelineRows ?? []).map((r) => r.broadcast))

  const priorRow = await db.one<{ avg_rli: number }>(
    `SELECT SUM(plays)*1.0/SUM(episodes) as avg_rli FROM (SELECT COUNT(*) as plays, COUNT(DISTINCT episode_id) as episodes FROM tracks GROUP BY artist HAVING episodes >= 3)`,
  )
  const prior = priorRow?.avg_rli ?? 1.0
  const rli = bayesianRli(stats.plays, stats.episodes, prior)
  const coverage = Math.round((stats.episodes / totalEpisodes) * 1000) / 10
  const albumDiv = stats.plays > 0 ? Math.round((stats.album_count / stats.plays) * 100) / 100 : 0
  const badge = computeBadge(stats.plays, stats.episodes, totalEpisodes)

  // Enrichment
  const enrichmentRow = await db.one<Record<string, unknown>>(
    'SELECT * FROM artist_enrichment WHERE artist_name = ?', name,
  )

  let enrichment: Record<string, unknown> | null = null
  if (enrichmentRow) {
    const e = enrichmentRow as Record<string, unknown>
    const parseJSON = (val: unknown): string[] | null => {
      if (typeof val === 'string') {
        try { return JSON.parse(val) } catch { return null }
      }
      return null
    }
    enrichment = {
      mbid: e.mbid ?? null,
      canonical_name: e.canonical_name ?? null,
      country: e.country ?? null,
      formed_year: e.formed_year ?? null,
      genres: parseJSON(e.genres) ?? [],
      tags: parseJSON(e.tags) ?? [],
      bio_summary: e.bio_summary ?? null,
      lastfm_tags: parseJSON(e.lastfm_tags) ?? [],
      lastfm_bio: e.lastfm_bio ?? null,
      lastfm_listeners: e.lastfm_listeners != null ? Number(e.lastfm_listeners) : null,
      lastfm_playcount: e.lastfm_playcount != null ? Number(e.lastfm_playcount) : null,
      lastfm_url: e.lastfm_url ?? null,
    }
  }

  // Album artwork (top 8)
  const albumBreakdown = []
  for (let i = 0; i < (albumRows ?? []).length; i++) {
    const a = albumRows![i]
    let artworkUrl: string | null = null
    let artworkUrlLarge: string | null = null
    let releaseDate: string | null = null
    if (i < 8) {
      const art = await db.one<{ artwork_url: string | null; mbid: string | null; release_date: string | null }>(
        'SELECT artwork_url, mbid, release_date FROM album_art WHERE album_name = ? AND artist_name = ?',
        a.album, name,
      )
      artworkUrl = art?.artwork_url ?? null
      if (art?.mbid) artworkUrlLarge = `https://coverartarchive.org/release/${art.mbid}/front-500`
      releaseDate = art?.release_date ?? null
    }
    albumBreakdown.push({
      album: a.album,
      artist: name,
      plays: a.plays,
      distinct_tracks: a.distinct_tracks,
      artwork_url: artworkUrl,
      artwork_url_large: artworkUrlLarge,
      release_date: releaseDate,
    })
  }

  // Artist DB id
  const artistRow = await db.one<{ id: number }>('SELECT id FROM artists WHERE name = ?', name)

  return c.json({
    id: artistRow?.id ?? null,
    artist: stats.artist,
    plays: stats.plays,
    episodes: stats.episodes,
    rli,
    coverage,
    first_appearance: stats.first_date ?? null,
    last_appearance: stats.last_date ?? null,
    streak,
    album_count: stats.album_count,
    album_diversity: albumDiv,
    enrichment,
    top_tracks: topTracks,
    album_breakdown: albumBreakdown,
    timeline: (timelineRows ?? []).map((t) => ({
      broadcast: t.broadcast,
      date: t.date,
      plays: t.plays,
    })),
    badge,
  })
})
