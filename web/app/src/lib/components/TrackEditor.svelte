<script>
  import { authFetch } from '../useAuth.svelte.js';

  let { show, onshowchange, mode = 'edit', track = null, episodeId = null, onSave, suggestions = [] } = $props();

  let formData = $state({
    artist: track?.artist || '',
    title: track?.title || '',
    album: track?.album || '',
    ...(track?.hour !== undefined && { hour: track.hour }),
    ...(track?.position !== undefined && { position: track.position }),
  });

  $effect(() => {
    if (show) {
      formData = {
        artist: track?.artist || '',
        title: track?.title || '',
        album: track?.album || '',
        ...(track?.hour !== undefined && { hour: track.hour }),
        ...(track?.position !== undefined && { position: track.position }),
      };
    }
  });

  function toggleShow(val) { if (onshowchange) onshowchange(val); }
  function handleKeydown(e) { if (e.key === 'Escape') toggleShow(false); }
  
  let saving = $state(false);

  async function save() {
    saving = true;
    try {
      const corrected = { title: formData.title };
      if (formData.artist !== track?.artist) corrected.artist = formData.artist;
      if (formData.album !== track?.album) corrected.album = formData.album;
      if ('hour' in formData) corrected.hour = formData.hour;
      if ('position' in formData) corrected.position = formData.position;

      const original = track ? {
        artist: track.artist,
        title: track.title,
        album: track.album,
        ...('hour' in track && { hour: track.hour }),
        ...('position' in track && { position: track.position }),
      } : null;

      const payload = {
        type: mode === 'add' ? 'TRACK_ADD' : 'TRACK_EDIT',
        track_id: track?.id || null,
        episode_id: episodeId,
        original_data: original,
        corrected_data: corrected
      };
      
      const res = await authFetch('/api/admin/correction', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (res.ok) {
        if (onSave) onSave();
        toggleShow(false);
      }
    } catch (e) {
      console.error(e);
    } finally {
      saving = false;
    }
  }
</script>

{#if show}
  <div class="modal-overlay" role="button" tabindex="0" onclick={() => toggleShow(false)} onkeydown={handleKeydown}>
    <div class="modal-content" role="dialog" aria-modal="true" onclick={(e) => e.stopPropagation()} onkeydown={handleKeydown}>
      <h3>{mode === 'add' ? 'Add New Track' : 'Correct Track Details'}</h3>
      
      <div class="form-row">
        <div class="form-group">
          <label for="artist">Artist</label>
          <input id="artist" type="text" bind:value={formData.artist} />
        </div>
        <div class="form-group">
          <label for="title">Title</label>
          <input id="title" type="text" bind:value={formData.title} />
          {#if suggestions.length > 0}
            <div class="suggestions">
              <span class="suggestions-label">MB suggestions:</span>
              {#each suggestions as s}
                <button class="suggestion-chip" onclick={() => formData.title = s}>{s}</button>
              {/each}
            </div>
          {/if}
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label for="album">Album</label>
          <input id="album" type="text" bind:value={formData.album} />
        </div>
        {#if 'hour' in formData}
        <div class="form-group half">
          <label for="hour">Hour</label>
          <input id="hour" type="number" bind:value={formData.hour} />
        </div>
        {/if}
        {#if 'position' in formData}
        <div class="form-group half">
          <label for="pos">Pos</label>
          <input id="pos" type="number" bind:value={formData.position} />
        </div>
        {/if}
      </div>
      
      <div class="actions">
        <button onclick={() => toggleShow(false)}>Cancel</button>
        <button class="save" onclick={save} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  .modal-content {
    background: var(--color-henry-800);
    padding: 2rem;
    border-radius: 12px;
    width: 100%;
    max-width: 500px;
    border: 1px solid var(--color-henry-600);
  }
  h3 { margin: 0 0 1.5rem; }
  .form-row { display: flex; gap: 1rem; }
  .form-group { margin-bottom: 1rem; flex: 1; }
  .half { flex: 0 0 60px; }
  label { display: block; font-size: 0.8rem; color: var(--color-henry-400); margin-bottom: 0.25rem; }
  input { width: 100%; padding: 0.6rem; border-radius: 6px; border: 1px solid var(--color-henry-600); background: var(--color-henry-900); color: white; }
  .actions { display: flex; gap: 1rem; margin-top: 1.5rem; justify-content: flex-end; }
  button { padding: 0.5rem 1rem; border-radius: 6px; border: 1px solid var(--color-henry-600); background: transparent; color: var(--color-henry-200); cursor: pointer; }
  button.save { background: var(--color-accent); border: none; color: white; }
  .suggestions { margin-top: 0.4rem; display: flex; flex-wrap: wrap; gap: 0.3rem; align-items: center; }
  .suggestions-label { font-size: 0.7rem; color: var(--color-henry-500); }
  .suggestion-chip { padding: 0.15rem 0.5rem; border-radius: 4px; border: 1px solid var(--color-henry-600); background: var(--color-henry-700); color: var(--color-henry-300); font-size: 0.7rem; cursor: pointer; }
  .suggestion-chip:hover { border-color: var(--color-accent); color: var(--color-accent); }
</style>
