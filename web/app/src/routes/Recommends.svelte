<script>
  import { onMount } from 'svelte';
  import { api } from '../lib/api.js';
  import { router, urlSegment } from '../lib/router.svelte.js';
  

  
  let items = $state([]);
  let total = $state(0);
  let page = $state(1);
  let sort = $state('-episode_count');
  let linkType = $state('album');
  let loading = $state(true);
  let viewMode = $state('grid'); // 'grid' | 'table'
  const perPage = 30;
  
  async function load() {
    loading = true;
    try {
      const data = await api.recommends(page, perPage, sort, linkType);
      items = data.items;
      total = data.total;
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  }
  
  onMount(load);
  $effect(() => { page; sort; linkType; load(); });
  
  function toggleSort(col) {
    if (sort === col) sort = `-${col}`;
    else if (sort === `-${col}`) sort = col;
    else sort = `-${col}`;
    page = 1;
  }
  
  function artistLink(name) {
    return (e) => { e.preventDefault(); e.stopPropagation(); router.goto(`/artist/${urlSegment(name)}`); };
  }
  

</script>

<div class="page">
  <header class="page-header">
    <div>
      <h1>📢 Henry Recommends</h1>
      <p class="subtitle">{total} Bandcamp albums shared across 496 episodes. If Henry shares it, it's worth a listen.</p>
    </div>
  </header>
  
  <!-- Filters -->
  <div class="filter-bar">
    <div class="filter-pills">
      <button class="pill" class:pill-active={linkType === 'album'} onclick={() => { linkType = 'album'; page = 1; }}>
        🎵 Albums
      </button>
      <button class="pill" class:pill-active={linkType === 'label'} onclick={() => { linkType = 'label'; page = 1; }}>
        🏷️ Labels
      </button>
    </div>
    <div class="view-toggle">
      <button class="pill" class:pill-active={viewMode === 'grid'} onclick={() => viewMode = 'grid'}>Grid</button>
      <button class="pill" class:pill-active={viewMode === 'table'} onclick={() => viewMode = 'table'}>Table</button>
    </div>
    <div class="sort-options">
      <button class="pill" class:pill-active={sort === '-episode_count'} onclick={() => { sort = '-episode_count'; page = 1; }}>Most Shared</button>
      <button class="pill" class:pill-active={sort === '-last_seen'} onclick={() => { sort = '-last_seen'; page = 1; }}>Recent</button>
    </div>
  </div>
  
  {#if loading}
    <div class="loading-pulse"><div class="pulse-block" style="height:300px"></div></div>
  {:else}
    {#if viewMode === 'grid'}
      <div class="card-grid">
        {#each items as item}
          <a href={item.url} target="_blank" rel="noopener" class="bc-card">
            <div class="bc-card-art">
              <span class="bc-card-icon">🎵</span>
            </div>
            <div class="bc-card-body">
              <span onclick={artistLink(item.bandcamp_artist)} onkeydown={(e) => e.key === 'Enter' && artistLink(item.bandcamp_artist)()} class="bc-card-artist" role="link" tabindex="0">{item.bandcamp_artist}</span>
              <span class="bc-card-album">{item.album_title}</span>
              <div class="bc-card-meta">
                <span class="bc-card-count">{item.episode_count} episode{item.episode_count !== 1 ? 's' : ''}</span>
                <span class="bc-card-latest">latest: {item.last_seen}</span>
              </div>
              <div class="bc-card-eps">
                {#each item.episodes.slice(0, 5) as b}
                  <span role="button" tabindex="0" class="ep-chip" onclick={(e) => { e.preventDefault(); e.stopPropagation(); router.goto(`/episode/${b}`); }} onkeydown={(e) => e.key === 'Enter' && (e.preventDefault(), router.goto(`/episode/${b}`))}>
                    #{b}
                  </span>
                {/each}
                {#if item.episodes.length > 5}
                  <span class="ep-chip-more">+{item.episodes.length - 5}</span>
                {/if}
              </div>
            </div>
          </a>
        {/each}
      </div>
    {:else}
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th class="sortable" onclick={() => toggleSort('bandcamp_artist')}>Artist{sort.replace('-', '') === 'bandcamp_artist' ? (sort.startsWith('-') ? ' ▼' : ' ▲') : ''}</th>
              <th>Album</th>
              <th class="sortable right" onclick={() => toggleSort('episode_count')}>Episodes{sort.replace('-', '') === 'episode_count' ? (sort.startsWith('-') ? ' ▼' : ' ▲') : ''}</th>
              <th>First</th>
              <th>Latest</th>
            </tr>
          </thead>
          <tbody>
            {#each items as item}
              <tr class="bc-table-row">
                <td class="bc-tb-artist"><span onclick={artistLink(item.bandcamp_artist)} onkeydown={(e) => e.key === 'Enter' && artistLink(item.bandcamp_artist)()} role="link" tabindex="0" class="artist-link">{item.bandcamp_artist}</span></td>
                <td class="bc-tb-album"><span class="bc-row-link" role="button" tabindex="0" onclick={() => window.open(item.url, '_blank')} onkeydown={(e) => e.key === 'Enter' && window.open(item.url, '_blank')}>{item.album_title}</span></td>
                <td class="right bold">{item.episode_count}</td>
                <td class="muted">{item.first_seen}</td>
                <td class="muted">{item.last_seen}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
    
    {#if Math.ceil(total / perPage) > 1}
      <div class="pagination">
        <button disabled={page <= 1} onclick={() => page--}>← Prev</button>
        <span class="page-info">Page {page} of {Math.ceil(total / perPage)}</span>
        <button disabled={page >= Math.ceil(total / perPage)} onclick={() => page++}>Next →</button>
      </div>
    {/if}
  {/if}
</div>

<style>
  .page { animation: fadeIn 0.3s ease-out; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  
  .page-header { margin-bottom: 1rem; }
  .page-header h1 { margin: 0; font-size: 1.8rem; }
  .subtitle { margin: 0.3rem 0 0; color: var(--color-henry-300); font-size: 0.9rem; }
  
  .filter-bar {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
    flex-wrap: wrap;
    align-items: center;
  }
  .filter-pills, .view-toggle, .sort-options {
    display: flex;
    gap: 0.3rem;
  }
  .pill {
    padding: 0.3rem 0.7rem;
    border-radius: 16px;
    border: 1px solid var(--color-henry-600);
    background: var(--color-henry-800);
    color: var(--color-henry-300);
    font-size: 0.8rem;
    cursor: pointer;
    transition: all 0.15s;
  }
  .pill:hover { border-color: var(--color-henry-400); color: var(--color-henry-100); }
  .pill-active {
    background: var(--color-accent);
    border-color: var(--color-accent);
    color: var(--color-henry-900);
    font-weight: 600;
  }
  
  /* ── Card Grid ── */
  .card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem;
  }
  .bc-card {
    display: flex;
    gap: 0.75rem;
    background: var(--color-henry-800);
    border: 1px solid var(--color-henry-600);
    border-radius: 12px;
    padding: 1rem;
    text-decoration: none;
    color: var(--color-henry-100);
    transition: all 0.2s;
  }
  .bc-card:hover {
    border-color: var(--color-accent);
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(255,107,53,0.1);
  }
  .bc-card-art {
    width: 64px;
    height: 64px;
    border-radius: 8px;
    background: var(--color-henry-700);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .bc-card-icon { font-size: 1.5rem; }
  .bc-card-body {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }
  .bc-card-artist {
    font-weight: 700;
    font-size: 0.9rem;
    color: var(--color-accent);
  }
  .bc-card-album {
    font-weight: 600;
    font-size: 0.95rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .bc-card-meta {
    display: flex;
    gap: 0.5rem;
    font-size: 0.75rem;
    color: var(--color-henry-300);
  }
  .bc-card-count { font-weight: 600; color: var(--color-henry-200); }
  .bc-card-eps {
    display: flex;
    gap: 0.2rem;
    flex-wrap: wrap;
    margin-top: 0.2rem;
  }
  .ep-chip {
    padding: 0.1rem 0.4rem;
    border-radius: 4px;
    background: var(--color-henry-700);
    font-size: 0.65rem;
    font-weight: 600;
    color: var(--color-accent);
    cursor: pointer;
    transition: background 0.15s;
  }
  .ep-chip:hover { background: var(--color-henry-600); }
  .ep-chip-more {
    font-size: 0.65rem;
    color: var(--color-henry-400);
    padding: 0.1rem 0.3rem;
  }
  
  /* ── Table ── */
  .table-wrap { overflow-x: auto; background: var(--color-henry-800); border: 1px solid var(--color-henry-600); border-radius: 12px; }
  .data-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  .data-table th { text-align: left; padding: 0.75rem 1rem; font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-henry-300); background: var(--color-henry-700); border-bottom: 1px solid var(--color-henry-600); white-space: nowrap; }
  .data-table td { padding: 0.5rem 1rem; border-bottom: 1px solid var(--color-henry-700); white-space: nowrap; }
  .data-table tr:last-child td { border-bottom: none; }
  .sortable { cursor: pointer; user-select: none; }
  .sortable:hover { color: var(--color-henry-100); }
  .right { text-align: right; }
  .bold { font-weight: 700; color: var(--color-accent); }
  .muted { color: var(--color-henry-300); }
  .bc-table-row { cursor: pointer; transition: background 0.15s; }
  .bc-table-row:hover { background: var(--color-henry-700); }
  .bc-tb-artist { font-weight: 600; color: var(--color-accent); }
  
  .loading-pulse { padding: 2rem 0; }
  .pulse-block { background: var(--color-henry-800); border-radius: 12px; animation: pulse 1.5s ease-in-out infinite; }
  @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.7; } }
  
  .pagination { display: flex; justify-content: center; align-items: center; gap: 1rem; margin-top: 1rem; }
  .pagination button { padding: 0.4rem 1rem; border-radius: 6px; border: 1px solid var(--color-henry-600); background: var(--color-henry-800); color: var(--color-henry-100); cursor: pointer; font-weight: 500; }
  .pagination button:hover:not(:disabled) { background: var(--color-henry-700); border-color: var(--color-accent); }
  .pagination button:disabled { opacity: 0.3; cursor: default; }
  .page-info { font-size: 0.85rem; color: var(--color-henry-300); }
</style>
