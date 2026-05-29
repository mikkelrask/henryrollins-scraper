/**
 * Album endpoints — list, detail, heatmap.
 */

import { Hono } from 'hono'
import type { Env } from '../db'
import { DB } from '../db'

export const albumsRouter = new Hono<{ Bindings: Env }>()

function fillHeatmap(
  rows: Array<{ year: string; month: string; plays: number }> | null,
): Array<{ year: string; month: string; plays: number }> {
  if (!rows || rows.length === 0) return []
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
    result.push({
      year: String(y).padStart(4, '0'),
      month: String(m).padStart(2, '0'),
      plays: byMonth.get(key) ?? 0,
    })
    m++
    if (m > 12) { m = 1; y++ }
  }
  return result
}

// ── List albums ──

albumsRouter.get('/', async (c) => {
  const db = DB(c.env)
  const page = Math.max(1, Number(c.req.query('page')) || 1)
  const perPage = Math.max(1, Math.min(200, Number(c.req.query('per_page')) || 50))
  const sort = c.req.query('sort') || '-plays'
  const search = c.req.query('search') || ''
  const offset = (page - 1) * perPage

  const whereClauses = ["t.album != ''"]
  const params: unknown[] = []

  if (search) {
    whereClauses.push('(t.album LIKE ? OR t.artist LIKE ?)')
    params.push(`%${search}%`, `%${search}%`)
  }

  const whereSQL = 'WHERE ' + whereClauses.join(' AND ')

  const orderDir = sort.startsWith('-') ? 'DESC' : 'ASC'
  const orderCol = sort.replace(/^-/, '')

  const total = (await db.one<{ c: number }>(
    `SELECT COUNT(*) as c FROM (SELECT t.album, t.artist FROM tracks t ${whereSQL} GROUP BY t.album, t.artist)`,
    ...params,
  ))?.c ?? 0

  const { results: rows } = await db.all<{
    album: string; artist: string; plays: number
    distinct_tracks: number; episodes: number; last_played: string | null
  }>(
    `SELECT t.album, t.artist,
            COUNT(*) as plays,
            COUNT(DISTINCT t.title) as distinct_tracks,
            COUNT(DISTINCT t.episode_id) as episodes,
            MAX(e.date) as last_played
     FROM tracks t
     JOIN episodes e ON e.id = t.episode_id
     ${whereSQL}
     GROUP BY t.album, t.artist
     ORDER BY ${orderCol} ${orderDir}
     LIMIT ? OFFSET ?`,
    ...params, perPage, offset,
  )

  const items = []
  for (const r of rows ?? []) {
    const art = await db.one<{ artwork_url: string | null }>(
      'SELECT artwork_url FROM album_art WHERE album_name = ? AND artist_name = ?',
      r.album, r.artist,
    )
    items.push({
      album: r.album,
      artist: r.artist,
      plays: r.plays,
      distinct_tracks: r.distinct_tracks,
      episodes: r.episodes,
      last_played: r.last_played ?? null,
      artwork_url: art?.artwork_url ?? null,
    })
  }

  return c.json({ items, total, page, per_page: perPage })
})

// ── Album heatmap ──

albumsRouter.get('/heatmap/:albumName{.+}', async (c) => {
  const db = DB(c.env)
  const albumName = decodeURIComponent(c.req.param('albumName'))

  const artistRow = await db.one<{ artist: string }>(
    "SELECT artist FROM tracks WHERE album = ? AND artist != '' LIMIT 1",
    albumName,
  )
  const artist = artistRow?.artist ?? ''

  const { results: rows } = await db.all<{ year: string; month: string; plays: number }>(
    `SELECT strftime('%Y', e.date) as year,
            strftime('%m', e.date) as month,
            COUNT(t.id) as plays
     FROM episodes e
     JOIN tracks t ON t.episode_id = e.id
     WHERE e.date != '' AND t.album = ? AND t.artist = ?
     GROUP BY year, month
     ORDER BY year, month`,
    albumName, artist,
  )

  return c.json(fillHeatmap(rows ?? null))
})

// ── Album detail ──

