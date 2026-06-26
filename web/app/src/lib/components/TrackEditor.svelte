<script>
  import { authFetch } from '../useAuth.svelte.js';

  let { show, onshowchange, mode = 'edit', track = null, episodeId = null, onSave, suggestions = [] } = $props();

  let formData = $state({
    artist: '',
    title: '',
    album: '',
    hour: undefined,
    position: undefined,
    album_mbid: '',
    album_release_group_mbid: '',
    track_mbid: '',
  });

  let artistSuggestions = $state([]);
  let albumSuggestions = $state([]);
  let artistSearchDebounce = $state(null);
  let albumSearchDebounce = $state(null);
  let selectedArtistId = $state(null);
  let artistDirty = $state(false);
  let albumDirty = $state(false);

  $effect(() => {
    if (show) {
      formData = {
        artist: track?.artist || '',
        title: track?.title || '',
        album: track?.album || '',
        ...(track?.hour !== undefined && { hour: track.hour }),
        ...(track?.position !== undefined && { position: track.position }),
        album_mbid: track?.album_mbid || '',
        album_release_group_mbid: track?.album_release_group_mbid || '',
        track_mbid: track?.track_mbid || '',
      };
      selectedArtistId = null;
      artistSuggestions = [];
      albumSuggestions = [];
      artistDirty = false;
      albumDirty = false;
    }
  });

  function toggleShow(val) { if (onshowchange) onshowchange(val); }
  function handleKeydown(e) { if (e.key === 'Escape') toggleShow(false); }

  async function searchArtist() {
    const q = formData.artist.trim();
    if (!q) { artistSuggestions = []; return; }
    try {
      const res = await authFetch(`/api/admin/entities?type=artist&q=${encodeURIComponent(q)}`);
      if (res.ok) {
        artistSuggestions = (await res.json()).filter(a => a.name !== q);
      }
    } catch (_) {}
  }

  function onArtistInput() {
    selectedArtistId = null;
    artistDirty = true;
    albumSuggestions = [];
    formData.album = '';
    if (artistSearchDebounce) clearTimeout(artistSearchDebounce);
    artistSearchDebounce = setTimeout(searchArtist, 200);
  }

  function selectArtist(name, id) {
    formData.artist = name;
    selectedArtistId = id;
    artistSuggestions = [];
    artistDirty = false;
    searchAlbums();
  }

  async function searchAlbums() {
    const q = formData.album.trim();
    try {
      let url = `/api/admin/entities?type=album&q=${encodeURIComponent(q)}`;
      if (selectedArtistId) url += `&artist_id=${selectedArtistId}`;
      const res = await authFetch(url);
      if (res.ok) {
        albumSuggestions = (await res.json()).filter(a => a.name !== q);
      }
    } catch (_) {}
  }

  function onAlbumInput() {
    albumDirty = true;
    if (albumSearchDebounce) clearTimeout(albumSearchDebounce);
    albumSearchDebounce = setTimeout(searchAlbums, 200);
  }

  function selectAlbum(name, mbid, rg_mbid) {
    formData.album = name;
    if (mbid) formData.album_mbid = mbid;
    if (rg_mbid) formData.album_release_group_mbid = rg_mbid;
    albumSuggestions = [];
    albumDirty = false;
  }

  let saving = $state(false);

  async function save() {
    saving = true;
    try {
      const corrected = { title: formData.title };
      if (formData.artist !== track?.artist) corrected.artist = formData.artist;
      if (formData.album !== track?.album) corrected.album = formData.album;
      if ('hour' in formData) corrected.hour = formData.hour;
      if ('position' in formData) corrected.position = formData.position;
      if (formData.album_mbid) corrected.album_mbid = formData.album_mbid;
      if (formData.album_release_group_mbid) corrected.album_release_group_mbid = formData.album_release_group_mbid;
      if (formData.track_mbid) corrected.track_mbid = formData.track_mbid;

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
    <div class="modal-content" role="dialog" tabindex="0" aria-modal="true" onclick={(e) => e.stopPropagation()} onkeydown={handleKeydown}>
      <h3>{mode === 'add' ? 'Add New Track' : 'Correct Track Details'}</h3>
      
      <div class="form-row">
        <div class="form-group">
          <label for="artist">Artist</label>
          <div class="autocomplete-wrap">
            <input id="artist" type="text" bind:value={formData.artist} oninput={onArtistInput} onblur={() => setTimeout(() => artistSuggestions = [], 200)} />
            {#if artistSuggestions.length > 0}
              <div class="autocomplete-dropdown">
                {#each artistSuggestions as a}
                  <button class="autocomplete-item" onmousedown={() => selectArtist(a.name, a.id)}>
                    <span class="ac-name">{a.name}</span>
                    <span class="ac-count">{a.track_count} tracks</span>
                  </button>
                {/each}
              </div>
            {/if}
          </div>
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
          <div class="autocomplete-wrap">
            <input id="album" type="text" bind:value={formData.album} oninput={onAlbumInput} onblur={() => setTimeout(() => albumSuggestions = [], 200)} />
            {#if albumSuggestions.length > 0}
              <div class="autocomplete-dropdown">
                {#each albumSuggestions as a}
                  <button class="autocomplete-item" onmousedown={() => selectAlbum(a.name, a.mbid, a.release_group_mbid)}>
                    <span class="ac-name">{a.name}</span>
                    <span class="ac-count">{a.track_count} tracks{#if a.mbid} · ✓{/if}</span>
                  </button>
                {/each}
              </div>
            {/if}
          </div>
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

      {#if formData.album}
      <div class="form-row">
        <div class="form-group">
          <label for="album_mbid">Album MBID {#if formData.album_mbid}<a href="https://musicbrainz.org/release/{formData.album_mbid}" target="_blank" rel="noopener" class="mbid-link" title="Open in MusicBrainz">↗</a>{/if}</label>
          <input id="album_mbid" type="text" bind:value={formData.album_mbid} placeholder="Release MBID (enables artwork)" />
        </div>
        <div class="form-group">
          <label for="album_release_group_mbid">RG MBID {#if formData.album_release_group_mbid}<a href="https://musicbrainz.org/release-group/{formData.album_release_group_mbid}" target="_blank" rel="noopener" class="mbid-link" title="Open in MusicBrainz">↗</a>{/if}</label>
          <input id="album_release_group_mbid" type="text" bind:value={formData.album_release_group_mbid} placeholder="Release Group MBID (links MusicBrainz)" />
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label for="track_mbid">Track MBID {#if formData.track_mbid}<a href="https://musicbrainz.org/recording/{formData.track_mbid}" target="_blank" rel="noopener" class="mbid-link" title="Open in MusicBrainz">↗</a>{/if}</label>
          <input id="track_mbid" type="text" bind:value={formData.track_mbid} placeholder="Recording MBID (this track only)" />
        </div>
        <div class="form-group">
        </div>
      </div>
      {/if}
      
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
  input { width: 100%; padding: 0.6rem; border-radius: 6px; border: 1px solid var(--color-henry-600); background: var(--color-henry-900); color: white; box-sizing: border-box; }
  .autocomplete-wrap { position: relative; }
  .autocomplete-dropdown {
    position: absolute; top: 100%; left: 0; right: 0;
    background: var(--color-henry-900); border: 1px solid var(--color-henry-600);
    border-radius: 6px; max-height: 200px; overflow-y: auto; z-index: 10;
    margin-top: 2px;
  }
  .autocomplete-item {
    display: flex; justify-content: space-between; align-items: center;
    width: 100%; padding: 0.5rem 0.6rem; border: none;
    background: transparent; color: var(--color-henry-200);
    text-align: left; cursor: pointer; font-size: 0.85rem;
  }
  .autocomplete-item:hover { background: var(--color-henry-700); color: var(--color-accent); }
  .ac-name { font-weight: 600; }
  .ac-count { font-size: 0.75rem; color: var(--color-henry-400); }
  .mbid-link { color: var(--color-accent); text-decoration: none; font-size: 0.85rem; margin-left: 0.3rem; opacity: 0.7; }
  .mbid-link:hover { opacity: 1; }
  .actions { display: flex; gap: 1rem; margin-top: 1.5rem; justify-content: flex-end; }
  button { padding: 0.5rem 1rem; border-radius: 6px; border: 1px solid var(--color-henry-600); background: transparent; color: var(--color-henry-200); cursor: pointer; }
  button.save { background: var(--color-accent); border: none; color: white; }
  .suggestions { margin-top: 0.4rem; display: flex; flex-wrap: wrap; gap: 0.3rem; align-items: center; }
  .suggestions-label { font-size: 0.7rem; color: var(--color-henry-500); }
  .suggestion-chip { padding: 0.15rem 0.5rem; border-radius: 4px; border: 1px solid var(--color-henry-600); background: var(--color-henry-700); color: var(--color-henry-300); font-size: 0.7rem; cursor: pointer; }
  .suggestion-chip:hover { border-color: var(--color-accent); color: var(--color-accent); }
</style>
