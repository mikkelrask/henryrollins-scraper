<script>
  import { api } from '../lib/api.js';
  import { router } from '../lib/router.svelte.js';
  import Badge from '../lib/components/Badge.svelte';
  
  let artists = $state([]);
  let total = $state(0);
  let page = $state(1);
  let search = $state('');
  let sort = $state('-plays');
  let loading = $state(true);
  const perPage = 50;
  
  async function load() {
    loading = true;
    try {
      const data = await api.artists(page, perPage, sort, search);
      artists = data.items;
      total = data.total;
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  }
  
  // Single effect handles initial load + re-load on page/sort change
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
  
  function totalPages() {
    return Math.ceil(total / perPage);
  }
  
  function artistLink(name) {
    return (e) => {
      e.preventDefault();
      router.goto(`/artist/${encodeURIComponent(name)}`);
    };
  }
</script>

<div class="page">
  <header class="page-header">
    <div>
      <h1>🎸 Artists</h1>
      <p class="subtitle">{total.toLocaleString()} unique artists across {new Intl.NumberFormat().format(496)} episodes</p>
    </div>
    <input
      type="search"
      placeholder="Search artists…"
      value={search}
      oninput={onSearch}
      class="search-input"
    />
  </header>
  
  <div class="table-wrap">
    <table class="data-table">
      <thead>
        <tr>
          <th class="sortable" onclick={() => toggleSort('artist')}>
            Artist{sortIcon('artist')}
          </th>
          <th class="sortable right" onclick={() => toggleSort('plays')}>
            Plays{sortIcon('plays')}
          </th>
          <th class="sortable right" onclick={() => toggleSort('episodes')}>
            Episodes{sortIcon('episodes')}
          </th>
          <th class="sortable right" onclick={() => toggleSort('rli')}>
            RLI{sortIcon('rli')}
            <span class="col-hint" title="Rollins Love Index (plays per episode)">ⓘ</span>
          </th>
          <th class="right">Diversity</th>
          <th>Badge</th>
        </tr>
      </thead>
      <tbody>
        {#if loading}
          <tr>
            <td colspan="6" class="loading-cell">Loading…</td>
          </tr>
        {:else if artists.length === 0}
          <tr>
            <td colspan="6" class="loading-cell">No artists found</td>
          </tr>
        {:else}
          {#each artists as a}
            <tr class="artist-row" onclick={artistLink(a.artist)}>
              <td class="artist-name">{a.artist}</td>
              <td class="right bold accent">{a.plays}</td>
              <td class="right">{a.episodes}</td>
              <td class="right">{a.rli.toFixed(2)}</td>
              <td class="right muted">
                {#if a.album_diversity != null}
                  {a.album_diversity.toFixed(2)}
                {:else}
                  —
                {/if}
              </td>
              <td>
                {#if a.badge}
                  <Badge type={a.badge} />
                {/if}
              </td>
            </tr>
          {/each}
        {/if}
      </tbody>
    </table>
  </div>
  
  {#if totalPages() > 1}
    <div class="pagination">
      <button disabled={page <= 1} onclick={() => page--}>← Prev</button>
      <span class="page-info">Page {page} of {totalPages()}</span>
      <button disabled={page >= totalPages()} onclick={() => page++}>Next →</button>
    </div>
  {/if}
</div>

<style>
  .page { animation: fadeIn 0.3s ease-out; }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
  }
  
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 1.5rem;
    flex-wrap: wrap;
    gap: 1rem;
  }
  .page-header h1 { margin: 0; font-size: 1.8rem; }
  .subtitle { margin: 0.3rem 0 0; color: var(--color-henry-300); font-size: 0.9rem; }
  
  .search-input {
    padding: 0.5rem 1rem;
    border-radius: 8px;
    border: 1px solid var(--color-henry-600);
    background: var(--color-henry-800);
    color: var(--color-henry-100);
    font-size: 0.9rem;
    min-width: 250px;
    outline: none;
    transition: border-color 0.2s;
  }
  .search-input:focus {
    border-color: var(--color-accent);
  }
  
  .table-wrap {
    background: var(--color-henry-800);
    border: 1px solid var(--color-henry-600);
    border-radius: 12px;
    overflow: hidden;
  }
  .data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
  }
  .data-table th {
    text-align: left;
    padding: 0.75rem 1rem;
    font-weight: 600;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-henry-300);
    background: var(--color-henry-700);
    border-bottom: 1px solid var(--color-henry-600);
    user-select: none;
  }
  .data-table td {
    padding: 0.6rem 1rem;
    border-bottom: 1px solid var(--color-henry-700);
  }
  .data-table tr:last-child td { border-bottom: none; }
  
  .sortable { cursor: pointer; }
  .sortable:hover { color: var(--color-henry-100); }
  .right { text-align: right; }
  .bold { font-weight: 700; }
  .accent { color: var(--color-accent); }
  .muted { color: var(--color-henry-300); }
  .col-hint {
    cursor: help;
    font-size: 0.75rem;
    margin-left: 0.2rem;
    opacity: 0.6;
  }
  
  .artist-row { cursor: pointer; transition: background 0.15s; }
  .artist-row:hover { background: var(--color-henry-700); }
  .artist-name { font-weight: 600; }
  
  .loading-cell {
    text-align: center;
    padding: 3rem;
    color: var(--color-henry-300);
  }
  
  .pagination {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 1rem;
    margin-top: 1rem;
  }
  .pagination button {
    padding: 0.4rem 1rem;
    border-radius: 6px;
    border: 1px solid var(--color-henry-600);
    background: var(--color-henry-800);
    color: var(--color-henry-100);
    cursor: pointer;
    font-weight: 500;
    transition: all 0.15s;
  }
  .pagination button:hover:not(:disabled) {
    background: var(--color-henry-700);
    border-color: var(--color-accent);
  }
  .pagination button:disabled {
    opacity: 0.3;
    cursor: default;
  }
  .page-info { font-size: 0.85rem; color: var(--color-henry-300); }
</style>
