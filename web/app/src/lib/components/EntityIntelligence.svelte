<script>
  let { entityType, id, name, onEdit } = $props();
  let tracks = $state([]);
  let loading = $state(true);

  $effect(() => {
    loadDetails();
  });

  async function loadDetails() {
    loading = true;
    const endpoint = entityType === 'artist' 
        ? `/api/artists/tracks-by-id/${id}` 
        : `/api/albums/tracks-by-id/${id}`;
    console.log("Fetching tracks from:", endpoint);
    try {
        const res = await fetch(endpoint);
        if (!res.ok) throw new Error('API returned ' + res.status);
        tracks = await res.json();
        console.log("Fetched tracks:", tracks);
    } catch(e) {
        console.error("EntityIntelligence error:", e);
    }
    loading = false;
  }
</script>

<div class="entity-intelligence">
  <h4>Track Audit ({tracks.length} tracks)</h4>
  {#if loading}
    <p>Loading...</p>
  {:else}
    <div class="track-list">
      {#each tracks as t}
        <div class="track-audit-row">
          <span class="info">{t.artist} — {t.title} <span class="muted">({t.album})</span></span>
          <button class="small-btn" onclick={() => onEdit(t)}>Edit</button>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .entity-intelligence { background: #1a1a2e; padding: 1rem; border-radius: 8px; margin-top: 1rem; }
  .track-audit-row { display: flex; justify-content: space-between; padding: 0.4rem 0; border-bottom: 1px solid #333; font-size: 0.85rem; }
  .muted { color: #888; }
  .small-btn { padding: 0.2rem 0.5rem; background: var(--color-henry-600); border: none; color: white; border-radius: 4px; cursor: pointer; }
</style>
