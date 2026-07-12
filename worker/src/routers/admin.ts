/**
 * Admin endpoints — auth, cluster detection, merge, corrections, track browser.
 */

import { Hono, Context } from 'hono'
import { HTTPException } from 'hono/http-exception'
import type { Env } from '../db'
import { DB } from '../db'
import { fetchArtistEnrichment } from '../services/enrichment'

export const adminRouter = new Hono<{ Bindings: Env }>()

// ── Auth middleware ──

function adminRoute<T extends Hono<{ Bindings: Env }>>(router: T): T {
  router.use('*', async (c, next) => {
    const key = c.env.ADMIN_API_KEY
    if (key) {
      const provided = c.req.header('x-admin-key')
      if (provided !== key) {
        throw new HTTPException(401, { message: 'Unauthorized' })
      }
    }
    await next()
  })
  return router
}

// All routes in this router require admin
const a = adminRoute(adminRouter)

// ── Auth check ──

a.get('/check', async (c) => {
  const key = c.env.ADMIN_API_KEY
  if (!key) return c.json({ ok: true, mode: 'dev' })
  const provided = c.req.header('x-admin-key')
  if (provided === key) return c.json({ ok: true, mode: 'prod' })
  throw new HTTPException(401, { message: 'Unauthorized' })
})

// ── Helpers ──

function baseName(name: string): string {
  let n = name.trim()
  // Handle parenthetical cross-references
  const parenMatch = n.match(/^([\w\s]{1,15}?)\s*\([^)]*?([+&/])\s*([\w\s.]{5,})\s*\)$/i)
  if (parenMatch) {
    const outer = parenMatch[1].trim()
    const inner = parenMatch[3].trim()
    if (outer.split(/\s+/).length <= 2 || ['various', 'misc', 'plus', 'and', 'feat', 'with'].includes(outer.toLowerCase())) {
      n = inner
    }
  }

  const nLower = n.toLowerCase()
  const seps = [' & ', ' w/ ', ' + ', ' feat ', ' vs ', ' / ', ' with ', ' and ', ' x ', ' con ', ' y ', ' mit ', ' avec ', ' plus ', ' en ', ' et ']
  for (const sep of seps) {
    const idx = nLower.indexOf(sep)
    if (idx !== -1) {
      n = n.slice(0, idx)
      break
    }
  }

  n = n.toLowerCase().trim()
  n = n.replace(/[^\w\s]/g, ' ')
  n = n.replace(/\s+/g, ' ').trim()
  return n
}

function trigramSimilarity(a: string, b: string): number {
  if (!a || !b) return 0
  const trigrams = (s: string) => {
    const set = new Set<string>()
    for (let i = 0; i < s.length - 2; i++) set.add(s.slice(i, i + 3))
    return set
  }
  const ta = trigrams(a.toLowerCase().trim())
  const tb = trigrams(b.toLowerCase().trim())
  if (ta.size === 0 && tb.size === 0) return 1
  const intersection = new Set([...ta].filter((x) => tb.has(x)))
  const union = new Set([...ta, ...tb])
  return union.size > 0 ? intersection.size / union.size : 0
}

function parseIds(raw: string): number[] {
  return raw.split(',').map((x) => Number(x.trim())).filter((x) => !Number.isNaN(x))
}

// ── Entities list ──

a.get('/entities', async (c) => {
  const db = DB(c.env)
  const type = c.req.query('type') || 'artist'
  const q = c.req.query('q') || ''
  const term = `%${q}%`

  if (type === 'artist') {
    const { results: rows } = await db.all<{ id: number; name: string; track_count: number }>(
      `SELECT id, name, (SELECT COUNT(*) FROM tracks WHERE artist_id = artists.id) as track_count
       FROM artists WHERE name LIKE ? ORDER BY track_count DESC LIMIT 50`,
      term,
    )
    return c.json(rows ?? [])
  }

  const { results: rows } = await db.all<{ id: number; name: string; artist_name: string; track_count: number }>(
    `SELECT a.id, a.name,
            (SELECT ar.name FROM artists ar WHERE ar.id = a.artist_id) as artist_name,
            (SELECT COUNT(*) FROM tracks WHERE album_id = a.id) as track_count
     FROM albums a WHERE a.name LIKE ? ORDER BY track_count DESC LIMIT 50`,
    term,
  )
  return c.json(rows ?? [])
})

// ── Cluster detection ──

