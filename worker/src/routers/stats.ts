/**
 * Dashboard / stats endpoints — overview, top-*, heatmap, countries, genres, decades.
 */

import { Hono } from 'hono'
import type { Env } from '../db'
import { DB } from '../db'

export const statsRouter = new Hono<{ Bindings: Env }>()

// ISO 3166-1 alpha-2 → numeric for world map
const ISO_NUMERIC: Record<string, number> = {
  AF:4,AX:248,AL:8,DZ:12,AS:16,AD:20,AO:24,AI:660,AQ:10,AG:28,AR:32,AM:51,AW:533,AU:36,
  AT:40,AZ:31,BS:44,BH:48,BD:50,BB:52,BY:112,BE:56,BZ:84,BJ:204,BM:60,BT:64,BO:68,
  BQ:535,BA:70,BW:72,BV:74,BR:76,IO:86,BN:96,BG:100,BF:854,BI:108,CV:132,KH:116,CM:120,
  CA:124,KY:136,CF:140,TD:148,CL:152,CN:156,CX:162,CC:166,CO:170,KM:174,CG:178,CD:180,
  CK:184,CR:188,HR:191,CU:192,CW:531,CY:196,CZ:203,DK:208,DJ:262,DM:212,DO:214,EC:218,
  EG:818,SV:222,GQ:226,ER:232,EE:233,SZ:748,ET:231,FK:238,FO:234,FJ:242,FI:246,FR:250,
  GF:254,PF:258,TF:260,GA:266,GM:270,GE:268,DE:276,GH:288,GI:292,GR:300,GL:304,GD:308,
  GP:312,GU:316,GT:320,GG:831,GN:324,GW:624,GY:328,HT:332,HM:334,VA:336,HN:340,HK:344,
  HU:348,IS:352,IN:356,ID:360,IR:364,IQ:368,IE:372,IM:833,IL:376,IT:380,JM:388,JP:392,
  JE:832,JO:400,KZ:398,KE:404,KI:296,KP:408,KR:410,KW:414,KG:417,LA:418,LV:428,LB:422,
  LS:426,LR:430,LY:434,LI:438,LT:440,LU:442,MO:446,MG:450,MW:454,MY:458,MV:462,ML:466,
  MT:470,MH:584,MQ:474,MR:478,MU:480,YT:175,MX:484,FM:583,MD:498,MC:492,MN:496,ME:499,
  MS:500,MA:504,MZ:508,MM:104,NA:516,NR:520,NP:524,NL:528,NC:540,NZ:554,NI:558,NE:562,
  NG:566,NU:570,NF:574,MK:807,MP:580,NO:578,OM:512,PK:586,PW:585,PS:275,PA:591,PG:598,
  PY:600,PE:604,PH:608,PN:612,PL:616,PT:620,PR:630,QA:634,RE:638,RO:642,RU:643,RW:646,
  BL:652,SH:654,KN:659,LC:662,MF:663,PM:666,VC:670,WS:882,SM:674,ST:678,SA:682,SN:686,
  RS:688,SC:690,SL:694,SG:702,SX:534,SK:703,SI:705,SB:90,SO:706,ZA:710,GS:239,SS:728,
  ES:724,LK:144,SD:729,SR:740,SJ:744,SE:752,CH:756,SY:760,TW:158,TJ:762,TZ:834,TH:764,
  TL:626,TG:768,TK:772,TO:776,TT:780,TN:788,TR:792,TM:795,TC:796,TV:798,UG:800,UA:804,
  AE:784,GB:826,US:840,UM:581,UY:858,UZ:860,VU:548,VE:862,VN:704,VG:92,VI:850,WF:876,
  EH:732,YE:887,ZM:894,ZW:716,
}

// ── Overview ──

statsRouter.get('/overview', async (c) => {
  const db = DB(c.env)
  const epCount = (await db.one<{ c: number }>('SELECT COUNT(*) as c FROM episodes'))?.c ?? 0
  const trCount = (await db.one<{ c: number }>('SELECT COUNT(*) as c FROM tracks'))?.c ?? 0
  const artCount = (await db.one<{ c: number }>('SELECT COUNT(DISTINCT artist) as c FROM tracks'))?.c ?? 0
  const linkCount = (await db.one<{ c: number }>('SELECT COUNT(*) as c FROM links'))?.c ?? 0

  const range = await db.one<{ first: string | null; last: string | null }>(
    'SELECT MIN(date) as first, MAX(date) as last FROM episodes',
  )

  return c.json({
    episodes: epCount,
    tracks: trCount,
    unique_artists: artCount,
    bandcamp_links: linkCount,
    date_range: range?.first && range?.last ? [range.first, range.last] : null,
  })
})

