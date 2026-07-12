<script>
  import { onMount } from 'svelte';
  import { api } from '../lib/api.js';
  import { router, urlSegment } from '../lib/router.svelte.js';
  import TrackSearchLinks from '../lib/components/TrackSearchLinks.svelte';
  
  let overview = $state(null);
  let topArtists = $state([]);
  let topAlbums = $state([]);
  let topTracks = $state([]);
  let newAdditions = $state([]);
  let recentEps = $state([]);
  let loading = $state(true);

  let top4 = $derived(topArtists.slice(0, 4));
  let maxTop = $derived(top4.reduce((m, a) => Math.max(m, a.value), 0) || 1);

  // European number formatting: 1.234.567 instead of 1,234,567
  function fmt(n) {
    return n?.toLocaleString().replace(/,/g, '.');
  }
  
  onMount(async () => {
    try {
      const [ov, ta, talb, ttr, na, re] = await Promise.all([
        api.overview(),
        api.topArtists(8),
        api.topAlbums(5),
        api.topTracks(5),
        api.newAdditions(5),
        api.recentEpisodes(5),
      ]);
      overview = ov;
      topArtists = ta;
      topAlbums = talb;
      topTracks = ttr;
      newAdditions = na;
      recentEps = re;
    } catch (e) {
      console.error('Failed to load dashboard:', e);
    } finally {
      loading = false;
    }
  });
  
  function artistLink(name) {
    return (e) => {
      e.preventDefault();
      router.goto(`/artist/${urlSegment(name)}`);
    };
  }
  
  function epLink(broadcast) {
    return (e) => {
      e.preventDefault();
      router.goto(`/episode/${broadcast}`);
    };
  }
</script>

