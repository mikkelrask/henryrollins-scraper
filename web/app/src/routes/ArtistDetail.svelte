<script>
  import { onMount } from 'svelte';
  import { api } from '../lib/api.js';
  import { router } from '../lib/router.svelte.js';
  import Badge from '../lib/components/Badge.svelte';
  import TrackSearchLinks from '../lib/components/TrackSearchLinks.svelte';
  
  let { params = {} } = $props();
  let artistName = $derived(params.name);
  
  let artist = $state(null);
  let heatmapData = $state([]);
  let tracks = $state([]);
  let loading = $state(true);
  let trackPage = $state(1);
  let trackTotal = $state(0);
  
  onMount(async () => {
    try {
      const [art, hm, tr] = await Promise.all([
        api.artist(artistName),
        api.artistHeatmap(artistName),
        api.artistTracks(artistName, trackPage)
      ]);
      artist = art;
      heatmapData = hm;
      tracks = tr.items;
      trackTotal = tr.total;
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  });
  
  // Fanatic Heatmap 2.0 Logic
  let heatmapCells = $derived.by(() => {
    if (!heatmapData.length) return [];
    const cells = [];
    const maxPlays = Math.max(...heatmapData.map(d => d.plays));
    for (const item of heatmapData) {
      const intensity = Math.min(item.plays / Math.max(maxPlays, 1), 1);
      // Levels 0-4 mapped to orange/gold scale
      const level = intensity > 0.7 ? 4 : intensity > 0.4 ? 3 : intensity > 0.15 ? 2 : intensity > 0 ? 1 : 0;
      cells.push({ ...item, level });
    }
    return cells;
  });
  
  let years = $derived([...new Set(heatmapCells.map(c => c.year))].sort());

  let totalAlbums = $derived(artist?.album_breakdown?.length || 0);

  // Album diversity gauge
  let diversityPct = $derived(artist?.album_diversity != null ? Math.min(artist.album_diversity * 100, 100) : 0);
  let diversityLabel = $derived(
    diversityPct > 50 ? 'Crate Digger 🏅' : 
    diversityPct < 10 ? 'One-Album Wonder 🪩' : 'Explorer'
  );
  
  function goAlbums(e) {
    e.preventDefault();
    router.goto(`/artist/${encodeURIComponent(artist.artist)}/albums`);
  }
  function back(e) {
    e.preventDefault();
    router.goto('/artists');
  }

  async function loadMoreTracks() {
    trackPage++;
    const tr = await api.artistTracks(artistName, trackPage);
    tracks = [...tracks, ...tr.items];
  }
</script>

{#if loading}
  <div class="loading-pulse"><div class="pulse-block" style="height:400px"></div></div>
{:else if artist}
  <div class="page">
    <!-- Back + Header -->
    <a href="#/artists" onclick={back} class="back-link">← All Artists</a>
    
    <header class="artist-header-new">
      <div class="header-top">
        <div class="header-identity">
          <a href="#/artists" onclick={back} class="back-link-new">← All Artists</a>
          <div class="artist-title-row">
            <h1 class="artist-name">{artist.artist}</h1>
            {#if artist.badge}
              <Badge type={artist.badge} />
            {/if}
          </div>
          
          {#if artist.enrichment?.genres?.length}
            <div class="tags-row-new">
              {#each artist.enrichment.genres.slice(0, 4) as genre}
                <span class="tag-new">{genre}</span>
              {/each}
            </div>
          {/if}
          
          <div class="meta-row-new">
            {#if artist.first_appearance}
              <span class="meta-item">First: <strong>{artist.first_appearance}</strong></span>
            {/if}
            {#if artist.last_appearance}
              <span class="meta-item">Latest: <strong>{artist.last_appearance}</strong></span>
            {/if}
          </div>
        </div>

        <div class="header-stats-new">
          <div class="stat-box">
            <span class="stat-val">{artist.plays}</span>
            <span class="stat-label">Plays</span>
          </div>
          <div class="stat-box">
            <span class="stat-val">{artist.episodes}</span>
            <span class="stat-label">Episodes</span>
          </div>
          <div class="stat-box">
            <span class="stat-val accent">{artist.rli.toFixed(2)}</span>
            <span class="stat-label">Love Index</span>
          </div>
          {#if artist.streak != null}
            <div class="stat-box">
              <span class="stat-val gold">{artist.streak}</span>
              <span class="stat-label">Best Streak</span>
            </div>
          {/if}
        </div>
      </div>

      <!-- Integrated Trend Timeline (Full Width, No Card) -->
      {#if heatmapCells.length > 0}
        <div class="integrated-trend-container">
          <div class="trend-meta">
            <span class="trend-label">Fanatic History</span>
            <div class="trend-legend">
              <span class="legend-text">Rare</span>
              <div class="legend-pip level-1"></div>
              <div class="legend-pip level-2"></div>
              <div class="legend-pip level-3"></div>
              <div class="legend-pip level-4"></div>
              <span class="legend-text">Heavy</span>
            </div>
          </div>
          <div class="trend-strip">
            {#each heatmapCells as cell}
              <div 
                class="trend-pip level-{cell.level}" 
                title="{cell.plays} plays in {cell.month}/{cell.year}"
              ></div>
            {/each}
          </div>
          <div class="trend-years">
            {#each years as year, i}
              {#if i === 0 || i === years.length - 1 || i % 3 === 0}
                <span class="trend-year-label">{year}</span>
              {/if}
            {/each}
          </div>
        </div>
      {/if}

      {#if artist.enrichment?.bio_summary}
        <div class="bio-section-new">
          <p class="bio-text-new">{artist.enrichment.bio_summary}</p>
        </div>
      {/if}
    </header>
    
    <!-- Main Stats Grid -->
    <div class="main-stats-grid">
      <div class="details-grid">
        <!-- Top Tracks -->
        <section class="card">
          <h2 class="section-title">🎵 Henry's Favs</h2>
          <div class="top-list">
            {#each artist.top_tracks as track}
              <div class="top-row">
                <div class="top-info">
                  <span class="top-name">{track.title}</span>
                  {#if track.album}
                    <span class="top-album">
                      on <a href="#/album/{encodeURIComponent(track.album)}" onclick={router.navigate}>{track.album}</a>
                    </span>
                  {/if}
                </div>
                <div class="top-actions">
                  <TrackSearchLinks artist={artist.artist} title={track.title} />
                  <span class="top-val">{track.plays}x</span>
                </div>
              </div>
            {/each}
          </div>
        </section>
        
        <!-- Album Breakdown -->
        <section class="card">
          <h2 class="section-title">💿 Album Breakdown</h2>
          <div class="diversity-gauge">
            <div class="gauge-label">{diversityLabel}</div>
            <div class="gauge-track">
              <div class="gauge-fill" style="width: {diversityPct}%"></div>
            </div>
          </div>
          <div class="album-list">
            {#each artist.album_breakdown.slice(0, 9) as alb}
              <div class="album-row-list">
                {#if alb.artwork_url}
                  <img src={alb.artwork_url} alt={alb.album} class="album-mini-art" loading="lazy" />
                {:else}
                  <div class="album-mini-placeholder">💿</div>
                {/if}
                <div class="album-row-info">
                  <span class="album-row-name"><a href="#/album/{encodeURIComponent(alb.album)}" onclick={router.navigate} class="album-link">{alb.album}</a></span>
                  <span class="album-row-sub">{alb.distinct_tracks} tracks</span>
                </div>
                <span class="album-row-plays">{alb.plays}x</span>
              </div>
            {/each}
          </div>
          {#if totalAlbums > 5}
            <button onclick={goAlbums} class="show-all-btn">View All {totalAlbums} Albums →</button>
          {/if}
        </section>
      </div>
    </div>
    
    <!-- Track History -->
    <section class="card track-history">
      <h2 class="section-title">📋 Track History ({trackTotal} plays)</h2>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Date</th>
              <th>Title</th>
              <th>Album</th>
              <th class="right">Listen</th>
            </tr>
          </thead>
          <tbody>
            {#each tracks as t}
              <tr>
                <td class="ep-num">
                  <a href="#/episode/{t.broadcast}" onclick={router.navigate}>
                    #{t.broadcast}
                  </a>
                </td>
                <td class="muted">
                  <a href="#/episode/{t.broadcast}" onclick={router.navigate} class="date-link">
                    {t.date}
                  </a>
                </td>
                <td class="track-title">{t.title}</td>
                <td class="album-cell">
                  {#if t.album}
                    <a href="#/album/{encodeURIComponent(t.album)}" onclick={router.navigate} class="album-link">
                      {t.album}
                    </a>
                  {:else}
                    <span class="muted">—</span>
                  {/if}
                </td>
                <td class="right">
                  <TrackSearchLinks artist={artist.artist} title={t.title} />
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      {#if trackTotal > tracks.length}
        <button class="load-more" onclick={loadMoreTracks}>
          Load more…
        </button>
      {/if}
    </section>
  </div>
{/if}

<style>
  .page { animation: fadeIn 0.3s ease-out; }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
  }
  
  .artist-header-new {
    margin-bottom: 2rem;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }
  
  .header-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 2rem;
    flex-wrap: wrap;
  }

  .header-identity { flex: 1; min-width: 300px; }
  .back-link-new {
    color: var(--color-henry-400);
    text-decoration: none;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 0.5rem;
    display: block;
  }
  .back-link-new:hover { color: var(--color-accent); }

  .artist-title-row { display: flex; align-items: center; gap: 1rem; margin-bottom: 0.75rem; }
  .artist-name { font-size: 3rem; font-weight: 900; margin: 0; line-height: 1; letter-spacing: -0.02em; }
  
  .tags-row-new { display: flex; gap: 0.4rem; margin-bottom: 0.75rem; }
  .tag-new {
    padding: 0.1rem 0.6rem;
    border-radius: 4px;
    background: rgba(255,255,255,0.05);
    color: var(--color-henry-300);
    font-size: 0.7rem;
    text-transform: uppercase;
    font-weight: 600;
    border: 1px solid rgba(255,255,255,0.05);
  }

  .meta-row-new { display: flex; gap: 1.5rem; color: var(--color-henry-400); font-size: 0.85rem; }
  .meta-item strong { color: var(--color-henry-200); margin-left: 0.2rem; }

  .header-stats-new {
    display: flex;
    gap: 2.5rem;
    padding-bottom: 0.5rem;
  }
  .stat-box { display: flex; flex-direction: column; align-items: flex-end; }
  .stat-val { font-size: 2.2rem; font-weight: 900; line-height: 1; }
  .stat-label { font-size: 0.65rem; color: var(--color-henry-400); text-transform: uppercase; letter-spacing: 0.1em; margin-top: 0.4rem; }
  .accent { color: var(--color-accent); }
  .gold { color: var(--color-gold); }

  /* Integrated Trend Strip (Card-free) */
  .integrated-trend-container {
    padding: 1.5rem 0;
    border-top: 1px solid rgba(255,255,255,0.05);
    border-bottom: 1px solid rgba(255,255,255,0.05);
  }
  .trend-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }
  .trend-label { font-size: 0.7rem; font-weight: 800; text-transform: uppercase; color: var(--color-henry-500); letter-spacing: 0.2em; }
  .trend-legend { display: flex; align-items: center; gap: 4px; }
  .legend-text { font-size: 0.6rem; color: var(--color-henry-500); text-transform: uppercase; margin: 0 4px; }
  .legend-pip { width: 8px; height: 8px; border-radius: 1px; }

  .trend-strip {
    display: flex;
    gap: 3px;
    height: 32px;
    width: 100%;
  }
  .trend-pip {
    flex: 1;
    height: 100%;
    border-radius: 2px;
    transition: all 0.2s;
  }
  .trend-pip:hover {
    transform: scaleY(1.3);
    z-index: 10;
    box-shadow: 0 0 10px var(--color-accent);
  }

  .trend-years {
    display: flex;
    justify-content: space-between;
    margin-top: 0.5rem;
    padding: 0 2px;
  }
  .trend-year-label { font-size: 0.65rem; font-weight: 600; color: var(--color-henry-500); }

  .level-0 { background: rgba(255,255,255,0.03); }
  .level-1 { background: #4a2c1a; }
  .level-2 { background: #8a4a2a; }
  .level-3 { background: var(--color-accent); }
  .level-4 { background: var(--color-gold); box-shadow: 0 0 8px rgba(255, 215, 0, 0.2); }

  .bio-section-new {
    max-width: 800px;
  }
  .bio-text-new {
    font-size: 0.95rem;
    line-height: 1.6;
    color: var(--color-henry-300);
    margin: 0;
  }

  .main-stats-grid {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    margin-bottom: 1rem;
  }
  
  .details-grid {
    display: grid;
    grid-template-columns: 1.2fr 1fr;
    gap: 1rem;
    align-items: start;
  }

  @media (max-width: 1024px) {
    .details-grid { grid-template-columns: 1fr; }
  }
  
  .card {
    background: var(--color-henry-800);
    border: 1px solid var(--color-henry-600);
    border-radius: 12px;
    padding: 1.25rem;
    display: flex;
    flex-direction: column;
  }
  .section-title {
    font-size: 1.1rem;
    font-weight: 700;
    margin: 0 0 1rem;
  }
  
  /* Heatmap (Moved to Header) */
  
  .top-list { display: flex; flex-direction: column; gap: 0.4rem; }
  .top-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem;
    border-radius: 8px;
    transition: background 0.15s;
    background: rgba(255,255,255,0.02);
  }
  .top-row:hover { background: var(--color-henry-700); }
  .top-info { display: flex; flex-direction: column; gap: 0.1rem; }
  .top-name { font-weight: 600; font-size: 0.9rem; color: var(--color-henry-100); }
  .top-album { font-size: 0.75rem; color: var(--color-henry-400); }
  .top-album a { color: var(--color-henry-300); text-decoration: none; }
  .top-album a:hover { color: var(--color-accent); text-decoration: underline; }
  
  .top-actions { display: flex; align-items: center; gap: 0.75rem; }
  .top-val { font-weight: 700; color: var(--color-accent); min-width: 2rem; text-align: right; }
  
  /* Album list with artwork */
  .album-list { display: flex; flex-direction: column; gap: 0.4rem; }
  .album-row-list {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.35rem 0.5rem;
    border-radius: 8px;
    transition: background 0.15s;
  }
  .album-row-list:hover { background: var(--color-henry-700); }
  .album-mini-art {
    width: 32px;
    height: 32px;
    border-radius: 4px;
    object-fit: cover;
    flex-shrink: 0;
  }
  .album-mini-placeholder {
    width: 32px;
    height: 32px;
    border-radius: 4px;
    background: var(--color-henry-700);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.8rem;
    flex-shrink: 0;
  }
  .album-row-info { flex: 1; min-width: 0; }
  .album-row-name a { color: var(--color-henry-100); text-decoration: none; }
  .album-row-name a:hover { color: var(--color-accent); }
  .album-row-name { display: block; font-weight: 500; font-size: 0.85rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .album-row-sub { font-size: 0.7rem; color: var(--color-henry-300); }
  .album-row-plays { font-weight: 700; color: var(--color-accent); font-size: 0.9rem; }
  
  .diversity-gauge { margin-bottom: 1rem; }
  .show-all-btn {
    display: block; width: 100%; margin-top: auto; padding: 0.5rem;
    border-radius: 8px; border: 1px solid var(--color-henry-600);
    background: var(--color-henry-700); color: var(--color-henry-200);
    font-size: 0.85rem; cursor: pointer; transition: all 0.15s; text-align: center;
  }
  .show-all-btn:hover { background: var(--color-henry-600); color: var(--color-henry-100); }
  .gauge-label { font-size: 0.8rem; font-weight: 600; margin-bottom: 0.3rem; color: var(--color-henry-200); }
  .gauge-track {
    height: 8px;
    background: var(--color-henry-700);
    border-radius: 4px;
    overflow: hidden;
  }
  .gauge-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--color-accent), var(--color-gold));
    border-radius: 4px;
    transition: width 0.5s ease;
  }
  
  .track-history { margin-bottom: 2rem; }
  .table-wrap { overflow-x: auto; }
  .data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }
  .data-table th {
    text-align: left;
    padding: 0.5rem 0.75rem;
    font-weight: 600;
    font-size: 0.75rem;
    text-transform: uppercase;
    color: var(--color-henry-300);
    border-bottom: 1px solid var(--color-henry-600);
  }
  .data-table td {
    padding: 0.4rem 0.75rem;
    border-bottom: 1px solid var(--color-henry-700);
    vertical-align: middle;
  }
  .data-table tr:last-child td { border-bottom: none; }
  .data-table tr:hover { background: var(--color-henry-700); }
  .ep-num a { color: var(--color-accent); text-decoration: none; }
  .ep-num a:hover { text-decoration: underline; }
  .date-link { color: inherit; text-decoration: none; }
  .date-link:hover { color: var(--color-accent); text-decoration: underline; }
  
  .track-title { font-weight: 500; color: var(--color-henry-100); }
  .album-cell a { color: var(--color-henry-200); text-decoration: none; }
  .album-cell a:hover { color: var(--color-accent); text-decoration: underline; }
  .right { text-align: right; }
  .muted { color: var(--color-henry-300); }
  
  .load-more {
    width: 100%;
    padding: 0.5rem;
    margin-top: 0.5rem;
    border: 1px dashed var(--color-henry-600);
    border-radius: 8px;
    background: transparent;
    color: var(--color-henry-300);
    cursor: pointer;
    font-size: 0.85rem;
    transition: all 0.15s;
  }
  .load-more:hover {
    border-color: var(--color-accent);
    color: var(--color-accent);
  }
  
  .loading-pulse { padding: 2rem 0; }
  .pulse-block {
    background: var(--color-henry-800);
    border-radius: 12px;
    animation: pulse 1.5s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 0.4; }
    50% { opacity: 0.7; }
  }
</style>
