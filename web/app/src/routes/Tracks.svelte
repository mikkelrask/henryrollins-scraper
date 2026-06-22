<script>
  import { onMount } from 'svelte';
  import { api } from '../lib/api.js';
  import { router, urlSegment } from '../lib/router.svelte.js';
  import TrackSearchLinks from '../lib/components/TrackSearchLinks.svelte';

  let tracks = $state([]);
  let total = $state(0);
  let totalEpisodes = $state(496);
  let page = $state(Number(router.current?.query?.page) || 1);
  let search = $state(router.current?.query?.search || '');
  let sort = $state(router.current?.query?.sort || '-plays');
  let loading = $state(true);
  const perPage = 50;

  async function load() {
    loading = true;
    try {
      const data = await api.tracks(page, perPage, sort, search);
      tracks = data.items;
      total = data.total;
      totalEpisodes = data.total_episodes ?? 496;
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  }

  onMount(load);

  function updateUrl() {
    const params = new URLSearchParams();
    params.set('page', page);
    params.set('sort', sort);
    if (search) params.set('search', search);
    const qs = '/tracks?' + params.toString();
    if (qs === window.location.hash.replace('#', '')) return;
    router.goto(qs);
  }

  let debounceTimer;
  function onSearch(e) {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      search = e.target.value;
      page = 1;
      updateUrl();
    }, 300);
  }

  function toggleSort(col) {
    if (sort === col) sort = `-${col}`;
    else if (sort === `-${col}`) sort = col;
    else sort = `-${col}`;
    page = 1;
    updateUrl();
  }

  function sortIcon(col) {
    if (sort === col) return ' ▲';
    if (sort === `-${col}`) return ' ▼';
    return '';
  }

  function artistLink(name) {
    return (e) => { e.preventDefault(); e.stopPropagation(); router.goto(`/artist/${urlSegment(name)}`); };
  }
</script>

<div class="page">
  <header class="page-header">
    <div>
      <h1>🎵 Tracks</h1>
      <p class="subtitle">{total.toLocaleString()} tracks played across {totalEpisodes} episodes</p>
    </div>
    <input type="search" placeholder="Search tracks or artists..." value={search} oninput={onSearch} class="search-input" />
  </header>

  <div class="table-wrap">
    <table class="data-table">
      <thead>
        <tr>
          <th class="sortable" onclick={() => toggleSort('title')}>Track{sortIcon('title')}</th>
          <th class="sortable" onclick={() => toggleSort('artist')}>Artist{sortIcon('artist')}</th>
          <th class="sortable" onclick={() => toggleSort('album')}>Album{sortIcon('album')}</th>
          <th class="sortable right" onclick={() => toggleSort('plays')}>Plays{sortIcon('plays')}</th>
          <th class="right">Episodes</th>
          <th>Last Played</th>
          <th class="right">Listen</th>
        </tr>
      </thead>
      <tbody>
        {#if loading}
          <tr><td colspan="7" class="loading-cell">Loading…</td></tr>
        {:else if tracks.length === 0}
          <tr><td colspan="7" class="loading-cell">No tracks found</td></tr>
        {:else}
          {#each tracks as t}
            <tr>
              <td class="track-title">{t.title}</td>
              <td class="artist-cell"><span onclick={artistLink(t.artist)} class="artist-link" role="link" tabindex="0">{t.artist}</span></td>
              <td class="album-cell">{#if t.album}<a href="#/album/{urlSegment(t.artist)}/{urlSegment(t.album)}" onclick={router.navigate} class="album-link">{t.album}</a>{/if}</td>
              <td class="right bold">{t.plays}</td>
              <td class="right muted">{t.episodes}</td>
              <td class="muted">{t.last_played || '—'}</td>
              <td class="right">
                <TrackSearchLinks artist={t.artist} title={t.title} />
              </td>
            </tr>
          {/each}
        {/if}
      </tbody>
    </table>
  </div>

  {#if Math.ceil(total / perPage) > 1}
    <div class="pagination">
      <button disabled={page <= 1} onclick={() => { page--; updateUrl(); }}>← Prev</button>
      <span class="page-info">Page {page} of {Math.ceil(total / perPage)}</span>
      <button disabled={page >= Math.ceil(total / perPage)} onclick={() => { page++; updateUrl(); }}>Next →</button>
    </div>
  {/if}
</div>

<style>
  .page { animation: fadeIn 0.3s ease-out; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  .page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem; }
  .page-header h1 { margin: 0; font-size: 1.8rem; }
  .subtitle { margin: 0.3rem 0 0; color: var(--color-henry-300); font-size: 0.9rem; }
  .search-input { padding: 0.5rem 1rem; border-radius: 8px; border: 1px solid var(--color-henry-600); background: var(--color-henry-800); color: var(--color-henry-100); font-size: 0.9rem; min-width: 250px; outline: none; transition: border-color 0.2s; }
  .search-input:focus { border-color: var(--color-accent); }
  .table-wrap { overflow-x: auto; background: var(--color-henry-800); border: 1px solid var(--color-henry-600); border-radius: 12px; }
  .data-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  .data-table th { text-align: left; padding: 0.75rem 1rem; font-weight: 600; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-henry-300); background: var(--color-henry-700); border-bottom: 1px solid var(--color-henry-600); user-select: none; white-space: nowrap; }
  .data-table td { padding: 0.6rem 1rem; border-bottom: 1px solid var(--color-henry-700); vertical-align: middle; white-space: nowrap; }
  .data-table tr:last-child td { border-bottom: none; }
  .sortable { cursor: pointer; }
  .sortable:hover { color: var(--color-henry-100); }
  .right { text-align: right; }
  .bold { font-weight: 700; color: var(--color-accent); }
  .muted { color: var(--color-henry-300); }
  .loading-cell { text-align: center; padding: 3rem; color: var(--color-henry-300); }
  .track-title { font-weight: 600; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .artist-cell { }
  .artist-link { color: var(--color-henry-200); cursor: pointer; text-decoration: none; }
  .artist-link:hover { color: var(--color-accent); text-decoration: underline; }
  .album-link { color: var(--color-henry-200); text-decoration: none; }
  .album-link:hover { color: var(--color-accent); text-decoration: underline; }
  .pagination { display: flex; justify-content: center; align-items: center; gap: 1rem; margin-top: 1rem; }
  .pagination button { padding: 0.4rem 1rem; border-radius: 6px; border: 1px solid var(--color-henry-600); background: var(--color-henry-800); color: var(--color-henry-100); cursor: pointer; font-weight: 500; transition: all 0.15s; }
  .pagination button:hover:not(:disabled) { background: var(--color-henry-700); border-color: var(--color-accent); }
  .pagination button:disabled { opacity: 0.3; cursor: default; }
  .page-info { font-size: 0.85rem; color: var(--color-henry-300); }
</style>