a.get('/clusters', async (c) => {
  const db = DB(c.env)
  const type = c.req.query('type') || 'artist'
  const minSize = Math.max(2, Number(c.req.query('min_size')) || 2)
  const minTracks = Math.max(0, Number(c.req.query('min_tracks')) || 1)
  const showLonely = c.req.query('show_lonely') === 'true'

  let entities: Array<Record<string, unknown>>
  if (type === 'artist') {
    const { results: rows } = await db.all(
      `SELECT a.id, a.name,
              (SELECT COUNT(*) FROM tracks WHERE artist_id = a.id) AS track_count,
              (SELECT COUNT(*) FROM albums WHERE artist_id = a.id) AS album_count
       FROM artists a ORDER BY a.name`,
    )
    entities = (rows ?? []) as unknown as Array<Record<string, unknown>>
  } else {
    const { results: rows } = await db.all(
      `SELECT al.id, al.name, al.artist_id,
              COALESCE(ar.name, '(orphaned)') AS artist_name,
              (SELECT COUNT(*) FROM tracks WHERE album_id = al.id) AS track_count,
              0 AS album_count
       FROM albums al
       LEFT JOIN artists ar ON al.artist_id = ar.id
       ORDER BY ar.name, al.name`,
    )
    entities = (rows ?? []) as unknown as Array<Record<string, unknown>>
  }

  // Group by base name
  const groups = new Map<string, Array<Record<string, unknown>>>()
  for (const ent of entities) {
    const base = baseName(ent.name as string)
    const key = type === 'album' ? `${ent.artist_id}||${base}` : base
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(ent)
  }

  const seenIds = new Set<number>()
  const clusters: Array<{
    base_name: string; total_tracks: number; variant_count: number
    variants: Array<{ id: number; name: string; tracks: number; albums: number }>
  }> = []

  for (const [key, variants] of groups.entries()) {
    if (variants.length < minSize) continue
    const totalTracks = variants.reduce((s, v) => s + (v.track_count as number), 0)
    if (totalTracks < minTracks) continue

    const baseNameRaw = key.includes('||') ? key.split('||')[1] : key
    const artistForCluster = type === 'album' ? (variants[0].artist_name as string ?? '') : ''

    const clusterVariants: Array<{ id: number; name: string; tracks: number; albums: number }> = []
    for (const v of variants) {
      const sim = trigramSimilarity(baseNameRaw, v.name as string)
      const normalized = (v.name as string).toLowerCase().trim().replace(/[^\w\s]/g, ' ').replace(/\s+/g, ' ').trim()
      if (sim > 0.3 || normalized.includes(baseNameRaw)) {
        if (!seenIds.has(v.id as number)) {
          const vData: { id: number; name: string; tracks: number; albums: number; artist_name?: string } = {
            id: v.id as number,
            name: v.name as string,
            tracks: v.track_count as number,
            albums: v.album_count as number,
          }
          if (type === 'album') vData.artist_name = v.artist_name as string
          clusterVariants.push(vData)
          seenIds.add(v.id as number)
        }
      }
    }

    if (clusterVariants.length >= minSize) {
      clusterVariants.sort((a, b) => b.tracks - a.tracks)
      const total = clusterVariants.reduce((s, v) => s + v.tracks, 0)
      let displayName = baseNameRaw.replace(/\b\w/g, (c) => c.toUpperCase()).trim()
      if (artistForCluster) displayName = `${displayName} (${artistForCluster})`
      clusters.push({ base_name: displayName, total_tracks: total, variant_count: clusterVariants.length, variants: clusterVariants })
    }
  }

  // Secondary merge: absorb satellites where one base is a word-subset of another
  const mergedKeys = new Set<number>()
  for (let i = 0; i < clusters.length; i++) {
    if (mergedKeys.has(i)) continue
    const bigWords = new Set(clusters[i].base_name.toLowerCase().split(/\s+/))
    for (let j = 0; j < clusters.length; j++) {
      if (i === j || mergedKeys.has(j)) continue
      if (clusters[j].base_name.length < 4) continue
      const smallWords = new Set(clusters[j].base_name.toLowerCase().split(/\s+/))
      if ([...smallWords].every((w) => bigWords.has(w))) {
        clusters[i].variants.push(...clusters[j].variants)
        clusters[i].variants.sort((a, b) => b.tracks - a.tracks)
        clusters[i].total_tracks += clusters[j].total_tracks
        clusters[i].variant_count = clusters[i].variants.length
        mergedKeys.add(j)
      }
    }
  }

  let filteredClusters = clusters.filter((_, i) => !mergedKeys.has(i))
  filteredClusters.sort((a, b) => b.total_tracks - a.total_tracks)

  // Filter ignored clusters
  const { results: ignoredRows } = await db.all<{ entity_ids: string }>(
    'SELECT entity_ids FROM ignored_clusters WHERE entity_type = ?', type,
  )
  const ignoredSets = new Set<string>()
  for (const row of ignoredRows ?? []) {
    const ids = (row.entity_ids as unknown as string).split(',').map(Number).filter((n) => !Number.isNaN(n)).sort((a, b) => a - b)
    if (ids.length > 0) ignoredSets.add(JSON.stringify(ids))
  }

  filteredClusters = filteredClusters.filter((c) => {
    const ids = JSON.stringify(c.variants.map((v) => v.id).sort((a, b) => a - b))
    return !ignoredSets.has(ids)
  })

  // Lonely variants
  let lonely: Array<{ id: number; name: string; tracks: number; albums: number }> = []
  if (showLonely) {
    const collabSeps = [' & ', ' + ', ' w/', ' feat ', ' vs ', ' / ']
    for (const ent of entities) {
      if (seenIds.has(ent.id as number)) continue
      const nameLower = (ent.name as string).toLowerCase()
      if (!collabSeps.some((s) => nameLower.includes(s))) continue
      if ((nameLower.startsWith('the ') || nameLower.startsWith('a ')) && (ent.track_count as number) >= 5) continue
      if ((ent.track_count as number) >= 15) continue
      lonely.push({
        id: ent.id as number,
        name: ent.name as string,
        tracks: ent.track_count as number,
        albums: ent.album_count as number,
      })
    }
    lonely.sort((a, b) => b.tracks - a.tracks)
  }

  return c.json({ clusters: filteredClusters, lonely })
})

