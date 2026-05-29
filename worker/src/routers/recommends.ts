/**
 * Bandcamp "Henry Recommends" endpoints.
 */

import { Hono } from 'hono'
import type { Env } from '../db'
import { DB } from '../db'

export const recommendsRouter = new Hono<{ Bindings: Env }>()

function parseBandcampUrl(url: string): { artist: string; album: string } {
  try {
    const parsed = new URL(url)
    const host = parsed.hostname
    const path = parsed.pathname.replace(/\/$/, '')

    let artist = host.replace('.bandcamp.com', '')
    if (!host.includes('.bandcamp.com')) artist = host

    let album = ''
    if (path.includes('/album/')) {
      album = path.split('/album/')[1]
        .replace(/-/g, ' ')
        .replace(/\b\w/g, (c) => c.toUpperCase())
    } else if (path.includes('/track/')) {
      album = path.split('/track/')[1]
        .replace(/-/g, ' ')
        .replace(/\b\w/g, (c) => c.toUpperCase())
    } else if (path === '/releases' || !path) {
      album = 'Profile / Releases'
    } else {
      album = path.replace(/-/g, ' ')
        .replace(/\b\w/g, (c) => c.toUpperCase())
    }

    return { artist, album }
  } catch {
    return { artist: url, album: '' }
  }
}

// ── List recommends ──

recommendsRouter.get('/', async (c) => {
  const db = DB(c.env)
  const page = Math.max(1, Number(c.req.query('page')) || 1)
  const perPage = Math.max(1, Math.min(100, Number(c.req.query('per_page')) || 30))
  const sort = c.req.query('sort') || '-episode_count'
  const linkType = c.req.query('link_type') || 'album'
  const offset = (page - 1) * perPage

  let whereClause = ''
  if (linkType === 'album') whereClause = "WHERE l.url LIKE '%/album/%'"
  else if (linkType === 'label') whereClause = "WHERE l.url NOT LIKE '%/album/%' AND l.url NOT LIKE '%/track/%'"

  const orderDir = sort.startsWith('-') ? 'DESC' : 'ASC'
  const orderCol = sort.replace(/^-/, '')

  const { results: totalRow } = await db.all<{ c: number }>(
    `SELECT COUNT(*) as c FROM (SELECT l.url FROM links l ${whereClause} GROUP BY l.url)`,
  )
  const total = totalRow?.[0]?.c ?? 0

  const { results: rows } = await db.all<{
    url: string; episode_count: number; first_seen: string | null
    last_seen: string | null; episode_ids: string | null
  }>(
    `SELECT l.url,
            COUNT(DISTINCT e.id) as episode_count,
            MIN(e.date) as first_seen,
            MAX(e.date) as last_seen,
            GROUP_CONCAT(DISTINCT e.broadcast) as episode_ids
     FROM links l
     JOIN episodes e ON e.id = l.episode_id
     ${whereClause}
     GROUP BY l.url
     ORDER BY ${orderCol} ${orderDir}
     LIMIT ? OFFSET ?`,
    perPage, offset,
  )

  const items = (rows ?? []).map((r) => {
    const parsed = parseBandcampUrl(r.url)
    const epIds = (r.episode_ids ?? '')
      .split(',')
      .map((x) => Number(x.trim()))
      .filter((x) => !Number.isNaN(x))
      .sort((a, b) => b - a)
      .slice(0, 10)

    return {
      url: r.url,
      bandcamp_artist: parsed.artist,
      album_title: parsed.album,
      episode_count: r.episode_count,
      first_seen: r.first_seen ?? null,
      last_seen: r.last_seen ?? null,
      episodes: epIds,
    }
  })

  return c.json({ items, total, page, per_page: perPage })
})

// ── Recommend artists ──

recommendsRouter.get('/artists', async (c) => {
  const db = DB(c.env)

  const { results: rows } = await db.all<{
    url: string; total_episodes: number; last_seen: string | null
  }>(
    `SELECT l.url,
            COUNT(DISTINCT e.id) as total_episodes,
            MAX(e.date) as last_seen
     FROM links l
     JOIN episodes e ON e.id = l.episode_id
     WHERE l.url LIKE '%/album/%'
     GROUP BY l.url
     ORDER BY total_episodes DESC
     LIMIT 50`,
  )

  const byArtist = new Map<string, { uniqueAlbums: Set<string>; totalEpisodes: number; lastSeen: string }>()

  for (const r of rows ?? []) {
    const parsed = parseBandcampUrl(r.url)
    if (!byArtist.has(parsed.artist)) {
      byArtist.set(parsed.artist, { uniqueAlbums: new Set(), totalEpisodes: 0, lastSeen: '' })
    }
    const entry = byArtist.get(parsed.artist)!
    entry.uniqueAlbums.add(r.url)
    entry.totalEpisodes += r.total_episodes
    if (r.last_seen && r.last_seen > entry.lastSeen) entry.lastSeen = r.last_seen
  }

  const items = Array.from(byArtist.entries())
    .sort((a, b) => b[1].totalEpisodes - a[1].totalEpisodes)
    .map(([artist, data]) => ({
      bandcamp_artist: artist,
      unique_albums: data.uniqueAlbums.size,
      total_episodes: data.totalEpisodes,
      last_seen: data.lastSeen || null,
    }))

  return c.json(items)
})

// ── Recommends by episode ──

recommendsRouter.get('/by-episode/:broadcast', async (c) => {
  const db = DB(c.env)
  const broadcast = Number(c.req.param('broadcast'))

  if (Number.isNaN(broadcast)) return c.json({ error: 'Invalid broadcast number' }, 400)

  const { results: rows } = await db.all<{ url: string; label: string }>(
    `SELECT l.url, l.label
     FROM links l JOIN episodes e ON e.id = l.episode_id
     WHERE e.broadcast = ?
     ORDER BY l.id`,
    broadcast,
  )

  return c.json((rows ?? []).map((r) => ({
    url: r.url,
    label: r.label ?? '',
  })))
})
