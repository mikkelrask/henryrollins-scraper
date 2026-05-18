<script>
  import { onMount } from 'svelte';
  import { api } from '../lib/api.js';
  import { router } from '../lib/router.svelte.js';
  import MergeDialog from '../lib/components/MergeDialog.svelte';

  let { params = {} } = $props();
  let albumName = $derived(params.name);

  let album = $state(null);
  let heatmapData = $state([]);
  let loading = $state(true);
  let showMerge = $state(false);

  onMount(async () => {
    try {
      const alb = await api.album(albumName);
      album = alb;
      heatmapData = alb.heatmap || [];
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  });

  // Trend pulse logic (matches artist page)
  let heatmapCells = $derived.by(() => {
    if (!heatmapData.length) return [];
    const cells = [];
    const maxPlays = Math.max(...heatmapData.map(d => d.plays), 1);
    for (const item of heatmapData) {
      const intensity = item.plays / maxPlays;
      const level = intensity > 0.7 ? 4 : intensity > 0.4 ? 3 : intensity > 0.15 ? 2 : intensity > 0 ? 1 : 0;
      cells.push({ ...item, level });
    }
    return cells;
  });

  let years = $derived([...new Set(heatmapCells.map(c => c.year))].sort());

  function back(e) {
    e.preventDefault();
    router.goto('/albums');
  }
</script>

{#if loading}
  <div class="loading-pulse"><div class="pulse-block" style="height:400px"></div></div>
{:else if album}
  <div class="page">
    <header class="album-header-new">
      <div class="header-top">
        <div class="header-identity">
          <a href="#/albums" onclick={back} class="back-link-new">← All Albums</a>

          <div class="album-title-row">
            {#if album.artwork_url_large || album.artwork_url}
              <img src={album.artwork_url_large || album.artwork_url} alt={album.album} class="album-art" loading="lazy" />
            {:else}
              <div class="album-art-placeholder">💿</div>
            {/if}
            <div class="title-artist">
              <h1 class="album-name">{album.album}</h1>
              <p class="album-artist-line">
                by <a href="#/artist/{encodeURIComponent(album.artist)}" onclick={router.navigate} class="artist-link">{album.artist}</a>
              </p>
              {#if album.release_date}
                <p class="release-info">📅 Released {album.release_date}</p>
              {/if}
              {#if album.mbid}
                <p class="release-info">
                  <a href="https://musicbrainz.org/release/{album.mbid}" target="_blank" rel="noopener" class="mbid-link">🧠 MusicBrainz</a>
                </p>
              {/if}
            </div>
          </div>
        </div>

        <div class="header-stats-new">
          <div class="stat-box">
            <span class="stat-val">{album.plays}</span>
            <span class="stat-label">Plays</span>
          </div>
          <div class="stat-box">
            <span class="stat-val">{album.distinct_tracks}</span>
            <span class="stat-label">Tracks</span>
          </div>
          <div class="stat-box">
            <span class="stat-val">{album.episodes}</span>
            <span class="stat-label">Episodes</span>
          </div>
          <button class="btn-merge-icon" onclick={() => showMerge = true} title="Merge this album into another">
            🔀 Merge
          </button>
        </div>
      </div>

      <!-- Integrated Trend Timeline (same as artist page) -->
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
    </header>

    <!-- Tracks Played -->
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

  <MergeDialog
    show={showMerge}
    entity={{ id: album.id, name: album.album, type: 'album' }}
    onclose={() => showMerge = false}
    onmerged={(detail) => {
      router.goto(`/album/${encodeURIComponent(detail.target.name)}`);
    }}
  />
{/if}

<style>
  .page { animation: fadeIn 0.3s ease-out; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

  .album-header-new {
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

  .album-title-row { display: flex; align-items: flex-start; gap: 1.25rem; margin-bottom: 0.75rem; }
  .album-art {
    width: 100px;
    height: 100px;
    border-radius: 8px;
    object-fit: cover;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    flex-shrink: 0;
  }
  .album-art-placeholder {
    width: 100px;
    height: 100px;
    border-radius: 8px;
    background: var(--color-henry-700);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 2rem;
    flex-shrink: 0;
  }
  .title-artist { min-width: 0; }
  .album-name { font-size: 2.2rem; font-weight: 900; margin: 0; line-height: 1.1; letter-spacing: -0.02em; word-break: break-word; }
  .album-artist-line { font-size: 1rem; margin: 0.4rem 0 0; color: var(--color-henry-300); }
  .artist-link { color: var(--color-henry-200); text-decoration: none; font-weight: 600; }
  .artist-link:hover { color: var(--color-accent); text-decoration: underline; }
  .release-info { font-size: 0.8rem; color: var(--color-henry-400); margin: 0.3rem 0 0; }
  .mbid-link { color: var(--color-henry-400); text-decoration: none; font-size: 0.8rem; }
  .mbid-link:hover { color: var(--color-accent); text-decoration: underline; }

  .header-stats-new {
    display: flex;
    gap: 2.5rem;
    padding-bottom: 0.5rem;
  }
  .stat-box { display: flex; flex-direction: column; align-items: flex-end; }
  .btn-merge-icon {
    margin-top: 0.5rem;
    padding: 0.3rem 0.6rem;
    border: 1px solid #555;
    border-radius: 6px;
    background: transparent;
    color: #aaa;
    cursor: pointer;
    font-size: 0.78rem;
  }
  .btn-merge-icon:hover { background: #333; color: #eac117; border-color: #eac117; }
  .stat-val { font-size: 2.2rem; font-weight: 900; line-height: 1; }
  .stat-label { font-size: 0.65rem; color: var(--color-henry-400); text-transform: uppercase; letter-spacing: 0.1em; margin-top: 0.4rem; }

  /* Integrated Trend Strip (matches artist page) */
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

  .card {
    background: var(--color-henry-800);
    border: 1px solid var(--color-henry-600);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
  }
  .card.dim { opacity: 0.65; }
  .section-title { font-size: 1.1rem; font-weight: 700; margin: 0 0 1rem; }
  .top-list { display: flex; flex-direction: column; gap: 0.3rem; }
  .top-row {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.5rem;
    border-radius: 6px;
    transition: background 0.15s;
  }
  .top-row:hover { background: var(--color-henry-700); }
  .track-name { flex: 1; font-weight: 500; }
  .track-name.unplayed { color: var(--color-henry-400); text-decoration: line-through; }
  .track-stat { font-weight: 700; color: var(--color-accent); white-space: nowrap; }
  .track-last { font-size: 0.8rem; white-space: nowrap; }
  .muted { color: var(--color-henry-300); }

  .loading-pulse { padding: 2rem 0; }
  .pulse-block { background: var(--color-henry-800); border-radius: 12px; animation: pulse 1.5s ease-in-out infinite; }
  @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.7; } }
</style>