// ── Merge preview ──

a.post('/merge/preview', async (c) => {
  const body = await c.req.json<{ type?: string; source_ids?: string; target_id?: number }>()
  return executeMerge(c, body.type || 'artist', parseIds(body.source_ids ?? ''), body.target_id ?? 0, true)
})

// ── Merge ──

a.post('/merge', async (c) => {
  const body = await c.req.json<{ type?: string; source_ids?: string; target_id?: number }>()
  return executeMerge(c, body.type || 'artist', parseIds(body.source_ids ?? ''), body.target_id ?? 0, false)
})

async function executeMerge(
  c: Context<{ Bindings: Env }>,
  entityType: string,
  sourceIds: number[],
  targetId: number,
  preview: boolean,
) {
  if (sourceIds.length === 0 || !targetId) {
    return c.json({ error: 'source_ids and target_id are required' }, 400)
  }

  const db = DB(c.env)

  // Ensure migration_log table exists
  await db.exec(`CREATE TABLE IF NOT EXISTS migration_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    old_name TEXT NOT NULL,
    new_name TEXT NOT NULL,
    affected_count INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
  )`)

  const tableName = entityType === 'artist' ? 'artists' : 'albums'
  const targetRow = await db.one<{ name: string }>(
    `SELECT name FROM ${tableName} WHERE id = ?`, targetId,
  )
  if (!targetRow) return c.json({ error: `Target ${entityType} id=${targetId} not found` }, 404)

  const targetName = targetRow.name
  let totalAffectedTracks = 0
  let totalAffectedAlbums = 0
  const details: Array<{ source_id: number; source_name: string; affected_tracks: number; affected_albums: number }> = []

  // Wrap in a transaction for non-preview
  if (!preview) await db.exec('BEGIN TRANSACTION')

  try {
    for (const sourceId of sourceIds) {
      const sourceRow = await db.one<{ name: string }>(
        `SELECT name FROM ${tableName} WHERE id = ?`, sourceId,
      )
      if (!sourceRow) continue

      const sourceName = sourceRow.name

      if (entityType === 'artist') {
        const trackCount = (await db.one<{ c: number }>('SELECT COUNT(*) as c FROM tracks WHERE artist_id = ?', sourceId))?.c ?? 0
        const albumCount = (await db.one<{ c: number }>('SELECT COUNT(*) as c FROM albums WHERE artist_id = ?', sourceId))?.c ?? 0

        if (preview) {
          totalAffectedTracks += trackCount
          totalAffectedAlbums += albumCount
        } else {
          // Merge albums that collide by name
          const { results: conflicts } = await db.all<{ source_album_id: number; target_album_id: number }>(
            `SELECT s.id AS source_album_id, t.id AS target_album_id
             FROM albums s JOIN albums t ON s.name = t.name
             WHERE s.artist_id = ? AND t.artist_id = ?`,
            sourceId, targetId,
          )
          for (const c of conflicts ?? []) {
            await db.run('UPDATE tracks SET album_id = ? WHERE album_id = ?', c.target_album_id, c.source_album_id)
            await db.run('DELETE FROM albums WHERE id = ?', c.source_album_id)
          }
          await db.run('UPDATE albums SET artist_id = ? WHERE artist_id = ?', targetId, sourceId)
          await db.run('UPDATE tracks SET artist_id = ? WHERE artist_id = ?', targetId, sourceId)
          await db.run("UPDATE tracks SET artist = ? WHERE artist_id = ? AND artist != ?", targetName, targetId, targetName)
          await db.run('DELETE FROM artists WHERE id = ?', sourceId)
          await db.run(
            'INSERT INTO migration_log (entity_type, old_name, new_name, affected_count) VALUES (?, ?, ?, ?)',
            'artist', sourceName, targetName, trackCount,
          )
          totalAffectedTracks += trackCount
          totalAffectedAlbums += albumCount
        }
      } else {
        const trackCount = (await db.one<{ c: number }>('SELECT COUNT(*) as c FROM tracks WHERE album_id = ?', sourceId))?.c ?? 0

        if (preview) {
          totalAffectedTracks += trackCount
          totalAffectedAlbums += 1
        } else {
          await db.run('UPDATE tracks SET album_id = ? WHERE album_id = ?', targetId, sourceId)
          await db.run("UPDATE tracks SET album = ? WHERE album_id = ? AND album != ?", targetName, targetId, targetName)
          await db.run('DELETE FROM albums WHERE id = ?', sourceId)
          await db.run(
            'INSERT INTO migration_log (entity_type, old_name, new_name, affected_count) VALUES (?, ?, ?, ?)',
            'album', sourceName, targetName, trackCount,
          )
          totalAffectedTracks += trackCount
          totalAffectedAlbums += 1
        }
      }

      const tCount = entityType === 'artist'
        ? (await db.one<{ c: number }>('SELECT COUNT(*) as c FROM tracks WHERE artist_id = ?', sourceId))?.c ?? 0
        : (await db.one<{ c: number }>('SELECT COUNT(*) as c FROM tracks WHERE album_id = ?', sourceId))?.c ?? 0
      const aCount = entityType === 'artist'
        ? (await db.one<{ c: number }>('SELECT COUNT(*) as c FROM albums WHERE artist_id = ?', sourceId))?.c ?? 0
        : 0
      details.push({ source_id: sourceId, source_name: sourceName, affected_tracks: tCount, affected_albums: aCount })
    }

    if (!preview) await db.exec('COMMIT')
  } catch (err) {
    if (!preview) await db.exec('ROLLBACK')
    throw err
  }

  if (preview) {
    return c.json({
      preview: true, target_id: targetId, target_name: targetName,
      total_affected_tracks: totalAffectedTracks,
      total_affected_albums: totalAffectedAlbums,
      details,
    })
  }

  return c.json({
    status: 'success', target_id: targetId, target_name: targetName,
    total_affected_tracks: totalAffectedTracks,
    total_affected_albums: totalAffectedAlbums,
    details,
  })
}

