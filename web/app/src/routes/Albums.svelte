<script>
  import { api } from '../lib/api.js';
  import { router } from '../lib/router.svelte.js';
  import AlbumCard from '../lib/components/AlbumCard.svelte';

  let viewMode = $state('grid'); // Default to grid for visual impact
  let albums = $state([]);
  let total = $state(0);
  let page = $state(1);
  let search = $state('');
  let sort = $state('-plays');
  let loading = $state(true);
  const perPage = 50;

  async function load() {
    loading = true;
    try {
      const data = await api.albums(page, perPage, sort, search);
      albums = data.items;
      total = data.total;
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  }

  $effect(() => { page; sort; load(); });

  let debounceTimer;
  function onSearch(e) {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      search = e.target.value;
      page = 1;
      load();
    }, 300);
  }

  function toggleSort(col) {
    if (sort === col) sort = `-${col}`;
    else if (sort === `-${col}`) sort = col;
    else sort = `-${col}`;
    page = 1;
  }

  function sortIcon(col) {
    if (sort === col) return ' ▲';
    if (sort === `-${col}`) return ' ▼';
    return '';
  }

  function albumLink(name) {
    return (e) => {
      e.preventDefault();
      router.goto(`/album/${encodeURIComponent(name)}`);
    };
  }
</script>

<div class="page">
  <header class="page-header">
    <div class="header-left">
      <h1>💿 Albums</h1>
      <p class="subtitle">Every album that's made it onto Henry's turntable</p>
    </div>
    <div class="header-actions">
      <div class="view-toggle">
        <button class:active={viewMode === 'grid'} onclick={() => viewMode = 'grid'} title="Grid View">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
        </button>
        <button class:active={viewMode === 'table'} onclick={() => viewMode = 'table'} title="Table View">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
        </button>
      </div>
      <input type="search" placeholder="Search albums or artists..." value={search} oninput={onSearch} class="search-input" />
    </div>
  </header>

  {#if loading && albums.length === 0}
    <div class="loading-state">
      <div class="spinner"></div>
      <p>Digging through the crates...</p>
    </div>
  {:else if albums.length === 0}
    <div class="empty-state">
      <p>No albums found matching "{search}"</p>
    </div>
  {:else}
    {#if viewMode === 'table'}
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th class="sortable" onclick={() => toggleSort('album')}>Album{sortIcon('album')}</th>
              <th class="sortable" onclick={() => toggleSort('artist')}>Artist{sortIcon('artist')}</th>
              <th class="sortable right" onclick={() => toggleSort('plays')}>Plays{sortIcon('plays')}</th>
              <th class="right">Tracks</th>
              <th class="sortable right" onclick={() => toggleSort('episodes')}>Episodes{sortIcon('episodes')}</th>
              <th>Last Played</th>
            </tr>
          </thead>
          <tbody>
            {#each albums as a}
              <tr class="album-row" onclick={albumLink(a.album)}>
                <td class="album-name">{a.album}</td>
                <td class="artist-name">
                  <a href="#/artist/{encodeURIComponent(a.artist)}" onclick={(e) => { e.stopPropagation(); router.navigate(e); }} class="artist-inline">
                    {a.artist}
                  </a>
                </td>
                <td class="right bold">{a.plays}</td>
                <td class="right muted">{a.distinct_tracks}</td>
                <td class="right muted">{a.episodes}</td>
                <td class="muted">{a.last_played || '-'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else}
      <div class="album-grid">
        {#each albums as a}
          <AlbumCard album={a} />
        {/each}
      </div>
    {/if}
  {/if}

  {#if Math.ceil(total / perPage) > 1}
    <div class="pagination">
      <button disabled={page <= 1} onclick={() => page--}>← Prev</button>
      <span class="page-info">Page {page} of {Math.ceil(total / perPage)}</span>
      <button disabled={page >= Math.ceil(total / perPage)} onclick={() => page++}>Next →</button>
    </div>
  {/if}
</div>

<style>
  .page { animation: fadeIn 0.3s ease-out; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  
  .page-header { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 2rem; flex-wrap: wrap; gap: 1.5rem; }
  .page-header h1 { margin: 0; font-size: 2.2rem; font-weight: 800; letter-spacing: -0.02em; }
  .subtitle { margin: 0.3rem 0 0; color: var(--color-henry-400); font-size: 0.95rem; font-weight: 500; }
  
  .header-actions { display: flex; align-items: center; gap: 1rem; }
  
  .view-toggle {
    display: flex;
    background: var(--color-henry-800);
    border: 1px solid var(--color-henry-600);
    border-radius: 8px;
    padding: 2px;
  }
  .view-toggle button {
    background: transparent;
    border: none;
    color: var(--color-henry-400);
    padding: 6px 10px;
    border-radius: 6px;
    cursor: pointer;
    display: flex;
    align-items: center;
    transition: all 0.2s;
  }
  .view-toggle button:hover { color: var(--color-henry-100); }
  .view-toggle button.active {
    background: var(--color-henry-600);
    color: var(--color-accent);
  }

  .search-input { padding: 0.6rem 1rem; border-radius: 8px; border: 1px solid var(--color-henry-600); background: var(--color-henry-800); color: var(--color-henry-100); font-size: 0.9rem; min-width: 280px; outline: none; transition: all 0.2s; }
  .search-input:focus { border-color: var(--color-accent); box-shadow: 0 0 0 2px rgba(255, 107, 53, 0.2); }
  
  /* ── Table View ── */
  .table-wrap { background: var(--color-henry-800); border: 1px solid var(--color-henry-600); border-radius: 12px; overflow: hidden; }
  .data-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  .data-table th { text-align: left; padding: 0.85rem 1rem; font-weight: 700; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--color-henry-400); background: rgba(255,255,255,0.02); border-bottom: 1px solid var(--color-henry-600); user-select: none; }
  .data-table td { padding: 0.75rem 1rem; border-bottom: 1px solid var(--color-henry-700); }
  .data-table tr:last-child td { border-bottom: none; }
  .sortable { cursor: pointer; }
  .sortable:hover { color: var(--color-accent); }
  .right { text-align: right; }
  .bold { font-weight: 700; color: var(--color-accent); }
  .muted { color: var(--color-henry-400); }
  .album-row { cursor: pointer; transition: background 0.15s; }
  .album-row:hover { background: var(--color-henry-700); }
  .album-name { font-weight: 600; color: var(--color-henry-100); }
  .artist-inline { color: var(--color-henry-300); text-decoration: none; }
  .artist-inline:hover { color: var(--color-accent); text-decoration: underline; }

  /* ── Grid View ── */
  .album-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 1.5rem;
  }

  .loading-state, .empty-state { text-align: center; padding: 5rem 0; color: var(--color-henry-400); }
  .spinner { width: 40px; height: 40px; border: 3px solid var(--color-henry-700); border-top-color: var(--color-accent); border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 1rem; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .pagination { display: flex; justify-content: center; align-items: center; gap: 1.5rem; margin-top: 3rem; padding-bottom: 2rem; }
  .pagination button { padding: 0.5rem 1.25rem; border-radius: 8px; border: 1px solid var(--color-henry-600); background: var(--color-henry-800); color: var(--color-henry-100); cursor: pointer; font-weight: 600; font-size: 0.9rem; transition: all 0.15s; }
  .pagination button:hover:not(:disabled) { background: var(--color-henry-700); border-color: var(--color-accent); color: var(--color-accent); }
  .pagination button:disabled { opacity: 0.3; cursor: default; }
  .page-info { font-size: 0.9rem; color: var(--color-henry-400); font-weight: 500; }
</style>
