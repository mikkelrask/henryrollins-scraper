/**
 * Tracks router — list/search all tracks ever played on the show.
 */

import { Hono } from 'hono'
import type { Env } from '../db'
import { DB } from '../db'

export const tracksRouter = new Hono<{ Bindings: Env }>()

tracksRouter.get('/', async (c) => {
  const db = DB(c.env)
  const page = Math.max(1, Number(c.req.query('page')) || 1)
  const perPage = Math.max(1, Math.min(200, Number(c.req.query('per_page')) || 50))
  const sort = c.req.query('sort') || '-plays'
  const search = c.req.query('search') || ''
  const offset = (page - 1) * perPage

  const whereClauses: string[] = ['1=1']
  const params: unknown[] = []

  if (search) {
    whereClauses.push('(t.title LIKE ? OR t.artist LIKE ?)')
    params.push(`%${search}%`, `%${search}%`)
  }

  const whereSQL = 'WHERE ' + whereClauses.join(' AND ')
  const orderDir = sort.startsWith('-') ? 'DESC' : 'ASC'
  const orderCol = sort.replace(/^-/, '')

  const total = (await db.one<{ c: number }>(
    `SELECT COUNT(*) as c FROM (
      SELECT t.title, t.artist_id, t.album_id FROM tracks t ${whereSQL}
      GROUP BY t.title, t.artist_id, t.album_id
    )`,
    ...params,
  ))?.c ?? 0

  const { results: rows } = await db.all<{
    title: string; artist: string; album: string | null
    plays: number; episodes: number; last_played: string | null
  }>(
    `SELECT t.title, art.name as artist, alb.name as album,
            COUNT(*) as plays,
            COUNT(DISTINCT t.episode_id) as episodes,
            MAX(e.date) as last_played
     FROM tracks t
     JOIN episodes e ON e.id = t.episode_id
     JOIN artists art ON t.artist_id = art.id
     LEFT JOIN albums alb ON t.album_id = alb.id
     ${whereSQL}
     GROUP BY t.title, t.artist_id, t.album_id
     ORDER BY ${orderCol} ${orderDir}
     LIMIT ? OFFSET ?`,
    ...params, perPage, offset,
  )

  return c.json({
    items: (rows ?? []).map((r) => ({
      title: r.title,
      plays: r.plays,
      episodes: r.episodes,
      last_played: r.last_played ?? null,
      artist: r.artist,
      album: r.album ?? null,
    })),
    total,
    page,
    per_page: perPage,
  })
})
