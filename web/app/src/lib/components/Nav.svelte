<script>
  import { router, urlSegment } from '../router.svelte.js';
  
  let searchQuery = $state('');
  let menuOpen = $state(false);
  
  function onSearch(e) {
    e.preventDefault();
    if (searchQuery.trim()) {
      router.goto(`/search/${urlSegment(searchQuery.trim())}`);
    }
  }

  function closeMenu() {
    menuOpen = false;
  }

  function toggleMenu() {
    menuOpen = !menuOpen;
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
        <a href="#/tracks" onclick={() => { router.navigate(event); closeMenu(); }} class="nav-link">Tracks</a>
        <a href="#/albums" onclick={() => { router.navigate(event); closeMenu(); }} class="nav-link">Albums</a>
        <a href="#/artists" onclick={() => { router.navigate(event); closeMenu(); }} class="nav-link">Artists</a>
        <a href="#/episodes" onclick={() => { router.navigate(event); closeMenu(); }} class="nav-link">Episodes</a>
        <a href="#/insights" onclick={() => { router.navigate(event); closeMenu(); }} class="nav-link">Insights</a>
      </div>

      <button class="hamburger" onclick={toggleMenu} aria-label="Toggle menu">
        <span class="hamburger-line" class:open={menuOpen}></span>
        <span class="hamburger-line" class:open={menuOpen}></span>
        <span class="hamburger-line" class:open={menuOpen}></span>
      </button>
    </div>
  </div>

  {#if menuOpen}
    <div class="mobile-menu">
      <a href="#/tracks" onclick={() => { router.navigate(event); closeMenu(); }} class="mobile-link">Tracks</a>
      <a href="#/albums" onclick={() => { router.navigate(event); closeMenu(); }} class="mobile-link">Albums</a>
      <a href="#/artists" onclick={() => { router.navigate(event); closeMenu(); }} class="mobile-link">Artists</a>
      <a href="#/episodes" onclick={() => { router.navigate(event); closeMenu(); }} class="mobile-link">Episodes</a>
      <a href="#/insights" onclick={() => { router.navigate(event); closeMenu(); }} class="mobile-link">Insights</a>
    </div>
  {/if}
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

  .hamburger {
    display: none;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    gap: 4px;
    width: 32px;
    height: 32px;
    padding: 4px;
    border: none;
    background: transparent;
    cursor: pointer;
  }
  .hamburger-line {
    display: block;
    width: 22px;
    height: 2px;
    background: var(--color-henry-300);
    border-radius: 2px;
    transition: all 0.25s ease;
    transform-origin: center;
  }
  .hamburger-line.open:nth-child(1) {
    transform: translateY(6px) rotate(45deg);
  }
  .hamburger-line.open:nth-child(2) {
    opacity: 0;
  }
  .hamburger-line.open:nth-child(3) {
    transform: translateY(-6px) rotate(-45deg);
  }

  .mobile-menu {
    display: none;
    flex-direction: column;
    padding: 0.5rem 1.5rem 1rem;
    border-top: 1px solid var(--color-henry-600);
    background: rgba(10, 10, 15, 0.95);
  }
  .mobile-link {
    padding: 0.75rem 0;
    text-decoration: none;
    color: var(--color-henry-300);
    font-size: 1rem;
    font-weight: 500;
    border-bottom: 1px solid var(--color-henry-700);
    transition: color 0.2s;
  }
  .mobile-link:last-child { border-bottom: none; }
  .mobile-link:hover { color: var(--color-henry-100); }

  @media (max-width: 768px) {
    .nav-links { display: none; }
    .hamburger { display: flex; }
    .mobile-menu { display: flex; }
    .search-input {
      width: 120px;
    }
    .search-input:focus {
      width: 160px;
    }
  }
</style>
