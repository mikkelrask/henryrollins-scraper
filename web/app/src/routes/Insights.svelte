<script>
  import { onMount } from 'svelte';
  import { geoNaturalEarth1, geoPath } from 'd3-geo';
  import { router } from '../lib/router.svelte.js';

  let countryData = $state([]);
  let genreData = $state([]);
  let yearData = $state([]);
  let worldFeatures = $state([]);
  let loading = $state(true);
  let hoveredCountry = $state(null);
  let hoveredWord = $state(null);
  let decadeData = $state({ items: [], scatter: [], total_tracks: 0, unknown_tracks: 0 });
  let hoveredScatter = $state(null);

  onMount(async () => {
    try {
      const [cRes, gRes, yRes, dRes, world] = await Promise.all([
        fetch('/api/stats/countries').then(r => r.json()),
        fetch('/api/stats/genres').then(r => r.json()),
        fetch('/api/stats/genres-by-year').then(r => r.json()),
        fetch('/api/stats/decades').then(r => r.json()),
        fetch('https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json').then(r => r.json()),
      ]);
      countryData = cRes.items || [];
      genreData = (gRes.items || []).slice(0, 50);
      yearData = yRes || [];
      decadeData = dRes || { items: [], scatter: [], total_tracks: 0, unknown_tracks: 0 };
      if (world.objects && world.objects.countries) {
        const topojson = await import('topojson-client');
        worldFeatures = topojson.feature(world, world.objects.countries).features;
      }
    } catch (e) {
      console.error('Insights load failed:', e);
    } finally {
      loading = false;
    }
  });

  // ── World Map ──
  const codeMap = $derived.by(() => new Map(countryData.map(c => [c.code, c.count])));
  const numericMap = $derived.by(() => new Map(countryData.map(c => [c.numeric, c.count])));
  const maxCount = $derived.by(() => Math.max(...countryData.map(c => c.count), 1));

  // Logarithmic color scale from dark (low) → bright vivid orange (high).
  // interpolateOranges goes light→dark which is backwards for data viz.
  const colorScale = $derived.by(() => {
    const logMax = Math.log10(maxCount + 1);
    // Dark base near background color (#1e1208) → bright accent (#ff6b35)
    const lerp = (t) => {
      const r = Math.round(30 + 225 * t);
      const g = Math.round(18 + 89 * t);
      const b = Math.round(8 + 45 * t);
      return `rgb(${r}, ${g}, ${b})`;
    };
    return (count) => {
      if (!count) return 'var(--color-henry-700)';
      const t = Math.log10(count + 1) / logMax;
      // Slight floor so 1-artist countries are still visible
      return lerp(Math.max(0.08, t));
    };
  });

  const projection = $derived(geoNaturalEarth1().scale(160).translate([400, 220]));
  const pathGen = $derived(geoPath().projection(projection));

  function getFeatureCode(feature) {
    // world-atlas@2 properties
    const p = feature.properties || {};
    return p.ISO_A2 || p.iso_a2 || null;
  }

  function getFeatureNumeric(feature) {
    const id = feature.id;
    if (id === undefined || id === null) return null;
    const n = typeof id === 'number' ? id : parseInt(id, 10);
    return isNaN(n) ? null : n;
  }

  function countryColor(feature) {
    const code = getFeatureCode(feature);
    if (code && codeMap.has(code)) return colorScale(codeMap.get(code));
    const num = getFeatureNumeric(feature);
    if (num && numericMap.has(num)) return colorScale(numericMap.get(num));
    return 'var(--color-henry-700)';
  }

  function getCountryHover(feature) {
    const code = getFeatureCode(feature);
    const num = getFeatureNumeric(feature);
    const match = countryData.find(c => c.code === code || c.numeric === num);
    if (match) return { name: match.code, count: match.count };
    const name = feature.properties?.name || feature.properties?.NAME || feature.id;
    return name ? { name, count: null } : null;
  }

  function getFeatureCountryCode(feature) {
    const code = getFeatureCode(feature);
    if (code && codeMap.has(code)) return code;
    const num = getFeatureNumeric(feature);
    const match = countryData.find(c => c.numeric === num);
    return match ? match.code : null;
  }

  function onCountryClick(feature) {
    const code = getFeatureCountryCode(feature);
    if (code) router.goto(`/artists?country=${code}`);
  }

  // ── Word Cloud ──
  const words = $derived.by(() => {
    if (!genreData.length) return [];
    const max = genreData[0].count;
    const min = genreData[genreData.length - 1]?.count || 1;
    const fontScale = (count) => {
      const t = (count - min) / (max - min);
      return 10 + t * 34;
    };

    const result = [];
    const containerW = 800;
    const containerH = 400;
    const centerX = containerW / 2;
    const centerY = containerH / 2;

    for (const g of genreData) {
      const fs = fontScale(g.count);
      const wordW = g.name.length * fs * 0.55;
      const wordH = fs * 1.2;
      let found = false;
      let angle = 0;
      let radius = 0;
      const step = 0.5;
      const radiusStep = 8;

      while (radius < 400 && !found) {
        const x = centerX + Math.cos(angle) * radius - wordW / 2;
        const y = centerY + Math.sin(angle) * radius - wordH / 2;

        let overlaps = false;
        for (const p of result) {
          if (x < p.x + p.w && x + wordW > p.x &&
              y < p.y + p.h && y + wordH > p.y) {
            overlaps = true;
            break;
          }
        }

        if (!overlaps && x > 0 && y > 0 && x + wordW < containerW && y + wordH < containerH) {
          result.push({ ...g, x, y, w: wordW, h: wordH, fs, opacity: 0.4 + (g.count / max) * 0.6 });
          found = true;
          break;
        }

        angle += step;
        radius += radiusStep * (step / (2 * Math.PI));
      }
    }
    return result;
  });

  // ── Yearly Timeline ──
  function genreColor(name) {
    const colors = ['#ff6b35', '#eac117', '#50c878', '#3b7dc2', '#c23b3b', '#8a4a2a', '#d01f1f', '#6b4c9a', '#2a9d8f', '#e76f51', '#264653', '#f4a261'];
    let hash = 0;
    for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
    return colors[Math.abs(hash) % colors.length];
  }

  function getYearGenre(yearItem, genreName) {
    return yearItem.genres.find(g => g.name === genreName);
  }

  // ── Release Decades ──
  const decadeMaxPlays = $derived.by(() => Math.max(...decadeData.items.map(d => d.plays), 1));

  function decadeColor(decade) {
    const decades = [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020];
    const idx = decades.indexOf(decade);
    if (idx < 0) return 'var(--color-henry-500)';
    const t = idx / (decades.length - 1);
    const r = Math.round(40 + 215 * t);
    const g = Math.round(20 + 87 * t);
    const b = Math.round(8 + 45 * t);
    return `rgb(${r}, ${g}, ${b})`;
  }

  // Scatter plot layout
  const scatterLayout = $derived.by(() => {
    const pts = decadeData.scatter;
    if (!pts.length) return null;
    const minRel = Math.min(...pts.map(p => p.release_year));
    const maxRel = Math.max(...pts.map(p => p.release_year));
    const minBc = Math.min(...pts.map(p => p.broadcast_year));
    const maxBc = Math.max(...pts.map(p => p.broadcast_year));
    const padX = 60, padY = 45, padT = 15, padR = 15;
    const w = 700 - padX - padR;
    const h = 440 - padT - padY;
    const xRange = (maxRel - minRel) || 1;
    const yRange = (maxBc - minBc) || 1;
    const maxPlays = Math.max(...pts.map(p => p.plays), 1);
    const broadcastYears = [...new Set(pts.map(p => p.broadcast_year))].sort((a, b) => b - a);
    return { pts, minRel, maxRel, minBc, maxBc, w, h, padX, padT, xRange, yRange, maxPlays, broadcastYears };
  });

  function scatterX(release_year, lay) {
    if (!lay) return 0;
    return lay.padX + ((release_year - lay.minRel) / lay.xRange) * lay.w;
  }

  function scatterY(broadcast_year, lay) {
    if (!lay) return 0;
    return lay.padT + ((lay.maxBc - broadcast_year) / lay.yRange) * lay.h;
  }

  function dotRadius(plays, lay) {
    if (!lay) return 3;
    const t = plays / lay.maxPlays;
    return 2 + t * 10;
  }

  function diagStart(lay) {
    if (!lay) return null;
    // y=x diagonal: draw from where broadcast=minBc to where broadcast=maxBc
    // At broadcast=minBc: release=minBc
    // At broadcast=maxBc: release=maxBc
    const x1 = scatterX(lay.minBc, lay);
    const y1 = scatterY(lay.minBc, lay);
    const x2 = scatterX(lay.maxBc, lay);
    const y2 = scatterY(lay.maxBc, lay);
    // Clip to chart bounds
    return { x1: Math.max(lay.padX, Math.min(lay.padX + lay.w, x1)),
             y1: Math.max(lay.padT, Math.min(lay.padT + lay.h, y1)),
             x2: Math.max(lay.padX, Math.min(lay.padX + lay.w, x2)),
             y2: Math.max(lay.padT, Math.min(lay.padT + lay.h, y2)) };
  }

  function formatYear(y) {
    return y.toString();
  }