// ── Reassign (legacy) ──

a.post('/reassign', async (c) => {
  const body = await c.req.json<{ type?: string; source_id?: number; target_id?: number }>()
  return executeMerge(c, body.type || 'artist', [body.source_id ?? 0], body.target_id ?? 0, false)
})

// ── Corrections ──

a.post('/correction', async (c) => {
  const db = DB(c.env)
  const body = await c.req.json<{
    type?: string; track_id?: number | null; episode_id?: number
    original_data?: Record<string, unknown> | null; corrected_data?: Record<string, unknown>
  }>()

  if (!body.episode_id || !body.corrected_data) {
    return c.json({ error: 'episode_id and corrected_data are required' }, 400)
  }

  await db.exec(`CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER,
    episode_id INTEGER,
    type TEXT NOT NULL,
    original_data TEXT,
    corrected_data TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )`)

  await db.run(
    'INSERT INTO corrections (track_id, episode_id, type, original_data, corrected_data) VALUES (?, ?, ?, ?, ?)',
    body.track_id ?? null,
    body.episode_id,
    body.type || 'TRACK_EDIT',
    body.original_data ? JSON.stringify(body.original_data) : null,
    JSON.stringify(body.corrected_data),
  )

  // Also apply to main tracks table
  if ((body.type || 'TRACK_EDIT') === 'TRACK_EDIT') {
    if (body.corrected_data) {
      const fields: string[] = []
      const params: unknown[] = []
      for (const col of ['title', 'artist', 'album'] as const) {
        if (body.corrected_data[col] !== undefined) {
          fields.push(`${col} = ?`)
          params.push(body.corrected_data[col])
        }
      }
      if (fields.length > 0 && body.track_id) {
        params.push(body.track_id)
        await db.run(`UPDATE tracks SET ${fields.join(', ')} WHERE id = ?`, ...params)
      }

      // Propagate to similar rows
      const orig = body.original_data
      const corr = body.corrected_data
      if (orig && corr) {
        const album = (orig.album as string) ?? (corr.album as string) ?? ''
        const origArtist = orig.artist as string
        const newArtist = corr.artist as string
        const origTitle = orig.title as string
        const newTitle = corr.title as string
        const origAlbum = orig.album as string
        const newAlbum = corr.album as string

        if (newAlbum && origAlbum && newAlbum !== origAlbum) {
          await db.run('UPDATE tracks SET album = ? WHERE album = ? AND artist = ?', newAlbum, origAlbum, origArtist || newArtist)
        }
        if (newTitle && origTitle && newTitle !== origTitle) {
          await db.run('UPDATE tracks SET title = ? WHERE title = ? AND album = ? AND artist = ?', newTitle, origTitle, album, origArtist || newArtist)
        }
        if (newArtist && origArtist && newArtist !== origArtist) {
          await db.run('UPDATE tracks SET artist = ? WHERE artist = ? AND album = ?', newArtist, origArtist, album)
        }
      }
    }
  }

  return c.json({ status: 'saved' })
})

