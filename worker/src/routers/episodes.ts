/**
 * Episode endpoints — list with pagination, detail with track listing + corrections.
 */

import { Hono } from 'hono'
import type { Env } from '../db'
import { DB } from '../db'

export const episodesRouter = new Hono<{ Bindings: Env }>()

// ── List episodes ──

episodesRouter.get('/', async (c) => {
  const db = DB(c.env)
  const page = Math.max(1, Number(c.req.query('page')) || 1)
  const perPage = Math.max(1, Number(c.req.query('per_page')) || 20)
  const sort = c.req.query('sort') || '-broadcast'

  const orderDir = sort.startsWith('-') ? 'DESC' : 'ASC'
  const orderCol = sort.replace(/^-/, '')
  const offset = (page - 1) * perPage

  const { results: rows } = await db.all<{
    broadcast: number; date: string; title: string
    track_count: number; unique_artists: number
  }>(
    `SELECT e.broadcast, e.date, e.title,
            COUNT(t.id) as track_count,
            COUNT(DISTINCT t.artist) as unique_artists
     FROM episodes e
     LEFT JOIN tracks t ON t.episode_id = e.id
     GROUP BY e.id
     ORDER BY e.${orderCol} ${orderDir}
     LIMIT ? OFFSET ?`,
    perPage, offset,
  )

  const total = (await db.one<{ c: number }>('SELECT COUNT(*) as c FROM episodes'))?.c ?? 0

  const items = (rows ?? []).map((r) => ({
    broadcast: r.broadcast ?? 0,
    date: r.date ?? '',
    title: r.title ?? `Broadcast #${r.broadcast}`,
    track_count: r.track_count,
    unique_artists: r.unique_artists,
    repeat_rate: r.track_count > 0
      ? Math.round(((r.track_count - r.unique_artists) / r.track_count) * 1000) / 10
      : 0,
  }))

  return c.json({ items, total, page, per_page: perPage })
})

// ── Get episode detail ──

episodesRouter.get('/:ident', async (c) => {
  const db = DB(c.env)
  const ident = c.req.param('ident')

  // Try broadcast number first, then date string
  let ep: {
    id: number; broadcast: number; date: string; title: string; url: string
  } | null = null

  const broadcastNum = Number(ident)
  if (!Number.isNaN(broadcastNum)) {
    ep = await db.one(
      'SELECT id, broadcast, date, title, url FROM episodes WHERE broadcast = ?',
      broadcastNum,
    )
  }
  if (!ep) {
    ep = await db.one(
      'SELECT id, broadcast, date, title, url FROM episodes WHERE date = ?',
      ident,
    )
  }
  if (!ep) {
    return c.json({ error: 'Episode not found' }, 404)
  }

  // Tracks
  const { results: trackRows } = await db.all<{
    hour: number; position: number; artist: string; title: string; album: string | null
  }>(
    `SELECT t.hour, t.position, art.name as artist, t.title, alb.name as album
     FROM tracks t
     JOIN artists art ON t.artist_id = art.id
     LEFT JOIN albums alb ON t.album_id = alb.id
     WHERE t.episode_id = ?
     ORDER BY t.hour, t.position`,
    ep.id,
  )

  // Corrections from enrichment tables
  const { results: corrections } = await db.all<{
    track_id: number | null; corrected_data: string; hour: number; position: number
  }>(
    `SELECT track_id, corrected_data
     FROM corrections WHERE episode_id = ?`,
    ep.broadcast,
  )

  const correctionMap = new Map<string, Record<string, unknown>>()
  for (const c of corrections ?? []) {
    try {
      const data = JSON.parse(c.corrected_data as unknown as string) as Record<string, unknown>
      const key = c.track_id ? String(c.track_id) : `${data.hour}:${data.position}`
      correctionMap.set(key, data)
    } catch { /* skip malformed JSON */ }
  }

  const trackList = (trackRows ?? []).map((t) => {
    const data = correctionMap.get(String(t.position)) ?? correctionMap.get(`${t.hour}:${t.position}`) ?? {}
    return {
      hour: (data.hour as number) ?? t.hour,
      position: (data.position as number) ?? t.position,
      artist: (data.artist as string) ?? t.artist,
      title: (data.title as string) ?? t.title,
      album: (data.album as string) ?? t.album ?? null,
    }
  })

  // Bandcamp links
  const { results: linkRows } = await db.all<{ url: string; label: string }>(
    'SELECT url, label FROM links WHERE episode_id = ?',
    ep.id,
  )
  const bandcampLinks = (linkRows ?? []).map((l) => ({
    url: l.url,
    label: l.label ?? '',
  }))

  const uniqueArtists = new Set(trackList.map((t) => t.artist)).size
  const repeatRate = trackList.length > 0
    ? Math.round(((trackList.length - uniqueArtists) / trackList.length) * 1000) / 10
    : 0

  return c.json({
    broadcast: ep.broadcast,
    date: ep.date ?? '',
    title: ep.title ?? `Broadcast #${ep.broadcast}`,
    url: ep.url ?? '',
    tracks: trackList,
    bandcamp_links: bandcampLinks,
    stats: {
      track_count: trackList.length,
      unique_artists: uniqueArtists,
      repeat_rate: repeatRate,
    },
  })
})
