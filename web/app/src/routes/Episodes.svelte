<script>
  import { onMount } from 'svelte';
  import { api } from '../lib/api.js';
  import { router } from '../lib/router.svelte.js';
  
  let { params = {} } = $props();
  
  let episodes = $state([]);
  let total = $state(0);
  let page = $state(Number(router.current?.query?.page) || 1);
  let sort = $state(router.current?.query?.sort || '-broadcast');
  let loading = $state(true);
  const perPage = 25;
  
  async function load() {
    loading = true;
    try {
      const data = await api.episodes(page, perPage, sort);
      episodes = data.items;
      total = data.total;
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
    const qs = '/episodes?' + params.toString();
    if (qs === window.location.hash.replace('#', '')) return;
    router.goto(qs);
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
  
  function epLink(b) {
    return (e) => { e.preventDefault(); router.goto(`/episode/${b}`); };
  }
</script>

<div class="page">
  <header class="page-header">
    <div>
      <h1>📻 Episodes</h1>
      <p class="subtitle">{total} episodes spanning 2017–2026</p>
    </div>
  </header>
  
  <div class="table-wrap">
    <table class="data-table">
      <thead>
        <tr>
          <th class="sortable" onclick={() => toggleSort('broadcast')}>#{sortIcon('broadcast')}</th>
          <th class="sortable" onclick={() => toggleSort('date')}>Date{sortIcon('date')}</th>
          <th>Title</th>
          <th class="sortable right" onclick={() => toggleSort('track_count')}>Tracks{sortIcon('track_count')}</th>
          <th class="right">Unique Artists</th>
          <th class="right">Repeat Rate</th>
        </tr>
      </thead>
      <tbody>
        {#if loading}
          <tr><td colspan="6" class="loading-cell">Loading…</td></tr>
        {:else if episodes.length === 0}
          <tr><td colspan="6" class="loading-cell">No episodes found</td></tr>
        {:else}
          {#each episodes as ep}
            <tr class="ep-row" onclick={epLink(ep.broadcast)}>
              <td class="ep-num">#{ep.broadcast}</td>
              <td class="ep-date">{ep.date}</td>
              <td class="ep-title">{ep.title}</td>
              <td class="right bold">{ep.track_count}</td>
              <td class="right muted">{ep.unique_artists}</td>
              <td class="right muted">{ep.repeat_rate}%</td>
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
  .page-header { margin-bottom: 1.5rem; }
  .page-header h1 { margin: 0; font-size: 1.8rem; }
  .subtitle { margin: 0.3rem 0 0; color: var(--color-henry-300); font-size: 0.9rem; }
  .table-wrap { overflow-x: auto; background: var(--color-henry-800); border: 1px solid var(--color-henry-600); border-radius: 12px; }
  .data-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  .data-table th { text-align: left; padding: 0.75rem 1rem; font-weight: 600; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-henry-300); background: var(--color-henry-700); border-bottom: 1px solid var(--color-henry-600); user-select: none; white-space: nowrap; }
  .data-table td { padding: 0.6rem 1rem; border-bottom: 1px solid var(--color-henry-700); white-space: nowrap; }
  .data-table tr:last-child td { border-bottom: none; }
  .sortable { cursor: pointer; }
  .sortable:hover { color: var(--color-henry-100); }
  .right { text-align: right; }
  .bold { font-weight: 700; color: var(--color-accent); }
  .muted { color: var(--color-henry-300); }
  .ep-row { cursor: pointer; transition: background 0.15s; }
  .ep-row:hover { background: var(--color-henry-700); }
  .ep-num { font-weight: 700; color: var(--color-accent); }
  .ep-date { color: var(--color-henry-300); }
  .ep-title { font-weight: 500; }
  .loading-cell { text-align: center; padding: 3rem; color: var(--color-henry-300); }
  .pagination { display: flex; justify-content: center; align-items: center; gap: 1rem; margin-top: 1rem; }
  .pagination button { padding: 0.4rem 1rem; border-radius: 6px; border: 1px solid var(--color-henry-600); background: var(--color-henry-800); color: var(--color-henry-100); cursor: pointer; font-weight: 500; transition: all 0.15s; }
  .pagination button:hover:not(:disabled) { background: var(--color-henry-700); border-color: var(--color-accent); }
  .pagination button:disabled { opacity: 0.3; cursor: default; }
  .page-info { font-size: 0.85rem; color: var(--color-henry-300); }
</style>