// ── List corrections ──

a.get('/corrections', async (c) => {
  const db = DB(c.env)
  const episode = Number(c.req.query('episode')) || 0
  const type = c.req.query('type') || ''

  await db.exec(`CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER,
    episode_id INTEGER,
    type TEXT NOT NULL,
    original_data TEXT,
    corrected_data TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )`)

  const conditions: string[] = ['1=1']
  const params: unknown[] = []
  if (episode) { conditions.push('episode_id = ?'); params.push(episode) }
  if (type) { conditions.push('type = ?'); params.push(type) }

  const { results: rows } = await db.all(
    `SELECT id, track_id, episode_id, type, original_data, corrected_data, created_at
     FROM corrections WHERE ${conditions.join(' AND ')} ORDER BY created_at DESC`,
    ...params,
  )

  const items = (rows ?? []).map((r) => {
    const row = r as unknown as Record<string, unknown>
    let originalData: unknown = null
    let correctedData: unknown = null
    try { originalData = row.original_data ? JSON.parse(row.original_data as string) : null } catch { /* skip */ }
    try { correctedData = row.corrected_data ? JSON.parse(row.corrected_data as string) : null } catch { /* skip */ }
    return {
      id: row.id,
      track_id: row.track_id,
      episode_id: row.episode_id,
      type: row.type,
      original_data: originalData,
      corrected_data: correctedData,
      created_at: row.created_at,
    }
  })

  return c.json({ items, total: items.length })
})

// ── Revert correction ──

a.post('/corrections/:correctionId/revert', async (c) => {
  const db = DB(c.env)
  const correctionId = Number(c.req.param('correctionId'))

  await db.exec(`CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER,
    episode_id INTEGER,
    type TEXT NOT NULL,
    original_data TEXT,
    corrected_data TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )`)

  const result = await db.run('DELETE FROM corrections WHERE id = ?', correctionId)
  if (result.meta.changes === 0) {
    return c.json({ error: 'Correction not found' }, 404)
  }
  return c.json({ status: 'ok', deleted: correctionId })
})

// ── Rename track ──

a.post('/rename-track', async (c) => {
  const db = DB(c.env)
  const body = await c.req.json<{ album?: string; artist?: string; old_title?: string; new_title?: string }>()

  if (!body.album || !body.artist || !body.old_title || !body.new_title) {
    return c.json({ error: 'album, artist, old_title, and new_title are required' }, 400)
  }

  const result = await db.run(
    'UPDATE tracks SET title = ? WHERE title = ? AND album = ? AND artist = ?',
    body.new_title, body.old_title, body.album, body.artist,
  )

  return c.json({ status: 'ok', renamed: result.meta.changes })
})

// ── Rename artist ──

a.post('/rename-artist', async (c) => {
  const db = DB(c.env)
  const body = await c.req.json<{ old_name?: string; new_name?: string }>()
  if (!body.old_name || !body.new_name) {
    return c.json({ error: 'old_name and new_name are required' }, 400)
  }

  const oldArtist = await db.one<{ id: number }>('SELECT id FROM artists WHERE name = ?', body.old_name)
  if (!oldArtist) return c.json({ error: `Artist '${body.old_name}' not found` }, 404)

  const targetArtist = await db.one<{ id: number }>('SELECT id FROM artists WHERE name = ?', body.new_name)

  if (targetArtist) {
    await db.run('UPDATE albums SET artist_id = ? WHERE artist_id = ?', targetArtist.id, oldArtist.id)
    await db.run('UPDATE tracks SET artist_id = ? WHERE artist_id = ?', targetArtist.id, oldArtist.id)
    await db.run('DELETE FROM artists WHERE id = ?', oldArtist.id)
  } else {
    await db.run('UPDATE artists SET name = ? WHERE id = ?', body.new_name, oldArtist.id)
  }

  const result = await db.run('UPDATE tracks SET artist = ? WHERE artist = ?', body.new_name, body.old_name)

  return c.json({ status: 'ok', artists_updated: 1, tracks_updated: result.meta.changes })
})

// ── Edit artist (MBID correction / rename, with MusicBrainz + Last.fm
//    enrichment) — TypeScript port of web/api/routers/admin.py's
//    edit_artist(), scoped to what this D1-backed Worker needs. ──

interface CachedEnrichment {
  mbid: string | null
  canonical_name: string | null
  country: string | null
  formed_year: number | null
  genres: string
  tags: string
  bio_summary: string | null
  wikipedia_url: string | null
  lastfm_tags: string
  lastfm_bio: string | null
  lastfm_listeners: number | null
  lastfm_playcount: number | null
  lastfm_url: string | null
}