</script>

<div class="page">
  <header class="page-header">
    <h1>🌍 Insights</h1>
    <p class="subtitle">Global reach and genre landscape of Henry's collection</p>
  </header>

  {#if loading}
    <div class="loading-pulse"><div class="pulse-block" style="height:300px"></div></div>
  {:else}

    <!-- World Map -->
    <section class="card map-card">
      <h2 class="section-title">Artist Origins</h2>
      <div class="map-wrap">
        <svg viewBox="0 0 800 440" class="world-map">
          {#each worldFeatures as feature}
            <path
              d={pathGen(feature)}
              fill={countryColor(feature)}
              stroke="rgba(255,255,255,0.06)"
              stroke-width="0.5"
              class="country-path"
              onmouseenter={() => hoveredCountry = getCountryHover(feature)}
              onmouseleave={() => hoveredCountry = null}
              onclick={() => onCountryClick(feature)}
            />
          {/each}
        </svg>
        {#if hoveredCountry}
          <div class="map-tooltip">
            {#if hoveredCountry.count !== null}
              <strong>{hoveredCountry.name}</strong>
              <span>{hoveredCountry.count} artists</span>
            {:else}
              <span>{hoveredCountry.name}</span>
            {/if}
          </div>
        {/if}
        <div class="map-legend">
          <span class="legend-label">Low</span>
          <div class="legend-bar"></div>
          <span class="legend-label">High</span>
        </div>
      </div>
      <div class="top-countries">
        {#each countryData.slice(0, 10) as c}
          <div class="country-pill">
            <span class="country-flag">{countryFlag(c.code)}</span>
            <span class="country-name">{c.code}</span>
            <span class="country-count">{c.count}</span>
          </div>
        {/each}
      </div>
    </section>

    <!-- Genre Word Cloud -->
    <section class="card word-card">
      <h2 class="section-title">Genre Word Cloud</h2>
      <div class="word-cloud">
        {#each words as w}
          <span
            class="word"
            style="left: {w.x}px; top: {w.y}px; font-size: {w.fs}px; opacity: {w.opacity};"
            onmouseenter={() => hoveredWord = w}
            onmouseleave={() => hoveredWord = null}
            onclick={() => router.goto(`/artists?genre=${encodeURIComponent(w.name)}`)}
          >
            {w.name}
          </span>
        {/each}
      </div>
      {#if hoveredWord}
        <div class="word-tooltip">
          <strong>{hoveredWord.name}</strong> - {hoveredWord.count} artists (click to browse)
        </div>
      {/if}
    </section>

    <!-- Yearly Genre Timeline -->
    <section class="card timeline-card">
      <h2 class="section-title">Genre Evolution by Year</h2>
      <div class="timeline-wrap">
        {#each yearData as d}
          <div class="year-row">
            <div class="year-label">{d.year}</div>
            <div class="year-bar-wrap">
              <div class="year-bar">
                {#each d.genres as g, i}
                  <div
                    class="year-segment"
                    style="width: {(g.count / d.total_plays) * 100}%; background: {genreColor(g.name)};"
                    title="{g.name}: {g.count}"
                    onclick={() => router.goto(`/artists?genre=${encodeURIComponent(g.name)}`)}
                  ></div>
                {/each}
              </div>
              <div class="year-count">{d.total_plays.toLocaleString()}</div>
            </div>
            <div class="year-legend">
              {#each d.genres as g}
                <span
                  class="year-chip"
                  style="color: {genreColor(g.name)};"
                  onclick={() => router.goto(`/artists?genre=${encodeURIComponent(g.name)}`)}
                >{g.name}</span>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    </section>

    <!-- Release Decades -->
    <section class="card decades-card">
      <h2 class="section-title">Release Eras</h2>
      <p class="section-subtitle">When the played albums were originally released</p>

      <div class="decade-bars">
        {#each decadeData.items as d}
          <div class="decade-row">
            <div class="decade-label">{d.decade}s</div>
            <div class="decade-bar-track">
              <div
                class="decade-bar-fill"
                style="width: {(d.plays / decadeMaxPlays) * 100}%; background: {decadeColor(d.decade)};"
              ></div>
            </div>
            <div class="decade-stats">
              <span class="decade-plays">{d.plays.toLocaleString()}</span>
              <span class="decade-sub">{d.artists} artists</span>
            </div>
          </div>
        {/each}
        {#if decadeData.unknown_tracks > 0}
          <div class="decade-row decade-unknown">
            <div class="decade-label">??</div>
            <div class="decade-bar-track">
              <div class="decade-bar-fill" style="width: 100%; background: var(--color-henry-700);"></div>
            </div>
            <div class="decade-stats">
              <span class="decade-plays">{decadeData.unknown_tracks.toLocaleString()}</span>
              <span class="decade-sub">no year data</span>
            </div>
          </div>
        {/if}
      </div>

      <h3 class="sub-section-title">Release Year vs. Broadcast Year</h3>
      <p class="section-subtitle">Each dot = an album. Distance above the line = how old the music was when Henry played it.</p>
      <div class="scatter-wrap">
        <svg viewBox="0 0 700 440" class="scatter-plot">
          {#if scatterLayout}
            <!-- Axes -->
            <line x1={scatterLayout.padX} y1={scatterLayout.padT + scatterLayout.h}
                  x2={scatterLayout.padX + scatterLayout.w} y2={scatterLayout.padT + scatterLayout.h}
                  stroke="var(--color-henry-600)" stroke-width="1" />
            <line x1={scatterLayout.padX} y1={scatterLayout.padT}
                  x2={scatterLayout.padX} y2={scatterLayout.padT + scatterLayout.h}
                  stroke="var(--color-henry-600)" stroke-width="1" />

            <!-- X axis ticks -->
            {#each [1960, 1970, 1980, 1990, 2000, 2010, 2020] as yr}
              <text x={scatterX(yr, scatterLayout)} y={scatterLayout.padT + scatterLayout.h + 16}
                    fill="var(--color-henry-400)" font-size="9" text-anchor="middle">{yr}</text>
            {/each}
            <text x={scatterLayout.padX + scatterLayout.w / 2} y={scatterLayout.padT + scatterLayout.h + 36}
                  fill="var(--color-henry-500)" font-size="9" text-anchor="middle">Release Year</text>

            <!-- Y axis ticks -->
            {#each scatterLayout.broadcastYears as yr}
              <text x={scatterLayout.padX - 8} y={scatterY(yr, scatterLayout) + 3}
                    fill="var(--color-henry-400)" font-size="9" text-anchor="end">{yr}</text>
            {/each}
            <text x={14} y={scatterLayout.padT + scatterLayout.h / 2}
                  fill="var(--color-henry-500)" font-size="9" text-anchor="middle"
                  transform="rotate(-90, 14, {scatterLayout.padT + scatterLayout.h / 2})">Broadcast Year</text>

            <!-- y=x diagonal (brand new line) -->
            {#if diagStart(scatterLayout)}
              <line x1={diagStart(scatterLayout).x1} y1={diagStart(scatterLayout).y1}
                    x2={diagStart(scatterLayout).x2} y2={diagStart(scatterLayout).y2}
                    stroke="var(--color-accent)" stroke-width="1.5" stroke-dasharray="5,4" opacity="0.5" />
              <text x={diagStart(scatterLayout).x2 + 4} y={diagStart(scatterLayout).y2 - 4}
                    fill="var(--color-accent)" font-size="8" opacity="0.6">brand new</text>
            {/if}

            <!-- Data dots -->
            {#each scatterLayout.pts as p}
              <circle
                cx={scatterX(p.release_year, scatterLayout)}
                cy={scatterY(p.broadcast_year, scatterLayout)}
                r={dotRadius(p.plays, scatterLayout)}
                fill="var(--color-accent)"
                opacity="0.35"
                class="scatter-dot"
                onmouseenter={() => hoveredScatter = p}
                onmouseleave={() => hoveredScatter = null}
              />
            {/each}

            <!-- Hover highlight -->
            {#if hoveredScatter}
              <circle
                cx={scatterX(hoveredScatter.release_year, scatterLayout)}
                cy={scatterY(hoveredScatter.broadcast_year, scatterLayout)}
                r={dotRadius(hoveredScatter.plays, scatterLayout) + 3}
                fill="none"
                stroke="#fff"
                stroke-width="1.5"
                opacity="0.8"
              />
            {/if}
          {/if}
        </svg>
        {#if hoveredScatter}
          <div class="scatter-tooltip">
            Released <strong>{hoveredScatter.release_year}</strong>
            · Played in <strong>{hoveredScatter.broadcast_year}</strong>
            · <strong>{hoveredScatter.plays}</strong> plays
            {hoveredScatter.broadcast_year - hoveredScatter.release_year > 0
              ? `(${hoveredScatter.broadcast_year - hoveredScatter.release_year} year gap)`
              : '(brand new!)'}
          </div>
        {/if}
      </div>
    </section>

    <!-- About this data -->
    <section class="card about-card">
      <h2 class="section-title">About this data</h2>
      <div class="about-body">
        <p>
          The track data on this site comes directly from
          <a href="https://www.henryrollins.com/radio" target="_blank" rel="noopener">henryrollins.com/radio</a>,
          covering every episode available on the site. Henry hand-rolls each tracklist himself,
          and the raw scraped listings inevitably contain formatting quirks, inconsistent artist
          spellings, and the occasional typo. A lot of work goes into normalizing and deduplicating
          that data - fuzzy-matching artist and album names against MusicBrainz, canonicalizing
          entries, merging variants - all to surface the cleanest version possible. It's not
          perfect, but it's been a labour of love.
        </p>
        <p>
          Artist metadata is enriched through two complementary open sources:
          <a href="https://musicbrainz.org" target="_blank" rel="noopener">MusicBrainz</a>,
          an open music encyclopedia maintained by a global community of volunteers, and
          <a href="https://last.fm" target="_blank" rel="noopener">Last.fm</a>, which provides
          crowd-sourced listener data, bios, and genre tags. We match artist names as best we can
          using fuzzy matching and MusicBrainz identifiers, but coverage inevitably has gaps -
          especially for obscure, very new, or non-Western artists.
        </p>
        <p>
          Country of origin is derived from MusicBrainz artist profiles, while genre
          classifications blend MusicBrainz genres with Last.fm's user-generated tags. Release
          years for albums are pulled from MusicBrainz when available - currently about 36% of
          albums in the collection have a known release year, so the decade breakdowns and
          release-vs-broadcast scatter plot on this page reflect a best-effort subset of the data.
        </p>
        <p>
          Because both MusicBrainz and Last.fm rely on crowdsourced submissions, coverage is
          excellent for well-known artists but can be sparse or inaccurate for obscure or
          recently formed bands. Genres are inherently subjective - an artist tagged "post-punk"
          by one user might be "indie rock" to another. The counts and classifications here
          reflect the aggregated wisdom of those communities, not a definitive taxonomy. If
          something looks off, it probably is - and that's part of the charm of working with
          real-world music data.
        </p>
      </div>
    </section>

  {/if}
</div>

<script context="module">
  function countryFlag(code) {
    if (!code || code.length !== 2) return '🌐';
    return String.fromCodePoint(
      code.charCodeAt(0) + 0x1F1E6 - 0x41,
      code.charCodeAt(1) + 0x1F1E6 - 0x41,
    );
  }
</script>

<style>
  .page { padding-bottom: 3rem; animation: fadeIn 0.3s ease-out; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

  .page-header { margin-bottom: 2rem; }
  .page-header h1 { margin: 0; font-size: 2rem; }
  .subtitle { color: var(--color-henry-400); font-size: 0.9rem; margin: 0.3rem 0 0; }

  .card {
    background: var(--color-henry-800);
    border: 1px solid var(--color-henry-600);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
  }
  .section-title { font-size: 1.1rem; font-weight: 700; margin: 0 0 1rem; }

  /* Map */
  .map-card { position: relative; }
  .map-wrap { position: relative; }
  .world-map { width: 100%; height: auto; max-height: 440px; }
  .country-path { transition: fill 0.2s; cursor: pointer; }
  .country-path:hover { stroke: var(--color-accent); stroke-width: 1.5; filter: brightness(1.2); }
  .map-tooltip {
    position: absolute;
    top: 8px; right: 8px;
    background: var(--color-henry-800);
    border: 1px solid var(--color-henry-600);
    border-radius: 6px;
    padding: 0.35rem 0.7rem;
    font-size: 0.8rem;
    pointer-events: none;
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
  }
  .map-tooltip strong { color: var(--color-accent); }
  .map-tooltip span { color: var(--color-henry-300); font-size: 0.75rem; }
  .map-legend {
    display: flex; align-items: center; gap: 0.5rem;
    margin-top: 0.75rem; justify-content: center;
  }
  .legend-label { font-size: 0.7rem; color: var(--color-henry-500); }
  .legend-bar { width: 120px; height: 8px; border-radius: 4px; background: linear-gradient(90deg, #1a0f00, #ff6b35); }

  .top-countries {
    display: flex; flex-wrap: wrap; gap: 0.5rem;
    margin-top: 1rem; padding-top: 1rem;
    border-top: 1px solid var(--color-henry-700);
  }
  .country-pill {
    display: flex; align-items: center; gap: 0.35rem;
    padding: 0.25rem 0.6rem; border-radius: 5px;
    background: var(--color-henry-700); font-size: 0.78rem;
  }
  .country-flag { font-size: 0.9rem; }
  .country-name { font-weight: 600; color: var(--color-henry-200); }
  .country-count { color: var(--color-accent); font-weight: 700; margin-left: 0.2rem; }

  /* Word Cloud */
  .word-card { position: relative; min-height: 450px; }
  .word-cloud {
    position: relative;
    width: 100%;
    max-width: 800px;
    height: 400px;
    overflow: hidden;
    margin: 0 auto;
  }
  .word {
    position: absolute;
    font-weight: 700;
    color: var(--color-henry-100);
    cursor: pointer;
    transition: all 0.2s;
    line-height: 1;
    white-space: nowrap;
    text-transform: uppercase;
    letter-spacing: 0.02em;
  }
  .word:hover {
    color: var(--color-accent);
    z-index: 10;
    text-shadow: 0 0 12px rgba(255, 107, 53, 0.3);
  }
  .word-tooltip {
    text-align: center;
    margin-top: 0.5rem;
    font-size: 0.85rem;
    color: var(--color-henry-300);
    min-height: 1.5rem;
  }
  .word-tooltip strong { color: var(--color-accent); }

  /* Decade Bars */
  .decades-card { }
  .section-subtitle { color: var(--color-henry-400); font-size: 0.8rem; margin: -0.5rem 0 1rem; }
  .sub-section-title { font-size: 1rem; font-weight: 700; margin: 1.5rem 0 0.25rem; }

  .decade-bars {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 1rem;
  }
  .decade-row {
    display: grid;
    grid-template-columns: 55px 1fr 110px;
    gap: 0.75rem;
    align-items: center;
  }
  .decade-label {
    font-size: 0.85rem;
    font-weight: 700;
    color: var(--color-henry-200);
    text-align: right;
  }
  .decade-bar-track {
    height: 22px;
    background: var(--color-henry-700);
    border-radius: 5px;
    overflow: hidden;
  }
  .decade-bar-fill {
    height: 100%;
    border-radius: 5px;
    transition: width 0.4s ease-out;
    min-width: 2px;
  }
  .decade-stats {
    display: flex;
    flex-direction: column;
    line-height: 1.2;
  }
  .decade-plays {
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--color-henry-100);
  }
  .decade-sub {
    font-size: 0.7rem;
    color: var(--color-henry-400);
  }
  .decade-unknown .decade-label { color: var(--color-henry-500); }

  /* Scatter Plot */
  .scatter-wrap {
    position: relative;
    margin-top: 0.5rem;
  }
  .scatter-plot {
    width: 100%;
    height: auto;
    max-height: 440px;
  }
  .scatter-dot {
    transition: opacity 0.15s;
    cursor: crosshair;
  }
  .scatter-dot:hover {
    opacity: 0.8 !important;
  }
  .scatter-tooltip {
    position: absolute;
    top: 8px;
    right: 8px;
    background: var(--color-henry-800);
    border: 1px solid var(--color-henry-600);
    border-radius: 6px;
    padding: 0.4rem 0.7rem;
    font-size: 0.8rem;
    pointer-events: none;
    color: var(--color-henry-200);
  }
  .scatter-tooltip strong {
    color: var(--color-accent);
    font-weight: 700;
  }

  /* Yearly Timeline */
  .timeline-card { }
  .timeline-wrap {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .year-row {
    display: grid;
    grid-template-columns: 50px 1fr;
    gap: 0.75rem 1rem;
    align-items: center;
    padding: 0.4rem 0;
    border-bottom: 1px solid var(--color-henry-700);
  }
  .year-row:last-child { border-bottom: none; }
  .year-label {
    font-size: 0.8rem;
    font-weight: 700;
    color: var(--color-henry-200);
    text-align: right;
  }
  .year-bar-wrap {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
  .year-bar {
    flex: 1;
    display: flex;
    height: 22px;
    border-radius: 5px;
    overflow: hidden;
    background: var(--color-henry-700);
  }
  .year-segment {
    height: 100%;
    transition: opacity 0.15s;
    cursor: pointer;
    min-width: 2px;
  }
  .year-segment:hover {
    opacity: 0.8;
    filter: brightness(1.15);
  }
  .year-count {
    font-size: 0.7rem;
    color: var(--color-henry-400);
    min-width: 40px;
    text-align: right;
  }
  .year-legend {
    grid-column: 2;
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    margin-top: -0.3rem;
    margin-bottom: 0.2rem;
  }
  .year-chip {
    font-size: 0.68rem;
    font-weight: 600;
    background: rgba(255,255,255,0.04);
    padding: 0.08rem 0.35rem;
    border-radius: 3px;
    cursor: pointer;
    transition: background 0.15s;
  }
  .year-chip:hover {
    background: rgba(255,255,255,0.1);
  }

  /* About card */
  .about-card { }
  .about-body {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    color: var(--color-henry-300);
    font-size: 0.9rem;
    line-height: 1.6;
  }
  .about-body a {
    color: var(--color-accent);
    text-decoration: none;
    font-weight: 500;
  }
  .about-body a:hover { text-decoration: underline; }

  .loading-pulse { padding: 2rem 0; }
  .pulse-block {
    background: var(--color-henry-800);
    border-radius: 12px;
    animation: pulse 1.5s ease-in-out infinite;
  }
  @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.7; } }
</style>
