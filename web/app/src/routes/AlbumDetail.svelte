<script>
  import { onMount } from 'svelte';
  import { api } from '../lib/api.js';
  import { router } from '../lib/router.svelte.js';
  
  let { params = {} } = $props();
  let albumName = $derived(params.name);
  
  let album = $state(null);
  let loading = $state(true);
  
  onMount(async () => {
    try {
      album = await api.album(albumName);
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  });
  
  // Chart data
  let chartPoints = $derived(album?.timeline || []);
  let chartPath = $derived.by(() => {
    if (chartPoints.length < 2) return '';
    const w = 800, h = 180;
    const pad = { top: 20, right: 20, bottom: 30, left: 40 };
    const chartW = w - pad.left - pad.right;
    const chartH = h - pad.top - pad.bottom;
    const minX = Math.min(...chartPoints.map(p => p.broadcast));
    const maxX = Math.max(...chartPoints.map(p => p.broadcast));
    const maxY = Math.max(1, ...chartPoints.map(p => p.plays));
    const xScale = (x) => pad.left + ((x - minX) / (maxX - minX || 1)) * chartW;
    const yScale = (y) => pad.top + chartH - (y / maxY) * chartH;
    return chartPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${xScale(p.broadcast).toFixed(1)},${yScale(p.plays).toFixed(1)}`).join(' ');
  });
  
  function back(e) {
    e.preventDefault();
    router.goto('/albums');
  }
</script>

{#if loading}
  <div class="loading-pulse"><div class="pulse-block" style="height:200px"></div></div>
{:else if album}
  <div class="page">
    <a href="#/albums" onclick={back} class="back-link">← All Albums</a>
    
    <header class="album-header">
      <div class="album-header-row">
        {#if album.artwork_url_large || album.artwork_url}
          <img src={album.artwork_url_large || album.artwork_url} alt={album.album} class="album-art" loading="lazy" />
        {:else}
          <div class="album-art-placeholder">💿</div>
        {/if}
        <div>
          <h1 class="album-title">{album.album}</h1>
          <p class="album-artist">by <a href="#/artist/{encodeURIComponent(album.artist)}" onclick={router.navigate} class="artist-inline">{album.artist}</a></p>
          {#if album.release_date}
            <p class="release-info">📅 Released {album.release_date}</p>
          {/if}
          {#if album.mbid}
            <p class="release-info"><a href="https://musicbrainz.org/release/{album.mbid}" target="_blank" rel="noopener" class="mbid-link">🧠 View on MusicBrainz</a></p>
          {/if}
        </div>
      </div>
      <div class="stat-bar">
        <div class="stat-item">
          <span class="stat-num accent">{album.plays}</span>
          <span class="stat-lab">Plays</span>
        </div>
        <div class="stat-item">
          <span class="stat-num">{album.distinct_tracks}</span>
          <span class="stat-lab">Tracks</span>
        </div>
        <div class="stat-item">
          <span class="stat-num">{album.episodes}</span>
          <span class="stat-lab">Episodes</span>
        </div>
      </div>
    </header>
    
    {#if chartPath}
      <section class="card">
        <h2 class="section-title">📈 Appearances Over Time</h2>
        <svg viewBox="0 0 800 180" class="chart-svg">
          {#if chartPoints.length > 1}
            {@const maxY = Math.max(...chartPoints.map(p => p.plays))}
            {#each [0, 0.25, 0.5, 0.75, 1] as frac}
              <line x1="40" y1={160 - frac * 140} x2="780" y2={160 - frac * 140} stroke="#232340" stroke-width="1" />
              <text x="35" y={162 - frac * 140} text-anchor="end" fill="#4a4a8a" font-size="10">{Math.round(maxY * (1 - frac))}</text>
            {/each}
          {/if}
          <path d={chartPath} fill="none" stroke="#ff6b35" stroke-width="2" />
          {#each chartPoints as p}
            <circle cx={40 + ((p.broadcast - Math.min(...chartPoints.map(p2 => p2.broadcast))) / (Math.max(...chartPoints.map(p2 => p2.broadcast)) - Math.min(...chartPoints.map(p2 => p2.broadcast)) || 1)) * 740}
                    cy={160 - (p.plays / Math.max(1, ...chartPoints.map(p2 => p2.plays))) * 140}
                    r="3" fill="#ff6b35">
              <title>{p.date}: {p.plays} plays</title>
            </circle>
          {/each}
        </svg>
      </section>
    {/if}
    
    <section class="card">
      <h2 class="section-title">🎵 Tracks Played ({album.tracks.length})</h2>
      <div class="top-list">
        {#each album.tracks as track}
          <div class="top-row">
            <span class="track-name">{track.title}</span>
            <span class="track-stat">{track.plays} play{track.plays !== 1 ? 's' : ''}</span>
            {#if track.last_played}
              <span class="track-last muted">last: {track.last_played}</span>
            {/if}
          </div>
        {/each}
      </div>
    </section>
    
    {#if album.unplayed_tracks?.length}
      <section class="card dim">
        <h2 class="section-title">🚫 Not Played From This Album ({album.unplayed_tracks.length})</h2>
        <div class="top-list">
          {#each album.unplayed_tracks as title}
            <div class="top-row">
              <span class="track-name unplayed">{title}</span>
              <span class="track-stat muted">never played</span>
            </div>
          {/each}
        </div>
      </section>
    {/if}
  </div>
{/if}

<style>
  .page { animation: fadeIn 0.3s ease-out; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  .back-link { color: var(--color-henry-300); text-decoration: none; font-size: 0.9rem; margin-bottom: 1rem; display: inline-block; }
  .back-link:hover { color: var(--color-accent); }
  .album-header { margin-bottom: 2rem; }
  .album-header-row { display: flex; gap: 1.5rem; align-items: flex-start; }
  .album-art {
    width: 120px;
    height: 120px;
    border-radius: 8px;
    object-fit: cover;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    flex-shrink: 0;
  }
  .album-art-placeholder {
    width: 120px;
    height: 120px;
    border-radius: 8px;
    background: var(--color-henry-700);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 2.5rem;
    flex-shrink: 0;
  }
  .album-title { font-size: 2rem; font-weight: 800; margin: 0; }
  .album-artist { font-size: 1.1rem; margin: 0.3rem 0 0; }
  .album-artist a { color: var(--color-henry-300); text-decoration: none; }
  .album-artist a:hover { color: var(--color-accent); text-decoration: underline; }
  .release-info { font-size: 0.85rem; color: var(--color-henry-300); margin: 0.4rem 0 0; }
  .mbid-link { color: var(--color-henry-300); text-decoration: none; font-size: 0.85rem; }
  .mbid-link:hover { color: var(--color-accent); text-decoration: underline; }
  .stat-bar { display: flex; gap: 2rem; margin: 1.5rem 0; flex-wrap: wrap; }
  .stat-item { display: flex; flex-direction: column; }
  .stat-num { font-size: 1.8rem; font-weight: 800; }
  .stat-lab { font-size: 0.75rem; color: var(--color-henry-300); text-transform: uppercase; letter-spacing: 0.05em; }
  .accent { color: var(--color-accent); }
  .card { background: var(--color-henry-800); border: 1px solid var(--color-henry-600); border-radius: 12px; padding: 1.5rem; margin-bottom: 1rem; }
  .card.dim { opacity: 0.65; }
  .track-name.unplayed { color: var(--color-henry-400); text-decoration: line-through; }
  .section-title { font-size: 1.1rem; font-weight: 700; margin: 0 0 1rem; }
  .chart-svg { width: 100%; min-width: 500px; height: auto; }
  .top-list { display: flex; flex-direction: column; gap: 0.3rem; }
  .top-row { display: flex; align-items: center; gap: 1rem; padding: 0.5rem; border-radius: 6px; transition: background 0.15s; }
  .top-row:hover { background: var(--color-henry-700); }
  .track-name { flex: 1; font-weight: 500; }
  .track-stat { font-weight: 700; color: var(--color-accent); white-space: nowrap; }
  .track-last { font-size: 0.8rem; white-space: nowrap; }
  .muted { color: var(--color-henry-300); }
  .loading-pulse { padding: 2rem 0; }
  .pulse-block { background: var(--color-henry-800); border-radius: 12px; animation: pulse 1.5s ease-in-out infinite; }
  @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.7; } }
</style>