// ── Top artists ──

statsRouter.get('/top-artists', async (c) => {
  const db = DB(c.env)
  const limit = Math.min(100, Math.max(1, Number(c.req.query('limit')) || 10))
  const metric = c.req.query('metric') || 'plays'

  if (metric === 'coverage') {
    const totalEps = (await db.one<{ c: number }>('SELECT COUNT(*) as c FROM episodes'))?.c ?? 1
    const { results: rows } = await db.all<{ artist: string; plays: number; episodes: number }>(
      `SELECT artist, COUNT(*) as plays, COUNT(DISTINCT episode_id) as episodes
       FROM tracks GROUP BY artist ORDER BY episodes DESC LIMIT ?`,
      limit,
    )
    return c.json((rows ?? []).map((r) => ({
      name: r.artist,
      value: r.episodes,
      extra: { plays: r.plays, pct: Math.round((r.episodes / totalEps) * 1000) / 10 },
    })))
  }

  const { results: rows } = await db.all<{ artist: string; plays: number; episodes: number }>(
    `SELECT artist, COUNT(*) as plays, COUNT(DISTINCT episode_id) as episodes
     FROM tracks GROUP BY artist ORDER BY plays DESC LIMIT ?`,
    limit,
  )
  return c.json((rows ?? []).map((r) => ({
    name: r.artist,
    value: r.plays,
    extra: { episodes: r.episodes },
  })))
})

// ── Top albums ──

statsRouter.get('/top-albums', async (c) => {
  const db = DB(c.env)
  const limit = Math.min(100, Math.max(1, Number(c.req.query('limit')) || 10))

  const { results: rows } = await db.all<{ album: string; artist: string; plays: number }>(
    `SELECT album, artist, COUNT(*) as plays
     FROM tracks WHERE album != ''
     GROUP BY album, artist ORDER BY plays DESC LIMIT ?`,
    limit,
  )

  const items = []
  for (const r of rows ?? []) {
    const art = await db.one<{ artwork_url: string | null }>(
      'SELECT artwork_url FROM album_art WHERE album_name = ? AND artist_name = ?',
      r.album, r.artist,
    )
    items.push({
      name: r.album,
      value: r.plays,
      extra: { artist: r.artist, artwork_url: art?.artwork_url ?? null },
    })
  }
  return c.json(items)
})

// ── Top tracks ──

statsRouter.get('/top-tracks', async (c) => {
  const db = DB(c.env)
  const limit = Math.min(100, Math.max(1, Number(c.req.query('limit')) || 10))

  const { results: rows } = await db.all<{ title: string; artist: string; album: string | null; plays: number }>(
    `SELECT t.title, t.artist, t.album, COUNT(*) as plays
     FROM tracks t WHERE t.album != ''
     GROUP BY t.artist, t.title, t.album ORDER BY plays DESC LIMIT ?`,
    limit,
  )

  return c.json((rows ?? []).map((r) => ({
    name: r.title,
    value: r.plays,
    extra: { artist: r.artist, album: r.album ?? null },
  })))
})

// ── Heatmap ──

statsRouter.get('/heatmap', async (c) => {
  const db = DB(c.env)
  const { results: rows } = await db.all<{ year: string; month: string; plays: number }>(
    `SELECT strftime('%Y', e.date) as year,
            strftime('%m', e.date) as month,
            COUNT(t.id) as plays
     FROM episodes e
     JOIN tracks t ON t.episode_id = e.id
     WHERE e.date != ''
     GROUP BY year, month
     ORDER BY year, month`,
  )
  return c.json(rows ?? [])
})

// ── Recent episodes ──