{#if loading}
  <div class="loading-pulse">
    <div class="pulse-block" style="height:200px"></div>
    <div class="pulse-block" style="height:100px; margin-top:1rem"></div>
  </div>
{:else if overview}
  <div class="dashboard-new">
    <!-- Hero Header -->
    <header class="hero-new">
      <div class="hero-content">
        <h1 class="hero-title-new">
          Henry Rollins <span class="accent">Listens To</span>
        </h1>
        <p class="hero-tagline">
          Visualizing {overview.episodes} episodes of radio history.
        </p>
        <div class="hero-stats-new">
          <div class="hero-stat">
            <span class="h-stat-val">{overview.episodes}</span>
            <span class="h-stat-lab">Shows</span>
          </div>
          <div class="hero-stat">
            <span class="h-stat-val">{fmt(overview.tracks)}</span>
            <span class="h-stat-lab">Played Tracks</span>
          </div>
          <div class="hero-stat">
            <span class="h-stat-val">{fmt(overview.unique_artists)}</span>
            <span class="h-stat-lab">Artists</span>
          </div>
        </div>
      </div>
    </header>
    
    <!-- Top Artist Podium (Integrated Trend Style) -->
    <section class="podium-section">
      <div class="section-header-new">
        <h2 class="section-label-new">The heavy hitters</h2>
        <a href="#/artists" onclick={router.navigate} class="view-all-link">View all artists →</a>
      </div>
      <div class="podium-grid">
        {#each topArtists.slice(0, 4) as artist, i}
          <a href="#/artist/{urlSegment(artist.name)}" onclick={artistLink(artist.name)} class="podium-card {i === 0 ? 'top-spot' : ''}">
            <div class="p-rank">#{i + 1}</div>
            <div class="p-info">
              <span class="p-name">{artist.name}</span>
              <div class="p-meta">
                <span class="p-val">{artist.value}</span>
                <span class="p-lab">plays</span>
              </div>
            </div>
            <div class="p-visual-bar" style="height: {(artist.value / maxTop) * 120}px"></div>
          </a>
        {/each}
      </div>
    </section>
    
    <div class="main-dash-grid">
      <div class="dash-left-col">
        <!-- Top Tracks -->
        <section class="integrated-list">
          <div class="section-header-new">
            <h2 class="section-label-new">
              <a href="#/tracks" onclick={router.navigate} class="header-link">On heavy rotation →</a>
            </h2>
          </div>
          <div class="list-body">
            {#each topTracks as track, i}
              <div class="list-item">
                <span class="l-rank">0{i + 1}</span>
                <div class="l-info">
                  <span class="l-name">{track.name}</span>
                  <span class="l-sub">
                    <a href="#/artist/{urlSegment(track.extra.artist)}" onclick={router.navigate}>{track.extra.artist}</a>
                    {#if track.extra.album}
                      · {#if track.extra.artist}<a href="#/album/{urlSegment(track.extra.artist)}/{urlSegment(track.extra.album)}" onclick={router.navigate}>{track.extra.album}</a>{:else}<span class="dimmed">{track.extra.album}</span>{/if}
                    {/if}
                  </span>
                </div>
                <div class="l-actions">
                  <TrackSearchLinks artist={track.extra.artist} title={track.name} />
                  <span class="l-val">{track.value}x</span>
                </div>
              </div>
            {/each}
          </div>
        </section>

        <!-- New Additions -->
        {#if newAdditions.length > 0}
        <section class="integrated-list">
          <div class="section-header-new">
            <h2 class="section-label-new">New Additions</h2>
          </div>
          <div class="list-body">
            {#each newAdditions as add, i}
              <div class="list-item">
                <span class="l-rank">0{i + 1}</span>
                <div class="l-info">
                  <span class="l-name"><a href="#/artist/{urlSegment(add.artist)}" onclick={artistLink(add.artist)}>{add.artist}</a></span>
                  <span class="l-sub">
                    {add.title}
                    {#if add.album} · {add.album}{/if}
                  </span>
                </div>
                <div class="l-actions">
                  {#if add.broadcast}
                    <a href="#/episode/{add.broadcast}" onclick={epLink(add.broadcast)} class="l-val debut-link">#{add.broadcast}</a>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        </section>
        {/if}

        <!-- Top Albums -->
        <section class="integrated-list">
          <div class="section-header-new">
            <h2 class="section-label-new">
              <a href="#/albums" onclick={router.navigate} class="header-link">Crate digger's choice →</a>
            </h2>
          </div>
          <div class="list-body">
            {#each topAlbums as album, i}
              <div class="list-item">
                <span class="l-rank">0{i + 1}</span>
                {#if album.extra.artwork_url}
                  <img src={album.extra.artwork_url} alt={album.name} class="l-art" />
                {:else}
                  <div class="l-art-placeholder">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/></svg>
                  </div>
                {/if}
                <div class="l-info">
                  <span class="l-name">{#if album.extra.artist}<a href="#/album/{urlSegment(album.extra.artist)}/{urlSegment(album.name)}" onclick={router.navigate}>{album.name}</a>{:else}<span class="dimmed">{album.name}</span>{/if}</span>
                  <span class="l-sub"><a href="#/artist/{urlSegment(album.extra.artist)}" onclick={router.navigate}>{album.extra.artist}</a></span>
                </div>
                <span class="l-val">{album.value}x</span>
              </div>
            {/each}
          </div>
        </section>
      </div>

      <div class="dash-right-col">
        <!-- Recent Episodes -->
        <section class="side-panel">
          <h2 class="section-label-new">Recent Broadcasts</h2>
          <div class="side-list">
            {#each recentEps as ep}
              <a href="#/episode/{ep.broadcast}" onclick={epLink(ep.broadcast)} class="side-item">
                <span class="side-badge">#{ep.broadcast}</span>
                <div class="side-info">
                  <span class="side-date">{ep.date}</span>
                  <span class="side-count">{ep.track_count} tracks</span>
                </div>
                <span class="side-arrow">→</span>
              </a>
            {/each}
          </div>
          <a href="#/episodes" onclick={router.navigate} class="side-full-link">All episodes →</a>
        </section>

        <!-- Fast Navigation -->
        <section class="nav-shortcuts">
          <h2 class="section-label-new">Explore</h2>
          <div class="nav-grid-new">
            <a href="#/artists" onclick={router.navigate} class="nav-item-new">
              <span class="nav-title-new">Artists</span>
              <span class="nav-count-new">{fmt(overview.unique_artists)} total</span>
            </a>
            <a href="#/albums" onclick={router.navigate} class="nav-item-new">
              <span class="nav-title-new">Albums</span>
              <span class="nav-count-new">In the crates</span>
            </a>
            <a href="#/recommends" onclick={router.navigate} class="nav-item-new">
              <span class="nav-title-new">Bandcamp</span>
              <span class="nav-count-new">Henry's picks</span>
            </a>
          </div>
        </section>
      </div>
    </div>
  </div>
{/if}

<style>
  .dashboard-new { animation: fadeIn 0.3s ease-out; display: flex; flex-direction: column; gap: 2.5rem; }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
  }
  
  /* ── Hero ── */
  .hero-new {
    padding: 3rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
  }
  .hero-title-new {
    font-size: 4rem;
    font-weight: 900;
    margin: 0;
    letter-spacing: -0.03em;
    line-height: 0.9;
  }
  .accent { color: var(--color-accent); }
  .hero-tagline {
    font-size: 1.1rem;
    color: var(--color-henry-400);
    margin: 1rem 0 2rem;
    font-weight: 500;
  }
  .hero-stats-new {
    display: flex;
    flex-wrap: wrap;
    gap: 3rem;
  }
  .hero-stat { display: flex; flex-direction: column; }
  .h-stat-val { font-size: 2.5rem; font-weight: 900; line-height: 1; }
  .h-stat-lab { font-size: 0.7rem; color: var(--color-henry-500); text-transform: uppercase; letter-spacing: 0.15em; margin-top: 0.5rem; }
  
  /* ── Podium ── */
  .podium-section { display: flex; flex-direction: column; gap: 1rem; }
  .section-header-new {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-bottom: 0.5rem;
  }
  .section-label-new {
    font-size: 0.75rem;
    font-weight: 800;
    text-transform: uppercase;
    color: var(--color-henry-500);
    letter-spacing: 0.2em;
    margin: 0;
  }
  .header-link {
    color: inherit;
    text-decoration: none;
    transition: color 0.2s;
  }
  .header-link:hover {
    color: var(--color-accent);
  }
  .view-all-link { font-size: 0.75rem; color: var(--color-accent); text-decoration: none; font-weight: 600; }
  
  .podium-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 1rem;
  }
  .podium-card {
    position: relative;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 12px;
    padding: 1.5rem;
    text-decoration: none;
    color: var(--color-henry-100);
    transition: all 0.2s;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    min-height: 140px;
  }
  .podium-card:hover {
    background: rgba(255,255,255,0.06);
    border-color: var(--color-accent);
    transform: translateY(-4px);
  }
  .top-spot { border-color: rgba(255, 215, 0, 0.2); background: linear-gradient(135deg, rgba(255, 215, 0, 0.05) 0%, rgba(10, 10, 15, 0) 100%); }
  .top-spot:hover { border-color: var(--color-gold); }

  .p-rank { font-size: 0.7rem; font-weight: 800; color: var(--color-henry-500); }
  .p-name { font-size: 1.4rem; font-weight: 800; display: block; margin: 0.5rem 0; line-height: 1.1; }
  .top-spot .p-name { color: var(--color-gold); }
  .p-meta { display: flex; align-items: baseline; gap: 0.3rem; }
  .p-val { font-size: 1.1rem; font-weight: 800; color: var(--color-accent); }
  .top-spot .p-val { color: var(--color-gold); }
  .p-lab { font-size: 0.7rem; color: var(--color-henry-400); }
  .p-visual-bar {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    background: var(--color-accent);
    opacity: 0.05;
    pointer-events: none;
  }
  .top-spot .p-visual-bar { background: var(--color-gold); opacity: 0.1; }
  
  /* ── Dash Grid ── */
  .main-dash-grid {
    display: grid;
    grid-template-columns: 1.5fr 1fr;
    gap: 3rem;
  }
  @media (max-width: 1000px) { .main-dash-grid { grid-template-columns: 1fr; } }
  
  .dash-left-col { display: flex; flex-direction: column; gap: 3rem; }
  .integrated-list { display: flex; flex-direction: column; gap: 1rem; }
  .list-body { display: flex; flex-direction: column; border-top: 1px solid rgba(255,255,255,0.05); }
  
  .list-item {
    display: flex;
    align-items: center;
    gap: 1.25rem;
    padding: 1rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
  }
  .l-rank { font-size: 0.7rem; font-weight: 800; color: var(--color-henry-600); font-family: monospace; }
  .l-art, .l-art-placeholder { width: 40px; height: 40px; border-radius: 4px; object-fit: cover; flex-shrink: 0; }
  .l-art-placeholder { background: rgba(255,255,255,0.05); display: flex; align-items: center; justify-content: center; font-size: 1rem; }
  .l-info { flex: 1; min-width: 0; }
  .l-name { display: block; font-weight: 700; font-size: 1rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .l-name a { color: var(--color-henry-100); text-decoration: none; }
  .l-name a:hover { color: var(--color-accent); }
  .l-sub { font-size: 0.8rem; color: var(--color-henry-400); }
  .l-sub a { color: inherit; text-decoration: none; }
  .l-sub a:hover { color: var(--color-accent); }
  .l-val { font-size: 1.1rem; font-weight: 800; color: var(--color-accent); min-width: 3rem; text-align: right; }
  .debut-link { text-decoration: none; }
  .debut-link:hover { text-decoration: underline; }
  
  /* ── Side Panel ── */
  .dash-right-col { display: flex; flex-direction: column; gap: 3rem; }
  .side-panel {
    background: rgba(255,255,255,0.02);
    border-radius: 16px;
    padding: 1.5rem;
    border: 1px solid rgba(255,255,255,0.05);
  }
  .side-list { display: flex; flex-direction: column; gap: 0.5rem; margin: 1.5rem 0; }
  .side-item {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.75rem;
    border-radius: 8px;
    text-decoration: none;
    color: var(--color-henry-100);
    transition: background 0.15s;
  }
  .side-item:hover { background: rgba(255,255,255,0.04); }
  .side-badge { font-weight: 800; color: var(--color-accent); font-size: 0.8rem; }
  .side-info { flex: 1; display: flex; flex-direction: column; }
  .side-date { font-size: 0.85rem; font-weight: 600; }
  .side-count { font-size: 0.7rem; color: var(--color-henry-500); }
  .side-arrow { color: var(--color-henry-600); }
  .side-full-link { display: block; text-align: center; font-size: 0.8rem; font-weight: 700; color: var(--color-henry-400); text-decoration: none; }
  .side-full-link:hover { color: var(--color-accent); }

  /* ── Nav Shortcuts ── */
  .nav-grid-new { display: grid; grid-template-columns: 1fr; gap: 0.75rem; margin-top: 1rem; }
  .nav-item-new {
    padding: 1.25rem;
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 12px;
    text-decoration: none;
    color: var(--color-henry-100);
    transition: all 0.2s;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .nav-item-new:hover { border-color: var(--color-accent); background: rgba(255,255,255,0.04); }
  .nav-title-new { font-weight: 700; font-size: 1rem; }
  .nav-count-new { font-size: 0.75rem; color: var(--color-henry-500); }
  
  /* ── Loading ── */
  .loading-pulse { padding: 4rem 0; }
  .pulse-block { background: var(--color-henry-800); border-radius: 16px; animation: pulse 1.5s ease-in-out infinite; }
  @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.7; } }
</style>
