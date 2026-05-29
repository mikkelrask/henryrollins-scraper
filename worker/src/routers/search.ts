/**
 * Search endpoint — fuzzy search across artists, albums, and tracks.
 */

import { Hono } from 'hono'
import type { Env } from '../db'
import { DB } from '../db'

export const searchRouter = new Hono<{ Bindings: Env }>()

searchRouter.get('/', async (c) => {
  const db = DB(c.env)
  const q = c.req.query('q') || ''

  const empty = { artists: [], albums: [], tracks: [] }
  if (!q) return c.json(empty)

  const term = `%${q}%`

  const { results: artists } = await db.all<{ name: string; plays: number }>(
    `SELECT artist as name, COUNT(*) as plays
     FROM tracks WHERE artist LIKE ?
     GROUP BY artist ORDER BY plays DESC LIMIT 10`,
    term,
  )

  const { results: albums } = await db.all<{ name: string; artist: string; plays: number }>(
    `SELECT album as name, artist, COUNT(*) as plays
     FROM tracks WHERE album LIKE ?
     GROUP BY album, artist ORDER BY plays DESC LIMIT 10`,
    term,
  )

  const { results: tracks } = await db.all<{ name: string; artist: string; plays: number }>(
    `SELECT title as name, artist, COUNT(*) as plays
     FROM tracks WHERE title LIKE ?
     GROUP BY artist, title ORDER BY plays DESC LIMIT 10`,
    term,
  )

  return c.json({
    artists: (artists ?? []).map((a) => ({ name: a.name, plays: a.plays })),
    albums: (albums ?? []).map((a) => ({ name: a.name, artist: a.artist, plays: a.plays })),
    tracks: (tracks ?? []).map((t) => ({ name: t.name, artist: t.artist, plays: t.plays })),
  })
})