statsRouter.get('/recent-episodes', async (c) => {
  const db = DB(c.env)
  const limit = Math.min(50, Math.max(1, Number(c.req.query('limit')) || 5))

  const { results: rows } = await db.all<{
    broadcast: number; date: string; title: string; track_count: number
  }>(
    `SELECT e.broadcast, e.date, e.title, COUNT(t.id) as track_count
     FROM episodes e
     LEFT JOIN tracks t ON t.episode_id = e.id
     GROUP BY e.id
     ORDER BY e.broadcast DESC
     LIMIT ?`,
    limit,
  )

  return c.json(rows ?? [])
})

// ── Countries (world map) ──

statsRouter.get('/countries', async (c) => {
  const db = DB(c.env)

  const { results: trackArtists } = await db.all<{ artist: string }>(
    'SELECT DISTINCT artist FROM tracks',
  )
  const trackArtistSet = new Set((trackArtists ?? []).map((r) => r.artist))

  const { results: rows } = await db.all<{ country: string; artist_name: string }>(
    `SELECT country, artist_name
     FROM artist_enrichment
     WHERE country IS NOT NULL AND country != '' AND country != 'XW'`,
  )

  const countryCounts = new Map<string, number>()
  for (const r of rows ?? []) {
    if (trackArtistSet.has(r.artist_name)) {
      countryCounts.set(r.country, (countryCounts.get(r.country) ?? 0) + 1)
    }
  }

  const items = Array.from(countryCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([code, count]) => ({
      code,
      numeric: ISO_NUMERIC[code] ?? null,
      count,
    }))
    .filter((i) => i.numeric !== null)

  return c.json({ items })
})

// ── Genres ──

statsRouter.get('/genres', async (c) => {
  const db = DB(c.env)

  const { results: trackArtists } = await db.all<{ artist: string }>(
    'SELECT DISTINCT artist FROM tracks',
  )
  const trackArtistSet = new Set((trackArtists ?? []).map((r) => r.artist))

  const { results: mbRows } = await db.all<{ artist_name: string; genres: string | null }>(
    "SELECT artist_name, genres FROM artist_enrichment WHERE genres IS NOT NULL AND genres != '[]'",
  )

  const genreCounter = new Map<string, number>()
  const artistsWithMB = new Set<string>()

  for (const r of mbRows ?? []) {
    if (!trackArtistSet.has(r.artist_name)) continue
    artistsWithMB.add(r.artist_name)
    try {
      const glist: string[] = JSON.parse(r.genres as unknown as string)
      for (const g of glist) genreCounter.set(g, (genreCounter.get(g) ?? 0) + 1)
    } catch { /* skip */ }
  }

  // Last.fm tags for artists without MB genres
  const { results: lfRows } = await db.all<{ artist_name: string; lastfm_tags: string | null }>(
    "SELECT artist_name, lastfm_tags FROM artist_enrichment WHERE lastfm_tags IS NOT NULL AND lastfm_tags != '[]'",
  )

  // This loop only ever sees artists with zero MB genres (the `artistsWithMB`
  // check above), so for any given tag it's counting a disjoint set of
  // artists from the MB pass — always incrementing is correct. (Previously
  // this only incremented when the genre name had never been seen from MB
  // at all, which silently dropped the entire Last.fm-only population for
  // any genre that even one MB-tagged artist also happened to have — e.g.
  // "punk" showed 44 instead of the true ~355.)
  for (const r of lfRows ?? []) {
    if (!trackArtistSet.has(r.artist_name)) continue
    if (artistsWithMB.has(r.artist_name)) continue
    try {
      const tlist: string[] = JSON.parse(r.lastfm_tags as unknown as string)
      for (const t of tlist) {
        const key = t.toLowerCase()
        genreCounter.set(key, (genreCounter.get(key) ?? 0) + 1)
      }
    } catch { /* skip */ }
  }

  const items = Array.from(genreCounter.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)

  return c.json({ items })
})

// ── Genres by year ──

