<script>
  import { router } from '../router.svelte.js';
  
  let searchQuery = $state('');
  
  function onSearch(e) {
    e.preventDefault();
    if (searchQuery.trim()) {
      router.goto(`/search/${encodeURIComponent(searchQuery.trim())}`);
    }
  }
</script>

<nav class="nav">
  <div class="nav-inner">
    <a href="#/" onclick={router.navigate} class="logo">
      <span class="logo-text"><span class="logo-highlight font-bold bold italic">FANATIC!</span></span>
    </a>
    
    <div class="nav-right">
      <form onsubmit={onSearch} class="search-form">
        <input
          type="search"
          placeholder="Search artists, albums, tracks…"
          bind:value={searchQuery}
          class="search-input"
        />
      </form>
      
      <div class="nav-links">
        <a href="#/artists" onclick={router.navigate} class="nav-link">Artists</a>
        <a href="#/albums" onclick={router.navigate} class="nav-link">Albums</a>
        <a href="#/episodes" onclick={router.navigate} class="nav-link">Episodes</a>
        <a href="#/tracks" onclick={router.navigate} class="nav-link">Tracks</a>
        <a href="#/recommends" onclick={router.navigate} class="nav-link">Recommends</a>
      </div>
    </div>
  </div>
</nav>

<style>
  .nav {
    position: sticky;
    top: 0;
    z-index: 100;
    background: rgba(10, 10, 15, 0.9);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--color-henry-600);
  }
  .nav-inner {
    max-width: 1280px;
    margin: 0 auto;
    padding: 0 1.5rem;
    height: 60px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .logo {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    text-decoration: none;
    color: var(--color-henry-100);
    font-weight: 700;
    font-size: 1.1rem;
  }
  .logo-highlight { color: var(--color-accent); }
  .nav-right {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
  .search-form { margin: 0; }
  .search-input {
    padding: 0.35rem 0.75rem;
    border-radius: 8px;
    border: 1px solid var(--color-henry-600);
    background: var(--color-henry-800);
    color: var(--color-henry-100);
    font-size: 0.8rem;
    width: 200px;
    outline: none;
    transition: all 0.2s;
  }
  .search-input:focus {
    border-color: var(--color-accent);
    width: 260px;
  }
  .search-input::placeholder { color: var(--color-henry-400); }
  .nav-links {
    display: flex;
    gap: 0.25rem;
  }
  .nav-link {
    padding: 0.4rem 0.9rem;
    border-radius: 6px;
    text-decoration: none;
    color: var(--color-henry-300);
    font-size: 0.9rem;
    font-weight: 500;
    transition: all 0.2s;
  }
  .nav-link:hover {
    color: var(--color-henry-100);
    background: var(--color-henry-700);
  }
</style>
