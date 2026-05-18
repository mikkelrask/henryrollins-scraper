<script>
  let { album } = $props();
</script>

<a href="#/album/{encodeURIComponent(album.artist).replace(/%2F/g, '~~')}/{encodeURIComponent(album.album).replace(/%2F/g, '~~')}" class="album-card">
  <div class="art-container">
    {#if album.artwork_url}
      <img src={album.artwork_url} alt={album.album} loading="lazy" class="album-art" />
    {:else}
      <div class="art-placeholder">💿</div>
    {/if}
    <div class="art-overlay">
      <span class="play-badge">{album.plays} plays</span>
    </div>
  </div>
  <div class="album-info">
    <span class="grid-album-name" title={album.album}>{album.album}</span>
    <span class="grid-artist-name">{album.artist}</span>
    <div class="card-stats">
      <span class="stat-pill">{album.distinct_tracks} tracks</span>
      <span class="stat-pill accent">{album.plays} plays</span>
    </div>
  </div>
</a>

<style>
  .album-card {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    text-decoration: none;
    color: var(--color-henry-100);
    transition: transform 0.2s;
  }
  .album-card:hover { transform: translateY(-4px); }
  
  .art-container {
    position: relative;
    aspect-ratio: 1/1;
    background: var(--color-henry-800);
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    border: 1px solid var(--color-henry-600);
  }
  .album-art { width: 100%; height: 100%; object-fit: cover; }
  .art-placeholder { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 2.5rem; background: var(--color-henry-700); }
  
  .art-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(to top, rgba(0,0,0,0.7) 0%, transparent 40%);
    opacity: 0;
    transition: opacity 0.2s;
    display: flex;
    align-items: flex-end;
    padding: 0.75rem;
  }
  .album-card:hover .art-overlay { opacity: 1; }
  .play-badge {
    background: var(--color-accent);
    color: white;
    font-size: 0.7rem;
    font-weight: 800;
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    text-transform: uppercase;
  }
  
  .album-info { display: flex; flex-direction: column; gap: 0.3rem; }
  .grid-album-name { font-weight: 700; font-size: 0.95rem; line-height: 1.2; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .grid-artist-name { font-size: 0.8rem; color: var(--color-henry-400); font-weight: 500; }
  .album-card:hover .grid-album-name { color: var(--color-accent); }

  .card-stats { display: flex; gap: 0.4rem; flex-wrap: wrap; margin-top: 0.25rem; }
  .stat-pill {
    font-size: 0.7rem;
    padding: 0.15rem 0.4rem;
    background: rgba(255,255,255,0.05);
    color: var(--color-henry-300);
    border-radius: 4px;
    font-weight: 600;
  }
  .stat-pill.accent {
    background: rgba(255, 107, 53, 0.1);
    color: var(--color-accent);
  }
</style>
