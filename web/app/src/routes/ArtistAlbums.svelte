<script>
  import { onMount } from 'svelte';
  import { api } from '../lib/api.js';
  import { router, urlSegment } from '../lib/router.svelte.js';
  import AlbumCard from '../lib/components/AlbumCard.svelte';

  let { params = {} } = $props();
  let artistName = $derived(params.name);

  let albums = $state([]);
  let artist = $state('');
  let loading = $state(true);
  let error = $state(null);
  let searchTerm = $state('');

  let filteredAlbums = $derived(
    searchTerm 
      ? albums.filter(a => a.album.toLowerCase().includes(searchTerm.toLowerCase()))
      : albums
  );

  onMount(async () => {
    try {
      const data = await api.artistAlbums(artistName);
      albums = data.items;
      artist = data.artist;
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  });

  function back(e) {
    e.preventDefault();
    router.goto(`/artist/${urlSegment(artistName)}`);
  }
</script>

{#if loading}
  <div class="loading-wrap">
    <div class="loading-pulse"><div class="pulse-block" style="height:300px"></div></div>
  </div>
{:else if error}
  <div class="page error-container">
    <a href="#/artist/{urlSegment(artistName)}" onclick={back} class="back-link">← Back to {artistName}</a>
    <div class="error-box">
      <h2>Something went wrong</h2>
      <p class="error-msg">{error}</p>
      <button class="retry-btn" onclick={() => window.location.reload()}>Retry</button>
    </div>
  </div>
{:else}
  <div class="page">
    <a href="#/artist/{urlSegment(artistName)}" onclick={back} class="back-link">← Back to {artist}</a>
    
    <header class="page-header">
      <div class="title-section">
        <h1>{artist}'s Albums</h1>
        <p class="subtitle">{albums.length} albums documented in the archive</p>
      </div>
      
      {#if albums.length > 12}
        <div class="search-box">
          <input 
            type="text" 
            placeholder="Search albums..." 
            bind:value={searchTerm}
            class="filter-input"
          />
        </div>
      {/if}
    </header>

    {#if filteredAlbums.length === 0}
      <div class="no-results">
        <p>No albums matching "{searchTerm}"</p>
        <button class="clear-btn" onclick={() => searchTerm = ''}>Clear search</button>
      </div>
    {:else}
      <div class="album-grid">
        {#each filteredAlbums as alb}
          <AlbumCard album={alb} />
        {/each}
      </div>
    {/if}
  </div>
{/if}

<style>
  .page { animation: fadeIn 0.3s ease-out; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  
  .back-link { 
    color: var(--color-henry-300); 
    text-decoration: none; 
    font-size: 0.9rem; 
    margin-bottom: 1.5rem; 
    display: inline-block;
    transition: color 0.2s;
  }
  .back-link:hover { color: var(--color-accent); }
  
  .page-header { 
    margin-bottom: 2rem; 
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 1rem;
    flex-wrap: wrap;
  }
  .page-header h1 { margin: 0; font-size: 2rem; font-weight: 800; letter-spacing: -0.02em; }
  .subtitle { margin: 0.4rem 0 0; color: var(--color-henry-300); font-size: 1rem; font-weight: 500; }

  .search-box { width: 100%; max-width: 300px; }
  .filter-input {
    width: 100%;
    padding: 0.6rem 1rem;
    background: var(--color-henry-800);
    border: 1px solid var(--color-henry-600);
    border-radius: 8px;
    color: var(--color-henry-100);
    font-size: 0.9rem;
    transition: all 0.2s;
  }
  .filter-input:focus {
    outline: none;
    border-color: var(--color-accent);
    box-shadow: 0 0 0 2px rgba(255, 107, 53, 0.2);
  }

  .album-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 1.5rem;
  }
  
  .no-results {
    padding: 4rem 2rem;
    text-align: center;
    background: var(--color-henry-800);
    border-radius: 12px;
    border: 1px dashed var(--color-henry-600);
  }
  
  .clear-btn {
    margin-top: 1rem;
    background: transparent;
    border: 1px solid var(--color-accent);
    color: var(--color-accent);
    padding: 0.4rem 1rem;
    border-radius: 6px;
    cursor: pointer;
    font-weight: 600;
  }
  
  /* Error styles */
  .error-container { text-align: center; padding-top: 3rem; }
  .error-box {
    background: var(--color-henry-800);
    border: 1px solid #ff444466;
    padding: 2.5rem;
    border-radius: 16px;
    max-width: 500px;
    margin: 0 auto;
  }
  .error-box h2 { color: #ff4444; margin-top: 0; }
  .error-msg { font-family: monospace; background: #000; padding: 0.75rem; border-radius: 8px; margin: 1rem 0; color: #ffaaaa; }
  .retry-btn {
    background: var(--color-accent);
    color: white;
    border: none;
    padding: 0.6rem 1.5rem;
    border-radius: 8px;
    font-weight: 700;
    cursor: pointer;
    margin-top: 1rem;
  }

  .loading-wrap { padding: 2rem 0; }
  .loading-pulse { width: 100%; }
  .pulse-block { background: var(--color-henry-800); border-radius: 12px; animation: pulse 1.5s ease-in-out infinite; }
  @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.7; } }
</style>
