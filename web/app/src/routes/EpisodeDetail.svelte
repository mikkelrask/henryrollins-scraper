<script>
  import { onMount } from 'svelte';
  import { api } from '../lib/api.js';
  import { router, urlSegment } from '../lib/router.svelte.js';
  import TrackSearchLinks from '../lib/components/TrackSearchLinks.svelte';
  import TrackEditor from '../lib/components/TrackEditor.svelte';
  import { auth } from '../lib/useAuth.svelte.js';
  
  let { params = {} } = $props();
  let ident = $derived(params.broadcast);
  let broadcast = $derived(Number(ident));
  
  let ep = $state(null);
  let loading = $state(true);

  // Modal state
  let editor = $state({ show: false, mode: 'edit', track: null });

  async function load() {
    loading = true;
    try {
      ep = await fetch(`/api/episodes/${encodeURIComponent(ident)}`).then(r => { if (!r.ok) throw Error(); return r.json(); });
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  }
  
  onMount(load);

  function editTrack(track) {
    editor = { show: true, mode: 'edit', track };
  }

  function addTrack() {
    editor = { show: true, mode: 'add', track: null };
  }
  
  let hour1Tracks = $derived(ep?.tracks.filter(t => t.hour === 1) || []);
  let hour2Tracks = $derived(ep?.tracks.filter(t => t.hour === 2) || []);
  let otherTracks = $derived(ep?.tracks.filter(t => t.hour === 0) || []);
  
  function artistLink(name) {
    return (e) => { e.preventDefault(); router.goto(`/artist/${urlSegment(name)}`); };
  }
  
  function back(e) {
    e.preventDefault();
    router.goto('/episodes');
  }
</script>

<TrackEditor 
  show={editor.show} 
  onshowchange={(val) => editor.show = val}
  mode={editor.mode} 
  track={editor.track} 
  episodeId={ep?.broadcast} 
  onSave={load} 
/>

{#if loading}
  <div class="loading-pulse"><div class="pulse-block" style="height:400px"></div></div>
{:else if ep}
  <div class="page">
    <a href="#/episodes" onclick={back} class="back-link">← All Episodes</a>
    
    <header class="ep-header">
      <div class="header-main">
        <h1 class="ep-title">{#if ep.broadcast}#{ep.broadcast}{:else}{ep.date}{/if}</h1>
        <p class="ep-date">{ep.date}</p>
      </div>
      
      {#if ep.stats}
        <div class="stat-bar">
          <div class="stat-item">
            <span class="stat-num accent">{ep.stats.track_count}</span>
            <span class="stat-lab">Tracks</span>
          </div>
          <div class="stat-item">
            <span class="stat-num">{ep.stats.unique_artists}</span>
            <span class="stat-lab">Unique Artists</span>
          </div>
          <div class="stat-item">
            <span class="stat-num gold">{ep.stats.repeat_rate}%</span>
            <span class="stat-lab">Repeat Rate</span>
          </div>
        </div>
      {/if}
    </header>
    
    <!-- Track Listing -->
    <section class="card">
      <div class="card-header">
        <h2 class="section-title">Track Listing</h2>
        {#if auth.authed}
        <button class="add-btn-icon" onclick={addTrack} title="Add Track">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        </button>
        {/if}
      </div>
      
      {#if otherTracks.length > 0}
        <div class="hour-section">
          <h3 class="hour-label">Uncategorized</h3>
          {#each otherTracks as t}
            <div class="track-row">
              <span class="track-pos">{t.position}.</span>
              <a href="#/artist/{urlSegment(t.artist)}" onclick={artistLink(t.artist)} class="track-artist">{t.artist}</a>
              <span class="track-sep">—</span>
              <span class="track-title">{t.title}</span>
              {#if t.artist_first || t.track_first}
                <span class="debut-badge" title="{t.artist_first ? 'Artist debuts here' : ''}{t.artist_first && t.track_first ? ' — ' : ''}{t.track_first ? 'First play' : ''}">★</span>
              {/if}
              {#if t.album}
                <span class="track-album"> / <a href="#/album/{urlSegment(t.artist)}/{urlSegment(t.album)}" onclick={router.navigate}>{t.album}</a></span>
              {/if}
              <div class="track-actions">
                {#if auth.authed}
                <button class="edit-btn-icon" onclick={() => editTrack(t)} title="Edit Track">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
                {/if}
                <TrackSearchLinks artist={t.artist} title={t.title} />
              </div>
            </div>
          {/each}
        </div>
      {/if}
      
      {#if hour1Tracks.length > 0}
        <div class="hour-section">
          <h3 class="hour-label">Hour 1</h3>
          {#each hour1Tracks as t}
            <div class="track-row">
              <span class="track-pos">{t.position}.</span>
              <a href="#/artist/{urlSegment(t.artist)}" onclick={artistLink(t.artist)} class="track-artist">{t.artist}</a>
              <span class="track-sep">—</span>
              <span class="track-title">{t.title}</span>
              {#if t.artist_first || t.track_first}
                <span class="debut-badge" title="{t.artist_first ? 'Artist debuts here' : ''}{t.artist_first && t.track_first ? ' — ' : ''}{t.track_first ? 'First play' : ''}">★</span>
              {/if}
              {#if t.album}
                <span class="track-album"> / <a href="#/album/{urlSegment(t.artist)}/{urlSegment(t.album)}" onclick={router.navigate}>{t.album}</a></span>
              {/if}
              <div class="track-actions">
                {#if auth.authed}
                <button class="edit-btn-icon" onclick={() => editTrack(t)} title="Edit Track">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
                {/if}
                <TrackSearchLinks artist={t.artist} title={t.title} />
              </div>
            </div>
          {/each}
        </div>
      {/if}
      
      {#if hour2Tracks.length > 0}
        <div class="hour-section">
          <h3 class="hour-label">Hour 2</h3>
          {#each hour2Tracks as t}
            <div class="track-row">
              <span class="track-pos">{t.position}.</span>
              <a href="#/artist/{urlSegment(t.artist)}" onclick={artistLink(t.artist)} class="track-artist">{t.artist}</a>
              <span class="track-sep">—</span>
              <span class="track-title">{t.title}</span>
              {#if t.artist_first || t.track_first}
                <span class="debut-badge" title="{t.artist_first ? 'Artist debuts here' : ''}{t.artist_first && t.track_first ? ' — ' : ''}{t.track_first ? 'First play' : ''}">★</span>
              {/if}
              {#if t.album}
                <span class="track-album"> / <a href="#/album/{urlSegment(t.artist)}/{urlSegment(t.album)}" onclick={router.navigate}>{t.album}</a></span>
              {/if}
              <div class="track-actions">
                {#if auth.authed}
                <button class="edit-btn-icon" onclick={() => editTrack(t)} title="Edit Track">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
                {/if}
                <TrackSearchLinks artist={t.artist} title={t.title} />
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </section>
    
    <!-- Bandcamp Links -->
    {#if ep.bandcamp_links.length > 0}
      <section class="card">
        <h2 class="section-title">📢 Henry Recommends</h2>
        <div class="bc-list">
          {#each ep.bandcamp_links as link}
            <a href={link.url} target="_blank" rel="noopener" class="bc-link">
              <span class="bc-icon">🎵</span>
              <span class="bc-url">{link.url.replace('https://', '')}</span>
              <span class="bc-arrow">↗</span>
            </a>
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
  
  .ep-header { margin-bottom: 2rem; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: 1rem; }
  .ep-title { font-size: 2.5rem; font-weight: 800; margin: 0; }
  .ep-date { font-size: 1.1rem; color: var(--color-henry-300); margin: 0.3rem 0 0; }
  
  .stat-bar { display: flex; gap: 2rem; margin: 1.5rem 0; flex-wrap: wrap; }
  .stat-item { display: flex; flex-direction: column; }
  .stat-num { font-size: 1.8rem; font-weight: 800; }
  .stat-lab { font-size: 0.75rem; color: var(--color-henry-300); text-transform: uppercase; letter-spacing: 0.05em; }
  .accent { color: var(--color-accent); }
  .gold { color: var(--color-gold); }
  
  .card { background: var(--color-henry-800); border: 1px solid var(--color-henry-600); border-radius: 12px; padding: 1.5rem; margin-bottom: 1rem; }
  .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
  .section-title { font-size: 1.1rem; font-weight: 700; margin: 0; }
  .add-btn-icon {
    background: transparent;
    border: none;
    color: var(--color-henry-400);
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
  }
  .add-btn-icon:hover { background: var(--color-henry-600); color: var(--color-accent); }
  
  .hour-section { margin-bottom: 1.5rem; }
  .hour-section:last-child { margin-bottom: 0; }
  .hour-label {
    font-size: 0.85rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--color-henry-400);
    margin: 0 0 0.5rem;
    padding-bottom: 0.3rem;
    border-bottom: 1px solid var(--color-henry-700);
  }
  
  .track-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.4rem 0.5rem;
    border-radius: 4px;
    font-size: 0.9rem;
    transition: background 0.1s;
  }
  .track-row:hover { background: var(--color-henry-700); }
  .track-pos { color: var(--color-henry-400); min-width: 2rem; text-align: right; font-size: 0.8rem; }
  .track-artist { color: var(--color-accent); text-decoration: none; font-weight: 600; white-space: nowrap; }
  .track-artist:hover { text-decoration: underline; }
  .track-sep { color: var(--color-henry-400); }
  .track-title { font-weight: 500; }
  .track-album { color: var(--color-henry-300); font-size: 0.85rem; }
  .track-album a { color: var(--color-henry-300); text-decoration: none; }
  .track-album a:hover { color: var(--color-accent); text-decoration: underline; }
  
  .track-actions { margin-left: auto; padding-left: 1rem; display: flex; align-items: center; gap: 0.5rem; }
  .edit-btn-icon {
    background: transparent;
    border: none;
    color: var(--color-henry-400);
    padding: 4px;
    cursor: pointer;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .edit-btn-icon:hover { background: var(--color-henry-600); color: var(--color-accent); }

  .bc-list { display: flex; flex-direction: column; gap: 0.3rem; }
  .bc-link {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0.5rem;
    border-radius: 6px;
    text-decoration: none;
    color: var(--color-henry-100);
    transition: background 0.15s;
  }
  .bc-link:hover { background: var(--color-henry-700); }
  .bc-icon { font-size: 0.9rem; }
  .bc-url { flex: 1; font-size: 0.85rem; color: var(--color-henry-200); }
  .bc-arrow { color: var(--color-henry-400); }
  
  .loading-pulse { padding: 2rem 0; }
  .pulse-block { background: var(--color-henry-800); border-radius: 12px; animation: pulse 1.5s ease-in-out infinite; }
  @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.7; } }
  
  .debut-badge {
    display: inline-flex; align-items: center; justify-content: center;
    margin-left: 0.4rem; font-size: 0.7rem;
    color: var(--color-gold, #eac117); cursor: default;
    animation: glow-pulse 2s ease-in-out infinite;
  }
  @keyframes glow-pulse {
    0%, 100% { opacity: 0.6; transform: scale(1); }
    50% { opacity: 1; transform: scale(1.2); }
  }
</style>