a.post('/edit-artist', async (c) => {
  const db = DB(c.env)
  const body = await c.req.json<{ name?: string; mbid?: string | null; new_name?: string | null }>()
  const name = body.name || ''
  const mbid = body.mbid || null
  if (!name) return c.json({ error: 'name is required' }, 400)

  // Reuse cached enrichment data unless the caller supplied an mbid that
  // differs from what's cached — that's a deliberate correction and should
  // force a refetch, mirroring the override handling in
  // get_artist_enrichment() (web/api/services/enrichment.py).
  const cached = await db.one<CachedEnrichment>('SELECT * FROM artist_enrichment WHERE artist_name = ?', name)

  const fetched = cached && (!mbid || mbid === cached.mbid)
    ? {
        mbid: cached.mbid, canonical_name: cached.canonical_name, country: cached.country,
        formed_year: cached.formed_year,
        genres: JSON.parse(cached.genres || '[]') as string[],
        tags: JSON.parse(cached.tags || '[]') as string[],
        bio_summary: cached.bio_summary, wikipedia_url: cached.wikipedia_url,
        lastfm_tags: JSON.parse(cached.lastfm_tags || '[]') as string[],
        lastfm_bio: cached.lastfm_bio, lastfm_listeners: cached.lastfm_listeners,
        lastfm_playcount: cached.lastfm_playcount, lastfm_url: cached.lastfm_url,
      }
    : await fetchArtistEnrichment(name, mbid)

  const newName = body.new_name || fetched.canonical_name || null
  const resolvedName = newName || name

  const oldRow = await db.one<{ id: number }>('SELECT id FROM artists WHERE name = ?', name)
  if (oldRow) {
    const oldId = oldRow.id
    const target = resolvedName !== name
      ? await db.one<{ id: number }>('SELECT id FROM artists WHERE name = ?', resolvedName)
      : null

    if (target && target.id !== oldId) {
      // Merge into existing canonical artist
      const targetId = target.id
      await db.run('UPDATE tracks SET artist_id = ?, artist = ? WHERE artist_id = ?', targetId, resolvedName, oldId)
      const { results: oldAlbums } = await db.all<{ id: number; name: string }>(
        'SELECT id, name FROM albums WHERE artist_id = ?', oldId,
      )
      for (const alb of oldAlbums ?? []) {
        const collision = await db.one<{ id: number }>(
          'SELECT id FROM albums WHERE artist_id = ? AND name = ?', targetId, alb.name,
        )
        if (collision) {
          await db.run('UPDATE tracks SET album_id = ? WHERE album_id = ?', collision.id, alb.id)
          await db.run('DELETE FROM albums WHERE id = ?', alb.id)
        } else {
          await db.run('UPDATE albums SET artist_id = ? WHERE id = ?', targetId, alb.id)
        }
      }
      await db.run('DELETE FROM artists WHERE id = ?', oldId)
      await db.run('DELETE FROM artist_enrichment WHERE artist_name = ?', name)
    } else if (resolvedName !== name) {
      await db.run('UPDATE artists SET name = ? WHERE id = ?', resolvedName, oldId)
      await db.run('UPDATE tracks SET artist = ? WHERE artist = ?', resolvedName, name)
      await db.run('DELETE FROM artist_enrichment WHERE artist_name = ?', name)
    }
  }

  // Write the mbid to artists.mbid for merge detection
  if (mbid) {
    const artistRow = await db.one<{ id: number }>('SELECT id FROM artists WHERE name = ?', resolvedName)
    if (artistRow) {
      await db.run('UPDATE artists SET mbid = ? WHERE id = ?', mbid, artistRow.id)
    }
  }

  // Write/update enrichment data keyed by the resolved (final) name
  await db.run(
    `INSERT INTO artist_enrichment
        (artist_name, mbid, canonical_name, country, formed_year, genres, tags, bio_summary, wikipedia_url, last_fetched, fetch_count, lastfm_tags, lastfm_bio, lastfm_listeners, lastfm_playcount, lastfm_url)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), 1, ?, ?, ?, ?, ?)
     ON CONFLICT(artist_name) DO UPDATE SET
        mbid = excluded.mbid, canonical_name = excluded.canonical_name, country = excluded.country,
        formed_year = excluded.formed_year, genres = excluded.genres, tags = excluded.tags,
        bio_summary = excluded.bio_summary, wikipedia_url = excluded.wikipedia_url,
        last_fetched = datetime('now'), fetch_count = fetch_count + 1,
        lastfm_tags = excluded.lastfm_tags, lastfm_bio = excluded.lastfm_bio,
        lastfm_listeners = excluded.lastfm_listeners, lastfm_playcount = excluded.lastfm_playcount,
        lastfm_url = excluded.lastfm_url`,
    resolvedName, fetched.mbid, fetched.canonical_name, fetched.country, fetched.formed_year,
    JSON.stringify(fetched.genres), JSON.stringify(fetched.tags), fetched.bio_summary, fetched.wikipedia_url,
    JSON.stringify(fetched.lastfm_tags), fetched.lastfm_bio, fetched.lastfm_listeners, fetched.lastfm_playcount, fetched.lastfm_url,
  )

  return c.json({
    status: 'ok',
    name: resolvedName,
    mbid,
    canonical_name: fetched.canonical_name,
    country: fetched.country,
    formed_year: fetched.formed_year,
    bio_summary: fetched.bio_summary,
  })
})