albumsRouter.get('/:albumId{.+}', async (c) => {
  const db = DB(c.env)
  const albumName = decodeURIComponent(c.req.param('albumId'))
  const artist = c.req.query('artist') || ''

  // Fetch album stats
  let r: { album: string; artist: string; plays: number; distinct_tracks: number; episodes: number } | null

  if (artist) {
    r = await db.one(
      `SELECT t.album, t.artist, COUNT(*) as plays,
              COUNT(DISTINCT t.title) as distinct_tracks,
              COUNT(DISTINCT t.episode_id) as episodes
       FROM tracks t
       WHERE t.album = ? AND t.artist = ?
       GROUP BY t.album, t.artist`,
      albumName, artist,
    )
  } else {
    r = await db.one(
      `SELECT t.album, t.artist, COUNT(*) as plays,
              COUNT(DISTINCT t.title) as distinct_tracks,
              COUNT(DISTINCT t.episode_id) as episodes
       FROM tracks t
       WHERE t.album = ?
       GROUP BY t.album, t.artist
       ORDER BY plays DESC`,
      albumName,
    )
  }

  if (!r) return c.json({ error: 'Album not found' }, 404)

  // Track plays
  const { results: trackRows } = await db.all<{ title: string; broadcast: number | null; date: string }>(
    `SELECT t.title, e.broadcast, e.date
     FROM tracks t JOIN episodes e ON e.id = t.episode_id
     WHERE t.album = ? AND t.artist = ?
     ORDER BY t.title, e.broadcast`,
    albumName, r.artist,
  )

  // Group tracks
  const trackMap = new Map<string, { broadcast: (number | null)[]; date: string[] }>()
  for (const tr of trackRows ?? []) {
    if (!trackMap.has(tr.title)) trackMap.set(tr.title, { broadcast: [], date: [] })
    const entry = trackMap.get(tr.title)!
    entry.broadcast.push(tr.broadcast)
    entry.date.push(tr.date)
  }

  const tracks = Array.from(trackMap.entries()).map(([title, plays]) => ({
    title,
    plays: plays.broadcast.length,
    last_played: plays.date[plays.date.length - 1] ?? null,
    last_broadcast: plays.broadcast[plays.broadcast.length - 1] ?? null,
    broadcasts: plays.broadcast.map((b, i) => ({
      broadcast: b,
      date: plays.date[i] ?? null,
    })),
  })).sort((a, b) => b.plays - a.plays)

  // Timeline
  const { results: timelineRows } = await db.all<{ broadcast: number | null; date: string; plays: number }>(
    `SELECT e.broadcast, e.date, COUNT(*) as plays
     FROM tracks t JOIN episodes e ON e.id = t.episode_id
     WHERE t.album = ? AND t.artist = ?
     GROUP BY e.id ORDER BY e.broadcast ASC`,
    albumName, r.artist,
  )

  // Heatmap
  const { results: heatRows } = await db.all<{ year: string; month: string; plays: number }>(
    `SELECT strftime('%Y', e.date) as year, strftime('%m', e.date) as month, COUNT(t.id) as plays
     FROM episodes e JOIN tracks t ON t.episode_id = e.id
     WHERE e.date != '' AND t.album = ? AND t.artist = ?
     GROUP BY year, month ORDER BY year, month`,
    albumName, r.artist,
  )

  // Artwork
  const art = await db.one<{ artwork_url: string | null; mbid: string | null; release_group_mbid: string | null; release_date: string | null }>(
    'SELECT artwork_url, mbid, release_group_mbid, release_date FROM album_art WHERE album_name = ? AND artist_name = ?',
    albumName, r.artist,
  )

  const largeUrl = art?.mbid ? `https://coverartarchive.org/release/${art.mbid}/front-500` : null

  // Releases from cache
  let releases: Record<string, unknown>[] = []
  if (art?.release_group_mbid) {
    const rgRow = await db.one<{ data: string }>(
      'SELECT data FROM release_group_cache WHERE rg_mbid = ?',
      art.release_group_mbid,
    )
    if (rgRow) {
      try {
        const rgData = JSON.parse(rgRow.data as unknown as string)
        releases = rgData.releases ?? []
      } catch { /* ignore */ }
    }
  }

  // Unplayed tracks — only if we have an MBID
  let unplayed: string[] = []
  if (art?.mbid) {
    // We can't fetch MusicBrainz data at request time (pre-baked)
    // unplayed remains empty unless pre-baked into album_art
    unplayed = []
  }

  // DB id
  const albumRow = await db.one<{ id: number; artist_id: number | null }>(
    'SELECT a.id, a.artist_id FROM albums a WHERE a.name = ? AND a.artist_id = (SELECT id FROM artists WHERE name = ?)',
    albumName, r.artist,
  )

  return c.json({
    id: albumRow?.id ?? null,
    artist_id: albumRow?.artist_id ?? null,
    album: r.album,
    artist: r.artist,
    plays: r.plays,
    distinct_tracks: r.distinct_tracks,
    episodes: r.episodes,
    tracks,
    timeline: (timelineRows ?? []).map((t) => ({ broadcast: t.broadcast, date: t.date, plays: t.plays })),
    heatmap: fillHeatmap(heatRows ?? null),
    artwork_url: art?.artwork_url ?? null,
    artwork_url_large: largeUrl,
    mbid: art?.mbid ?? null,
    release_group_mbid: art?.release_group_mbid ?? null,
    release_date: art?.release_date ?? null,
    unplayed_tracks: unplayed,
    releases,
  })
})
