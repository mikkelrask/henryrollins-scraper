/**
 * Henry Rollins Listens To — Cloudflare Worker API
 *
 * Rewrite of the Python FastAPI backend in Hono + D1.
 *
 * ── Local dev ──
 *   npx wrangler dev
 *   # or: npx wrangler dev --remote (uses real D1)
 *
 * ── Deploy ──
 *   npx wrangler deploy
 */

import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { secureHeaders } from 'hono/secure-headers'
import type { Env } from './db'

// Routers
import { episodesRouter } from './routers/episodes'
import { artistsRouter } from './routers/artists'
import { albumsRouter } from './routers/albums'
import { tracksRouter } from './routers/tracks'
import { statsRouter } from './routers/stats'
import { recommendsRouter } from './routers/recommends'
import { searchRouter } from './routers/search'
import { adminRouter } from './routers/admin'

const app = new Hono<{ Bindings: Env }>()

// ── Middleware ──

app.use(
  '/api/*',
  cors({
    origin: (origin) => {
      if (!origin) return origin
      try {
        const url = new URL(origin)
        if (
          url.hostname === 'localhost' ||
          url.hostname === '127.0.0.1' ||
          url.hostname.endsWith('.pages.dev') ||
          url.hostname.endsWith('.workers.dev')
        ) {
          return origin
        }
      } catch {
        /* ignore malformed URLs */
      }
      return null
    },
    credentials: true,
  }),
)
app.use('/api/*', secureHeaders())

// ── Health ──

app.get('/api/health', (c) => {
  return c.json({ status: 'ok', episodes: 498, tracks: 16935, artists: 2335 })
})

// ── Routers ──

app.route('/api/episodes', episodesRouter)
app.route('/api/artists', artistsRouter)
app.route('/api/albums', albumsRouter)
app.route('/api/tracks', tracksRouter)
app.route('/api/stats', statsRouter)
app.route('/api/recommends', recommendsRouter)
app.route('/api/search', searchRouter)
app.route('/api/admin', adminRouter)

// ── 404 catch-all ──

app.notFound((c) => c.json({ error: 'Not found' }, 404))

export default app