// ── Rename album ──

a.post('/rename-album', async (c) => {
  const db = DB(c.env)
  const body = await c.req.json<{ old_name?: string; new_name?: string; artist?: string }>()
  if (!body.old_name || !body.new_name || !body.artist) {
    return c.json({ error: 'old_name, new_name, and artist are required' }, 400)
  }

  const oldAlbum = await db.one<{ id: number; artist_id: number }>(
    'SELECT a.id, a.artist_id FROM albums a WHERE a.name = ? AND a.artist_id = (SELECT id FROM artists WHERE name = ?)',
    body.old_name, body.artist,
  )
  if (!oldAlbum) return c.json({ error: `Album '${body.old_name}' by '${body.artist}' not found` }, 404)

  const targetAlbum = await db.one<{ id: number }>(
    'SELECT id FROM albums WHERE name = ? AND artist_id = ?',
    body.new_name, oldAlbum.artist_id,
  )

  if (targetAlbum) {
    await db.run('UPDATE tracks SET album_id = ? WHERE album_id = ?', targetAlbum.id, oldAlbum.id)
    await db.run('DELETE FROM albums WHERE id = ?', oldAlbum.id)
  } else {
    await db.run('UPDATE albums SET name = ? WHERE id = ?', body.new_name, oldAlbum.id)
  }

  const result = await db.run(
    'UPDATE tracks SET album = ? WHERE album = ? AND artist = ?',
    body.new_name, body.old_name, body.artist,
  )

  return c.json({ status: 'ok', albums_updated: 1, tracks_updated: result.meta.changes })
})

// ── Apply all corrections ──

a.post('/corrections/apply-all', async (c) => {
  const db = DB(c.env)
  const { results: rows } = await db.all(
    "SELECT * FROM corrections WHERE type = 'TRACK_EDIT' ORDER BY id",
  )

  let applied = 0
  for (const row of rows ?? []) {
    const r = row as unknown as Record<string, unknown>
    let corrected: Record<string, unknown>
    let original: Record<string, unknown>
    try {
      corrected = JSON.parse(r.corrected_data as string)
      original = r.original_data ? JSON.parse(r.original_data as string) : {}
    } catch { continue }

    const newTitle = corrected.title as string | undefined
    const origTitle = original.title as string | undefined
    const origArtist = original.artist as string | undefined
    const newArtist = corrected.artist as string | undefined
    const album = (original.album as string) || (corrected.album as string) || ''
    const trackId = r.track_id as number | null

    if (trackId) {
      const fields: string[] = []
      const params: unknown[] = []
      for (const col of ['title', 'artist', 'album'] as const) {
        if (corrected[col] !== undefined) {
          fields.push(`${col} = ?`)
          params.push(corrected[col])
        }
      }
      if (fields.length > 0) {
        params.push(trackId)
        await db.run(`UPDATE tracks SET ${fields.join(', ')} WHERE id = ?`, ...params)
      }
    }

    const origAlbum = original.album as string | undefined
    const newAlbum = corrected.album as string | undefined
    if (newAlbum && origAlbum && newAlbum !== origAlbum) {
      await db.run('UPDATE tracks SET album = ? WHERE album = ? AND artist = ?', newAlbum, origAlbum, origArtist || newArtist)
    }
    if (newTitle && origTitle && newTitle !== origTitle) {
      await db.run('UPDATE tracks SET title = ? WHERE title = ? AND album = ? AND artist = ?', newTitle, origTitle, album, origArtist || newArtist)
    }
    if (newArtist && origArtist && newArtist !== origArtist) {
      await db.run('UPDATE tracks SET artist = ? WHERE artist = ? AND album = ?', newArtist, origArtist, album)
    }
    applied++
  }

  return c.json({ status: 'ok', applied })
})

// ── Track browser ──

