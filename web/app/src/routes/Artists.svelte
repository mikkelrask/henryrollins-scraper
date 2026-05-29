<script>
  import { api } from '../lib/api.js';
  import { router, urlSegment } from '../lib/router.svelte.js';
  import Badge from '../lib/components/Badge.svelte';
  
  let artists = $state([]);
  let total = $state(0);
  let page = $state(1);
  let search = $state('');
  let sort = $state('-plays');
  let loading = $state(true);
  let episodeCount = $state(0);
  const perPage = 50;

  // Filter badges from query params
  let countryFilter = $state(router.current?.query?.country || '');
  let genreFilter = $state(router.current?.query?.genre || '');

  // Dropdown data
  let countryOptions = $state([]);
  let genreOptions = $state([]);

  async function load() {
    loading = true;
    try {
      const [data, ov] = await Promise.all([
        api.artists(page, perPage, sort, search, countryFilter, genreFilter),
        api.overview()
      ]);
      artists = data.items;
      total = data.total;
      episodeCount = ov.episodes;
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  }

  async function loadFilters() {
    try {
      const [cRes, gRes] = await Promise.all([
        fetch('/api/stats/countries').then(r => r.json()),
        fetch('/api/stats/genres').then(r => r.json()),
      ]);
      countryOptions = cRes.items || [];
      genreOptions = (gRes.items || []).slice(0, 40);
    } catch (e) {
      console.error('Failed to load filter options:', e);
    }
  }

  // React to page, sort, or filter changes
  $effect(() => { page; sort; countryFilter; genreFilter; load(); });

  // Load filter options once on mount
  $effect(() => { loadFilters(); });

  function clearCountry() {
    countryFilter = '';
    page = 1;
    updateUrl();
  }

  function clearGenre() {
    genreFilter = '';
    page = 1;
    updateUrl();
  }

  function onCountryChange(e) {
    countryFilter = e.target.value;
    page = 1;
    updateUrl();
  }

  function onGenreChange(e) {
    genreFilter = e.target.value;
    page = 1;
    updateUrl();
  }

  function updateUrl() {
    const params = new URLSearchParams();
    if (countryFilter) params.set('country', countryFilter);
    if (genreFilter) params.set('genre', genreFilter);
    const qs = params.toString();
    router.goto('/artists' + (qs ? '?' + qs : ''));
  }
  
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
      router.goto(`/artist/${urlSegment(name)}`);
    };
  }

  function countryFlag(code) {
    if (!code || code.length !== 2) return '🌐';
    return String.fromCodePoint(
      code.charCodeAt(0) + 0x1F1E6 - 0x41,
      code.charCodeAt(1) + 0x1F1E6 - 0x41,
    );
  }
</script>

<div class="page">
  <header class="page-header">
    <div>
      <h1>🎸 Artists</h1>
      <p class="subtitle">
        {total.toLocaleString()} unique artists
        {#if countryFilter}
          from {countryFlag(countryFilter)} {countryFilter}
        {/if}
        {#if genreFilter}
          tagged "{genreFilter}"
        {/if}
        across {episodeCount.toLocaleString()} episodes
      </p>
    </div>
    <div class="header-actions">
      <select class="filter-select" value={countryFilter} onchange={onCountryChange}>
        <option value="">🌍 All countries</option>
        {#each countryOptions as c}
          <option value={c.code}>
            {c.code} {countryFlag(c.code)} ({c.count})
          </option>
        {/each}
      </select>

      <select class="filter-select" value={genreFilter} onchange={onGenreChange}>
        <option value="">🏷️ All genres</option>
        {#each genreOptions as g}
          <option value={g.name}>{g.name} ({g.count})</option>
        {/each}
      </select>

      {#if countryFilter}
        <button class="filter-badge" onclick={clearCountry}>
          <span>{countryFlag(countryFilter)} {countryFilter}</span>
          <span class="clear-x">×</span>
        </button>
      {/if}
      {#if genreFilter}
        <button class="filter-badge filter-genre" onclick={clearGenre}>
          <span>🏷️ {genreFilter}</span>
          <span class="clear-x">×</span>
        </button>
      {/if}

      <input
        type="search"
        placeholder="Search artists…"
        value={search}
        oninput={onSearch}
        class="search-input"
      />
    </div>
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
            <span class="col-hint" title="Bayesian Rollins Love Index (plays per episode, shrinkage-adjusted)">ⓘ</span>
          </th>
          <th class="sortable right" onclick={() => toggleSort('coverage')}>
            Coverage{sortIcon('coverage')}
            <span class="col-hint" title="Percentage of total episodes this artist appears in">ⓘ</span>
          </th>
          <th class="right">
            Diversity
            <span class="col-hint" title="Unique albums per episode — higher means more variety">ⓘ</span>
          </th>
          <th>Badge</th>
        </tr>
      </thead>
      <tbody>
        {#if loading}
          <tr>
            <td colspan="7" class="loading-cell">Loading…</td>
          </tr>
        {:else if artists.length === 0}
          <tr>
            <td colspan="7" class="loading-cell">No artists found</td>
          </tr>
        {:else}
          {#each artists as a}
            <tr class="artist-row" onclick={artistLink(a.artist)}>
              <td class="artist-name">{a.artist}</td>
              <td class="right bold accent">{a.plays}</td>
              <td class="right">{a.episodes}</td>
              <td class="right">{a.rli.toFixed(2)}</td>
              <td class="right">{a.coverage != null ? a.coverage.toFixed(1) + '%' : '—'}</td>
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

  .header-actions {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
  }

  .filter-badge {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.4rem 0.7rem;
    border-radius: 6px;
    border: 1px solid var(--color-accent);
    background: rgba(255, 107, 53, 0.1);
    color: var(--color-accent);
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
  }
  .filter-badge:hover {
    background: rgba(255, 107, 53, 0.2);
  }
  .filter-badge.filter-genre {
    border-color: #50c878;
    background: rgba(80, 200, 120, 0.1);
    color: #50c878;
  }
  .filter-badge.filter-genre:hover {
    background: rgba(80, 200, 120, 0.2);
  }
  .filter-badge .clear-x {
    font-size: 1rem;
    line-height: 1;
    margin-left: 0.2rem;
  }

  .filter-select {
    padding: 0.5rem 1.8rem 0.5rem 0.7rem;
    border-radius: 8px;
    border: 1px solid var(--color-henry-600);
    background: var(--color-henry-800);
    color: var(--color-henry-100);
    font-size: 0.85rem;
    outline: none;
    cursor: pointer;
    appearance: none;
    -webkit-appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%23998877' viewBox='0 0 16 16'%3E%3Cpath d='M7.247 11.14 2.451 5.658C1.885 5.013 2.345 4 3.204 4h9.592a1 1 0 0 1 .753 1.659l-4.796 5.48a1 1 0 0 1-1.506 0z'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 0.6rem center;
    transition: border-color 0.2s;
  }
  .filter-select:focus {
    border-color: var(--color-accent);
  }
  .filter-select option {
    background: var(--color-henry-800);
    color: var(--color-henry-100);
  }

  .table-wrap {
    overflow-x: auto;
    background: var(--color-henry-800);
    border: 1px solid var(--color-henry-600);
    border-radius: 12px;
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
    white-space: nowrap;
  }
  .data-table td {
    padding: 0.6rem 1rem;
    border-bottom: 1px solid var(--color-henry-700);
    white-space: nowrap;
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
