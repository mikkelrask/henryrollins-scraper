<script>
  import { onMount } from 'svelte';
  import { api } from '../lib/api.js';
  import { router } from '../lib/router.svelte.js';
  
  let { params = {} } = $props();
  let query = $derived(params.query || '');
  
  let results = $state({ artists: [], albums: [], tracks: [] });
  let loading = $state(false);
  
  $effect(() => {
    if (query) {
      loadResults();
    }
  });
  
  async function loadResults() {
    loading = true;
    try {
      results = await api.search(query);
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  }
  
  function artistLink(name) {
    return (e) => { e.preventDefault(); router.goto(`/artist/${encodeURIComponent(name)}`); };
  }
</script>

<div class="page">
  <header class="page-header">
    <h1>Search: "{query}"</h1>
  </header>
  
  {#if loading}
    <div class="loading">Searching…</div>
  {:else}
    {#if results.artists.length > 0}
      <section class="card">
        <h2 class="section-title">🎸 Artists ({results.artists.length})</h2>
        <div class="results-list">
          {#each results.artists as a}
            <a href="#/artist/{encodeURIComponent(a.name)}" onclick={artistLink(a.name)} class="result-row">
              <span class="result-name">{a.name}</span>
              <span class="result-count">{a.plays} plays</span>
            </a>
          {/each}
        </div>
      </section>
    {/if}
    
    {#if results.albums.length > 0}
      <section class="card">
        <h2 class="section-title">💿 Albums ({results.albums.length})</h2>
        <div class="results-list">
          {#each results.albums as a}
            <a href="#/album/{encodeURIComponent(a.name)}" onclick={(e) => { e.preventDefault(); router.goto(`/album/${encodeURIComponent(a.name)}`); }} class="result-row">
              <div class="result-info">
                <span class="result-name">{a.name}</span>
                <span class="result-sub">{a.artist}</span>
              </div>
              <span class="result-count">{a.plays} plays</span>
            </a>
          {/each}
        </div>
      </section>
    {/if}
    
    {#if results.tracks.length > 0}
      <section class="card">
        <h2 class="section-title">🎵 Tracks ({results.tracks.length})</h2>
        <div class="results-list">
          {#each results.tracks as t}
            <a href="#/artist/{encodeURIComponent(t.artist)}" onclick={artistLink(t.artist)} class="result-row">
              <div class="result-info">
                <span class="result-name">{t.name}</span>
                <span class="result-sub">{t.artist}</span>
              </div>
              <span class="result-count">{t.plays} plays</span>
            </a>
          {/each}
        </div>
      </section>
    {/if}
    
    {#if !results.artists.length && !results.albums.length && !results.tracks.length}
      <div class="no-results">
        <p>No results found for "{query}". Try a different search term.</p>
      </div>
    {/if}
  {/if}
</div>

<style>
  .page { animation: fadeIn 0.3s ease-out; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  .page-header h1 { font-size: 1.5rem; margin: 0 0 1.5rem; }
  .loading { text-align: center; padding: 3rem; color: var(--color-henry-300); }
  
  .card { background: var(--color-henry-800); border: 1px solid var(--color-henry-600); border-radius: 12px; padding: 1.5rem; margin-bottom: 1rem; }
  .section-title { font-size: 1.1rem; font-weight: 700; margin: 0 0 1rem; }
  
  .results-list { display: flex; flex-direction: column; gap: 0.2rem; }
  .result-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0.5rem;
    border-radius: 6px;
    text-decoration: none;
    color: var(--color-henry-100);
    transition: background 0.15s;
  }
  .result-row:hover { background: var(--color-henry-700); }
  .result-info { flex: 1; }
  .result-name { font-weight: 600; display: block; }
  .result-sub { font-size: 0.8rem; color: var(--color-henry-300); }
  .result-count { font-weight: 700; color: var(--color-accent); }
  .no-results { text-align: center; padding: 3rem; color: var(--color-henry-300); }
</style>