a.get('/tracks', async (c) => {
  const db = DB(c.env)
  const q = c.req.query('q') || ''
  const artist = c.req.query('artist') || ''
  const album = c.req.query('album') || ''
  const limit = Math.min(500, Math.max(1, Number(c.req.query('limit')) || 100))

  const conditions: string[] = []
  const params: unknown[] = []

  if (q) {
    conditions.push('(t.title LIKE ? OR t.artist LIKE ? OR t.album LIKE ?)')
    params.push(`%${q}%`, `%${q}%`, `%${q}%`)
  }
  if (artist) { conditions.push('t.artist LIKE ?'); params.push(`%${artist}%`) }
  if (album) { conditions.push('t.album LIKE ?'); params.push(`%${album}%`) }

  const where = conditions.length > 0 ? conditions.join(' AND ') : '1'

  const { results: rows } = await db.all(
    `SELECT t.title, t.artist, t.album,
            COUNT(*) as total_plays,
            COUNT(DISTINCT t.episode_id) as episode_count,
            GROUP_CONCAT(DISTINCT e.broadcast || '|' || e.date) as episodes
     FROM tracks t
     JOIN episodes e ON e.id = t.episode_id
     WHERE ${where}
     GROUP BY t.title, t.artist, t.album
     ORDER BY total_plays DESC
     LIMIT ?`,
    ...params, limit,
  )

  const items = (rows ?? []).map((r) => {
    const row = r as unknown as Record<string, unknown>
    const epList: Array<{ broadcast: number | null; date: string | null }> = []
    if (row.episodes) {
      for (const part of (row.episodes as string).split(',')) {
        const [broadcast, date] = part.split('|')
        epList.push({
          broadcast: broadcast && broadcast !== 'None' ? Number(broadcast) : null,
          date: date ?? null,
        })
      }
    }
    return {
      title: row.title,
      artist: row.artist,
      album: (row.album as string) || '',
      total_plays: row.total_plays,
      episode_count: row.episode_count,
      episodes: epList,
    }
  })

  return c.json({ items, total: items.length })
})

// ── Ignored clusters ──

a.post('/clusters/ignore', async (c) => {
  const db = DB(c.env)
  const body = await c.req.json<{ type?: string; entity_ids?: string; display_name?: string }>()

  const ids = parseIds(body.entity_ids ?? '')
  if (ids.length < 2) return c.json({ error: 'At least 2 entity_ids required' }, 400)

  await db.exec(`CREATE TABLE IF NOT EXISTS ignored_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_ids TEXT NOT NULL,
    display_name TEXT,
    created_at TEXT DEFAULT (datetime('now'))
  )`)

  await db.run(
    'INSERT INTO ignored_clusters (entity_type, entity_ids, display_name) VALUES (?, ?, ?)',
    body.type || 'artist', ids.join(','), body.display_name ?? '',
  )

  return c.json({ status: 'ignored', entity_ids: ids, display_name: body.display_name ?? '' })
})

a.get('/clusters/ignored', async (c) => {
  const db = DB(c.env)
  const type = c.req.query('type') || 'artist'

  await db.exec(`CREATE TABLE IF NOT EXISTS ignored_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_ids TEXT NOT NULL,
    display_name TEXT,
    created_at TEXT DEFAULT (datetime('now'))
  )`)

  const { results: rows } = await db.all(
    `SELECT id, entity_type, entity_ids, display_name, created_at
     FROM ignored_clusters WHERE entity_type = ? ORDER BY created_at DESC`,
    type,
  )

  return c.json({
    items: (rows ?? []).map((r) => {
      const row = r as unknown as Record<string, unknown>
      return {
        id: row.id,
        entity_type: row.entity_type,
        entity_ids: (row.entity_ids as string).split(',').map(Number).filter((n) => !Number.isNaN(n)),
        display_name: row.display_name,
        created_at: row.created_at,
      }
    }),
  })
})

a.delete('/clusters/ignore/:ignoreId', async (c) => {
  const db = DB(c.env)
  const ignoreId = Number(c.req.param('ignoreId'))

  const result = await db.run('DELETE FROM ignored_clusters WHERE id = ?', ignoreId)
  if (result.meta.changes === 0) return c.json({ error: 'Ignored cluster not found' }, 404)

  return c.json({ status: 'ok', deleted: ignoreId })
})

// ── Tracks by ID ──

a.get('/tracks-by-id/:entityType/:entityId', async (c) => {
  const db = DB(c.env)
  const entityType = c.req.param('entityType') // 'artist' or 'album'
  const entityId = Number(c.req.param('entityId'))

  if (Number.isNaN(entityId)) return c.json({ error: 'Invalid ID' }, 400)

  if (entityType === 'artist') {
    const { results: rows } = await db.all(
      `SELECT t.id, t.title, art.name as artist, alb.name as album
       FROM tracks t JOIN artists art ON t.artist_id = art.id
       LEFT JOIN albums alb ON t.album_id = alb.id
       WHERE t.artist_id = ?`,
      entityId,
    )
    return c.json(rows ?? [])
  }

  const { results: rows } = await db.all(
    `SELECT t.id, t.title, art.name as artist, alb.name as album
     FROM tracks t JOIN artists art ON t.artist_id = art.id
     JOIN albums alb ON t.album_id = alb.id
     WHERE t.album_id = ?`,
    entityId,
  )
  return c.json(rows ?? [])
})