statsRouter.get('/genres-by-year', async (c) => {
  const db = DB(c.env)

  const { results: rows } = await db.all<{ artist: string; year: string }>(
    `SELECT t.artist, strftime('%Y', e.date) as year
     FROM tracks t JOIN episodes e ON e.id = t.episode_id
     WHERE e.date != '' AND e.date IS NOT NULL`,
  )

  // Pre-fetch all enrichment in one round-trip to avoid N+1
  const artistNames = [...new Set((rows ?? []).map((r) => r.artist))]
  const enrichmentMap = new Map<string, string[]>()
  const BATCH_SIZE = 100
  for (let i = 0; i < artistNames.length; i += BATCH_SIZE) {
    const batch = artistNames.slice(i, i + BATCH_SIZE)
    const placeholders = batch.map(() => '?').join(',')
    const { results: enrichRows } = await db.all<{ artist_name: string; genres: string | null; lastfm_tags: string | null }>(
      `SELECT artist_name, genres, lastfm_tags FROM artist_enrichment WHERE artist_name IN (${placeholders})`,
      ...batch,
    )
    for (const er of enrichRows ?? []) {
      const tags = new Set<string>()
      try { for (const g of JSON.parse(er.genres ?? '[]')) tags.add(g.toLowerCase()) } catch { /* skip */ }
      try { for (const t of JSON.parse(er.lastfm_tags ?? '[]')) tags.add(t.toLowerCase()) } catch { /* skip */ }
      enrichmentMap.set(er.artist_name, [...tags])
    }
  }

  // Group by year
  const yearGenres = new Map<string, Map<string, number>>()
  for (const r of rows ?? []) {
    if (!r.year) continue
    const genres = enrichmentMap.get(r.artist) ?? []
    if (!yearGenres.has(r.year)) yearGenres.set(r.year, new Map())
    const yearMap = yearGenres.get(r.year)!
    for (const g of genres) {
      yearMap.set(g, (yearMap.get(g) ?? 0) + 1)
    }
  }

  const result = Array.from(yearGenres.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([year, genres]) => {
      const top = Array.from(genres.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, 8)
        .map(([name, count]) => ({ name, count }))
      return {
        year,
        total_plays: Array.from(genres.values()).reduce((s, c) => s + c, 0),
        genres: top,
      }
    })

  return c.json(result)
})

// ── Decades ──

statsRouter.get('/decades', async (c) => {
  const db = DB(c.env)

  // Pre-load album release years
  const { results: albumRows } = await db.all<{
    album_name: string; artist_name: string; release_year: number | null
  }>(
    'SELECT album_name, artist_name, release_year FROM album_art WHERE release_year IS NOT NULL',
  )

  const albumYears = new Map<string, number>()
  for (const r of albumRows ?? []) {
    albumYears.set(`${r.album_name}|${r.artist_name}`, r.release_year!)
  }

  const { results: tracks } = await db.all<{ artist: string; album: string; broadcast_year: string }>(
    `SELECT t.artist, t.album, strftime('%Y', e.date) as broadcast_year
     FROM tracks t JOIN episodes e ON e.id = t.episode_id
     WHERE t.album != '' AND e.date != ''`,
  )

  const decadePlays = new Map<number, number>()
  const decadeArtists = new Map<number, Set<string>>()
  const decadeAlbums = new Map<number, Set<string>>()
  const scatterCells = new Map<string, number>()
  let unknownTracks = 0

  for (const t of tracks ?? []) {
    const key = `${t.album}|${t.artist}`
    const year = albumYears.get(key)
    if (year) {
      const decade = Math.floor(year / 10) * 10
      decadePlays.set(decade, (decadePlays.get(decade) ?? 0) + 1)
      if (!decadeArtists.has(decade)) decadeArtists.set(decade, new Set())
      decadeArtists.get(decade)!.add(t.artist)
      if (!decadeAlbums.has(decade)) decadeAlbums.set(decade, new Set())
      decadeAlbums.get(decade)!.add(`${t.artist}|${t.album}`)
      if (t.broadcast_year) {
        const cell = `${year}|${t.broadcast_year}`
        scatterCells.set(cell, (scatterCells.get(cell) ?? 0) + 1)
      }
    } else {
      unknownTracks++
    }
  }

  const items = Array.from(decadePlays.entries())
    .sort(([a], [b]) => a - b)
    .map(([decade, plays]) => ({
      decade,
      plays,
      artists: decadeArtists.get(decade)?.size ?? 0,
      albums: decadeAlbums.get(decade)?.size ?? 0,
    }))

  const scatter = Array.from(scatterCells.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([cell, count]) => {
      const [releaseYear, broadcastYear] = cell.split('|').map(Number)
      return { release_year: releaseYear, broadcast_year: broadcastYear, plays: count }
    })

  return c.json({
    items,
    scatter,
    total_tracks: tracks?.length ?? 0,
    unknown_tracks: unknownTracks,
  })
})
