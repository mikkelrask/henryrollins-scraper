<script>
  import { onMount } from 'svelte';
  import EntityIntelligence from '../lib/components/EntityIntelligence.svelte';
  import TrackEditor from '../lib/components/TrackEditor.svelte';
  import { auth, authFetch } from '../lib/useAuth.svelte.js';
  import { router } from '../lib/router.svelte.js';

  // ── Tab state ──
  let activeTab = $state('merge');

  // ── Merge tab state ──
  let mergeType = $state('artist');
  let clusters = $state([]);
  let lonelyVariants = $state([]);
  let loading = $state(false);
  let mergePreview = $state(null);
  let mergeResult = $state(null);
  let merging = $state(false);
  let sortBy = $state('tracks');

  // ── Edit tab state ──
  let entityType = $state('artist');
  let searchTerm = $state('');
  let results = $state([]);
  let searchLoading = $state(false);
  let editor = $state({ show: false, mode: 'edit', track: null });
  let targets = $state({});

  // ── Rename tab state ──
  let renameForm = $state({ album: '', artist: '', old_title: '', new_title: '' });
  let renaming = $state(false);
  let renameResult = $state(null);

  async function doRename() {
    const { album, artist, old_title, new_title } = renameForm;
    if (!album || !artist || !old_title || !new_title) {
      renameResult = 'All fields are required.';
      return;
    }
    renaming = true;
    renameResult = null;
    try {
      const res = await authFetch('/api/admin/rename-track', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(renameForm),
      });
      const data = await res.json();
      if (res.ok) {
        renameResult = `✅ Renamed ${data.renamed} track${data.renamed !== 1 ? 's' : ''}.`;
        renameForm = { album: '', artist: '', old_title: '', new_title: '' };
      } else {
        renameResult = `❌ ${data.detail || 'Error'}`;
      }
    } catch (e) {
      renameResult = `❌ ${e.message}`;
    } finally {
      renaming = false;
    }
  }

  // ── Artist/Album rename tab state ──
  let artistRenameForm = $state({ old: '', new: '' });
  let artistRenaming = $state(false);
  let artistRenameResult = $state(null);

  async function doArtistRename() {
    const { old, new: newName } = artistRenameForm;
    if (!old || !newName) {
      artistRenameResult = 'Both fields are required.';
      return;
    }
    artistRenaming = true;
    artistRenameResult = null;
    try {
      const res = await authFetch('/api/admin/rename-artist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_name: old, new_name: newName }),
      });
      const data = await res.json();
      if (res.ok) {
        artistRenameResult = `✅ Updated ${data.artists_updated} artist entry, ${data.tracks_updated} tracks.`;
        artistRenameForm = { old: '', new: '' };
      } else {
        artistRenameResult = `❌ ${data.detail || 'Error'}`;
      }
    } catch (e) {
      artistRenameResult = `❌ ${e.message}`;
    } finally {
      artistRenaming = false;
    }
  }

  let albumRenameForm = $state({ artist: '', old: '', new: '' });
  let albumRenaming = $state(false);
  let albumRenameResult = $state(null);

  async function doAlbumRename() {
    const { artist, old, new: newName } = albumRenameForm;
    if (!artist || !old || !newName) {
      albumRenameResult = 'All fields are required.';
      return;
    }
    albumRenaming = true;
    albumRenameResult = null;
    try {
      const res = await authFetch('/api/admin/rename-album', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_name: old, new_name: newName, artist }),
      });
      const data = await res.json();
      if (res.ok) {
        albumRenameResult = `✅ Updated ${data.albums_updated} album entry, ${data.tracks_updated} tracks.`;
        albumRenameForm = { artist: '', old: '', new: '' };
      } else {
        albumRenameResult = `❌ ${data.detail || 'Error'}`;
      }
    } catch (e) {
      albumRenameResult = `❌ ${e.message}`;
    } finally {
      albumRenaming = false;
    }
  }

  // ── Toast state ──
  let toast = $state({ show: false, message: '', type: 'success' });
  let toastTimer = null;

  function showToast(message, type = 'success') {
    toast = { show: true, message, type };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast = { show: false, message: '', type: 'success' }, 3000);
  }

  // ── Cluster loading ──
  async function loadClusters() {
    loading = true;
    try {
      const res = await authFetch(`/api/admin/clusters?type=${mergeType}&min_size=2&show_lonely=true`);
      let data = await res.json();
      clusters = applySort(data.clusters || [], sortBy);
      lonelyVariants = data.lonely || [];
    } catch (e) {
      showToast('Failed to load clusters: ' + e.message, 'error');
    }
    loading = false;
  }

  async function switchMergeType(type) {
    mergeType = type;
    loadClusters();
  }

  function applySort(data, sortKey) {
    const sorted = [...data];
    if (sortKey === 'tracks') {
      sorted.sort((a, b) => b.total_tracks - a.total_tracks);
    } else if (sortKey === 'variants') {
      sorted.sort((a, b) => b.variant_count - a.variant_count);
    } else if (sortKey === 'name') {
      sorted.sort((a, b) => a.base_name.localeCompare(b.base_name));
    }
    return sorted;
  }

  function handleSortChange(e) {
    sortBy = e.target.value;
    clusters = applySort(clusters, sortBy);
  }

  onMount(() => {
    loadClusters();
  });

  // ── Merge logic ──
  function getCanonical(variants) {
    // Pick the variant with the most tracks as the one to keep
    return variants.reduce((a, b) => a.tracks >= b.tracks ? a : b);
  }

  async function previewMerge(cluster) {
    const canonical = getCanonical(cluster.variants);
    const sources = cluster.variants.filter(v => v.id !== canonical.id);
    if (sources.length === 0) {
      showToast('Only one variant — nothing to merge', 'info');
      return;
    }

    try {
      const sourceIds = sources.map(s => s.id).join(',');
      const res = await authFetch(`/api/admin/merge/preview?type=${mergeType}&source_ids=${sourceIds}&target_id=${canonical.id}`, {
        method: 'POST'
      });
      const result = await res.json();
      if (!res.ok) {
        throw new Error(result.detail || `Server error ${res.status}`);
      }
      mergePreview = result;
    } catch (e) {
      showToast('Preview failed: ' + e.message, 'error');
    }
  }

  async function confirmMerge() {
    if (!mergePreview) return;
    merging = true;

    try {
      const res = await authFetch(`/api/admin/merge?type=${mergeType}&source_ids=${mergePreview.details.map(d => d.source_id).join(',')}&target_id=${mergePreview.target_id}`, {
        method: 'POST'
      });
      const result = await res.json();

      if (!res.ok) {
        throw new Error(result.detail || `Server error ${res.status}`);
      }

      showToast(`✅ Merged ${result.total_affected_tracks} tracks into "${result.target_name}"`);
      mergePreview = null;

      // Reload clusters after a brief delay
      setTimeout(loadClusters, 500);
    } catch (e) {
      showToast('Merge failed: ' + e.message, 'error');
    }
    merging = false;
  }

  function cancelPreview() {
    mergePreview = null;
  }

  async function mergeSingle(sourceId, targetId, targetName) {
    try {
      const res = await authFetch(`/api/admin/reassign?type=${mergeType}&source_id=${sourceId}&target_id=${targetId}`, {
        method: 'POST'
      });
      const result = await res.json();
      if (!res.ok) {
        throw new Error(result.detail || `Server error ${res.status}`);
      }
      showToast(`✅ Merged into "${targetName}"`);
      loadClusters();
    } catch (e) {
      showToast('Merge failed: ' + e.message, 'error');
    }
  }

  // ── Edit tab logic (existing) ──
  async function search() {
    searchLoading = true;
    try {
      const res = await authFetch(`/api/admin/entities?type=${entityType}&q=${encodeURIComponent(searchTerm)}`);
      results = await res.json();
    } catch (e) {
      showToast('Search failed: ' + e.message, 'error');
    }
    searchLoading = false;
  }

  async function reassign(sourceId) {
    const targetId = targets[sourceId];
    if (!targetId || !confirm('Reassign records to ID ' + targetId + '?')) return;

    try {
      const res = await authFetch(`/api/admin/reassign?type=${entityType}&source_id=${sourceId}&target_id=${targetId}`, { method: 'POST' });
      if (res.ok) {
        showToast('Reassigned!');
        search();
      } else {
        const err = await res.text();
        showToast('Error: ' + err, 'error');
      }
    } catch (e) {
      showToast('Reassign failed: ' + e.message, 'error');
    }
  }

  // ── Cluster stats ──
  // ── Lonely merge logic (search-based, no IDs) ──
  let lonelySearch = $state({});
  let lonelyResults = $state({});
  let lonelyTarget = $state({});
  let searchTimers = $state({});

  async function lonelySearchChange(variantId, value) {
    lonelySearch[variantId] = value;
    if (lonelyTarget[variantId]) {
      // If a target was previously selected, clear it when typing
      delete lonelyTarget[variantId];
    }
    if (searchTimers[variantId]) clearTimeout(searchTimers[variantId]);
    if (value.length < 2) {
      lonelyResults[variantId] = [];
      return;
    }
    searchTimers[variantId] = setTimeout(async () => {
      try {
        const res = await authFetch(`/api/admin/entities?type=${mergeType}&q=${encodeURIComponent(value)}`);
        const data = await res.json();
        lonelyResults[variantId] = data.slice(0, 6);
      } catch (e) {
        lonelyResults[variantId] = [];
      }
    }, 250);
  }

  function selectLonelyTarget(variantId, entity) {
    lonelyTarget[variantId] = entity;
    lonelySearch[variantId] = entity.name;
    lonelyResults[variantId] = [];
  }

  async function mergeLonely(variantId) {
    const target = lonelyTarget[variantId];
    if (!target) {
      showToast('Search for and select an artist to merge into', 'error');
      return;
    }
    try {
      const res = await authFetch(`/api/admin/reassign?type=${mergeType}&source_id=${variantId}&target_id=${target.id}`, {
        method: 'POST'
      });
      const result = await res.json();
      if (!res.ok) {
        throw new Error(result.detail || `Server error ${res.status}`);
      }
      showToast(`✅ Merged into "${target.name}"`);
      // Clean up this variant's state
      delete lonelySearch[variantId];
      delete lonelyResults[variantId];
      delete lonelyTarget[variantId];
      loadClusters();
    } catch (e) {
      showToast('Merge failed: ' + e.message, 'error');
    }
  }

  // ── Cluster stats ──
  let clusterStats = $derived.by(() => {
    if (clusters.length === 0 && lonelyVariants.length === 0) return null;
    const totalTracks = clusters.reduce((s, c) => s + c.total_tracks, 0);
    const totalVariants = clusters.reduce((s, c) => s + c.variant_count, 0);
    const lonelyTracks = lonelyVariants.reduce((s, v) => s + v.tracks, 0);
    return {
      totalTracks: totalTracks + lonelyTracks,
      totalVariants: totalVariants + lonelyVariants.length,
      clusterCount: clusters.length,
      lonelyCount: lonelyVariants.length,
      lonelyTracks,
    };
  });

  // ── Track Browser tab state ──
  let trackSearch = $state('');
  let trackResults = $state([]);
  let trackSearchLoading = $state(false);
  let trackSearched = $state(false);
  let trackDrillOpen = $state(new Set());
  let trackBrowserEditor = $state({ show: false, track: null });

  async function searchTracks() {
    trackSearchLoading = true;
    trackSearched = true;
    try {
      const res = await authFetch(`/api/admin/tracks?q=${encodeURIComponent(trackSearch)}`);
      const data = await res.json();
      trackResults = data.items || [];
    } catch (e) {
      trackResults = [];
    }
    trackSearchLoading = false;
  }

  function toggleTrackDrill(row) {
    const next = new Set(trackDrillOpen);
    if (next.has(row)) next.delete(row);
    else next.add(row);
    trackDrillOpen = next;
  }

  function editTrackFromBrowser(row) {
    trackBrowserEditor = { show: true, track: {
      artist: row.artist,
      title: row.title,
      album: row.album,
      hour: null,
      position: null,
    }};
  }

  // ── Correction History tab state ──
  let corrections = $state([]);
  let correctionsLoading = $state(false);

  async function loadCorrections() {
    correctionsLoading = true;
    try {
      const res = await authFetch('/api/admin/corrections');
      const data = await res.json();
      corrections = data.items || [];
    } catch (e) {
      corrections = [];
    }
    correctionsLoading = false;
  }

  async function revertCorrection(id) {
    if (!confirm('Revert this correction?')) return;
    try {
      const res = await authFetch(`/api/admin/corrections/${id}/revert`, { method: 'POST' });
      if (res.ok) {
        corrections = corrections.filter(c => c.id !== id);
        showToast('Correction reverted');
      }
    } catch (e) {
      showToast('Revert failed: ' + e.message, 'error');
    }
  }

  onMount(() => {
    loadClusters();
    loadCorrections();
  });
</script>

<!-- Track Editor Modal -->
<TrackEditor
  show={editor.show}
  onshowchange={(val) => editor.show = val}
  mode={editor.mode}
  track={editor.track}
  onSave={search}
/>

<!-- Track Editor Modal (Browser) -->
<TrackEditor
  show={trackBrowserEditor.show}
  onshowchange={(val) => trackBrowserEditor.show = val}
  mode="edit"
  track={trackBrowserEditor.track}
  episodeId={null}
  onSave={searchTracks}
/>

<!-- Merge Preview Modal -->
{#if mergePreview}
  <div class="modal-overlay" role="button" tabindex="0" onclick={cancelPreview} onkeydown={(e) => e.key === 'Escape' && cancelPreview()}>
    <div class="modal-content preview-modal" role="dialog" aria-modal="true" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.key === 'Escape' && cancelPreview()}>
      <h3>Merge Preview</h3>
      <p class="preview-summary">
        Merge <strong>{mergePreview.details.length} source{mergePreview.details.length !== 1 ? 's' : ''}</strong>
        into <strong>{mergePreview.target_name}</strong>
      </p>
      <div class="preview-stats">
        <div class="stat">
          <span class="stat-value">{mergePreview.total_affected_tracks}</span>
          <span class="stat-label">tracks affected</span>
        </div>
        <div class="stat">
          <span class="stat-value">{mergePreview.total_affected_albums}</span>
          <span class="stat-label">albums affected</span>
        </div>
      </div>
      <div class="preview-details">
        {#each mergePreview.details as detail}
          <div class="preview-row">
            <span class="source-name">{detail.source_name}</span>
            <span class="arrow">→</span>
            <span class="target-name">{mergePreview.target_name}</span>
            <span class="affected">({detail.affected_tracks} tracks, {detail.affected_albums} albums)</span>
          </div>
        {/each}
      </div>
      <div class="preview-actions">
        <button class="btn-secondary" onclick={cancelPreview}>Cancel</button>
        <button class="btn-primary" onclick={confirmMerge} disabled={merging}>
          {merging ? 'Merging...' : 'Confirm Merge'}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- Toast Notification -->
{#if toast.show}
  <div class="toast {toast.type}">
    {toast.message}
  </div>
{/if}

{#if !auth.authed}
  <div class="page auth-gate">
    <div class="auth-prompt">
      <h1>Admin Access</h1>
      <p>Enter your admin API key to continue.</p>
      <button onclick={() => auth.prompt()}>Enter Key</button>
    </div>
  </div>
{:else}
<div class="page">
  <header class="page-header">
    <h1>Admin Center</h1>
  </header>

  <!-- Tabs -->
  <div class="tab-bar">
    <button
      class="tab-button"
      class:active={activeTab === 'merge'}
      onclick={() => activeTab = 'merge'}
    >🔄 Merge</button>
    <button
      class="tab-button"
      class:active={activeTab === 'edit'}
      onclick={() => activeTab = 'edit'}
    >✏️ Edit</button>
    <button
      class="tab-button"
      class:active={activeTab === 'rename'}
      onclick={() => activeTab = 'rename'}
    >🏷️ Rename</button>
    <button
      class="tab-button"
      class:active={activeTab === 'tracks'}
      onclick={() => activeTab = 'tracks'}
    >🔍 Tracks</button>
    <button
      class="tab-button"
      class:active={activeTab === 'history'}
      onclick={() => activeTab = 'history'}
    >📜 History</button>
  </div>

  <!-- ──────────────────── Merge Tab ──────────────────── -->
  {#if activeTab === 'merge'}
    <div class="merge-panel">
      <div class="merge-header">
        {#if clusterStats}
          <p class="cluster-summary">
            <strong>{clusterStats.clusterCount}</strong> clusters ·
            <strong>{clusterStats.totalVariants}</strong> variants ·
            <strong>{clusterStats.totalTracks}</strong> tracks affected
          </p>
        {/if}
        <div class="merge-controls">
          <label>
            Type:
            <select value={mergeType} onchange={(e) => switchMergeType(e.target.value)}>
              <option value="artist">Artists</option>
              <option value="album">Albums</option>
            </select>
          </label>
          <label>
            Sort:
            <select value={sortBy} onchange={handleSortChange}>
              <option value="tracks">Most tracks</option>
              <option value="variants">Most variants</option>
              <option value="name">Name A-Z</option>
            </select>
          </label>
          <button class="btn-secondary" onclick={loadClusters} disabled={loading}>
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {#if loading}
        <div class="loading-state">Loading clusters...</div>
      {:else if clusters.length === 0}
        <div class="empty-state">
          <p>No duplicate clusters found. ✨</p>
        </div>
      {:else}
        <div class="clusters-list">
          {#each clusters as cluster (cluster.base_name + cluster.total_tracks)}
            {@const canonical = getCanonical(cluster.variants)}
            <div class="cluster-card">
              <div class="cluster-header">
                <h3>{cluster.base_name}</h3>
                <span class="cluster-meta">
                  {cluster.variant_count} variant{cluster.variant_count !== 1 ? 's' : ''} ·
                  {cluster.total_tracks} track{cluster.total_tracks !== 1 ? 's' : ''}
                </span>
              </div>

              <div class="variant-list">
                {#each cluster.variants as variant}
                  <div class="variant-row" class:canonical={variant.id === canonical.id}>
                    <div class="variant-info">
                      {#if variant.id === canonical.id}
                        <span class="canonical-badge">KEEP</span>
                      {:else}
                        <span class="merge-badge">→</span>
                      {/if}
                      <span class="variant-name">
                        {variant.name}
                        {#if variant.artist_name}
                          <span class="artist-inline">· {variant.artist_name}</span>
                        {/if}
                      </span>
                      <span class="variant-stats">
                        {variant.tracks} tracks · {variant.albums} albums
                      </span>
                    </div>
                    <div class="variant-actions">
                      {#if variant.id !== canonical.id}
                        <button
                          class="btn-merge-single"
                          onclick={() => mergeSingle(variant.id, canonical.id, canonical.name)}
                          title="Merge this variant into {canonical.name}"
                        >Merge →</button>
                      {:else}
                        <span class="canonical-label">(canonical)</span>
                      {/if}
                    </div>
                  </div>
                {/each}
              </div>

              <div class="cluster-actions">
                <button class="btn-primary" onclick={() => previewMerge(cluster)}>
                  Merge All ({cluster.variant_count - 1} source{cluster.variant_count - 1 !== 1 ? 's' : ''})
                </button>
              </div>
            </div>
          {/each}
        </div>
      {/if}

      <!-- Lonely Variants (artists with &/+/feat that didn't cluster) -->
      {#if lonelyVariants.length > 0}
        <div class="lonely-section">
          <div class="lonely-header">
            <h3>👤 Unmatched Collaboration Variants</h3>
            <span class="lonely-meta">
              {lonelyVariants.length} artist{lonelyVariants.length !== 1 ? 's' : ''} ·
              {clusterStats.lonelyTracks} track{clusterStats.lonelyTracks !== 1 ? 's' : ''}
            </span>
          </div>
          <p class="lonely-hint">
            These have collaboration separators (&amp;, +, w/) but no similar artist was found
            automatically. Search for the artist you want to merge them into.
          </p>
          <div class="lonely-list">
            {#each lonelyVariants as variant}
              {@const selected = lonelyTarget[variant.id]}
              <div class="variant-row">
                <div class="variant-info">
                  <span class="merge-badge">?</span>
                  <span class="variant-name">{variant.name}</span>
                  <span class="variant-stats">
                    {variant.tracks} tracks · {variant.albums} albums
                  </span>
                </div>
                <div class="variant-actions lonely-action-group">
                  <div class="lonely-search-wrap">
                    <input
                      placeholder="Search target artist..."
                      value={lonelySearch[variant.id] || ''}
                      oninput={(e) => lonelySearchChange(variant.id, e.target.value)}
                      class="target-search-input"
                    />
                    {#if lonelyResults[variant.id]?.length > 0}
                      <div class="lonely-dropdown">
                        {#each lonelyResults[variant.id] as entity}
                          <button
                            class="lonely-option"
                            onclick={() => selectLonelyTarget(variant.id, entity)}
                          >
                            <span class="option-name">{entity.name}</span>
                            <span class="option-stats">{entity.track_count} tracks</span>
                          </button>
                        {/each}
                      </div>
                    {/if}
                  </div>
                  {#if selected}
                    <span class="lonely-target-badge">→ {selected.name}</span>
                    <button
                      class="btn-merge-single"
                      onclick={() => mergeLonely(variant.id)}
                    >Merge</button>
                  {:else}
                    <button
                      class="btn-merge-single"
                      disabled
                      title="Search and select a target first"
                    >Merge</button>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        </div>
      {/if}
    </div>
  {/if}

  <!-- ──────────────────── Edit Tab ──────────────────── -->
  {#if activeTab === 'edit'}
    <div class="edit-panel">
      <div class="search-bar">
        <select bind:value={entityType} onchange={search}>
          <option value="artist">Artists</option>
          <option value="album">Albums</option>
        </select>
        <input type="text" placeholder="Search..." bind:value={searchTerm} oninput={search} />
        <button onclick={search}>Search</button>
      </div>

      <div class="results-grid">
        {#each results as entity}
          <div class="card">
            <div class="card-header">
              <strong>{entity.name} <span class="id-label">(ID: {entity.id})</span></strong>
              <input placeholder="Target ID" bind:value={targets[entity.id]} style="width: 60px" />
              <button onclick={() => reassign(entity.id)}>Reassign</button>
            </div>
            <EntityIntelligence
              entityType={entityType}
              id={entity.id}
              name={entity.name}
              onEdit={(t) => editor = {show: true, mode: 'edit', track: t}}
            />
          </div>
        {/each}
      </div>
    </div>
  {/if}

  <!-- ──────────────────── Rename Tab ──────────────────── -->
  {#if activeTab === 'rename'}
    <div class="rename-panel">
      <div class="card">
        <h3>Rename Track Title</h3>
        <p class="help-text">Rename a track title across every episode it appears in.</p>
        <div class="rename-form">
          <div class="form-group">
            <label>Album</label>
            <input type="text" placeholder="e.g. Low" bind:value={renameForm.album} />
          </div>
          <div class="form-group">
            <label>Artist</label>
            <input type="text" placeholder="e.g. David Bowie" bind:value={renameForm.artist} />
          </div>
          <div class="form-group">
            <label>Old Title</label>
            <input type="text" placeholder="e.g. Sound And Vision" bind:value={renameForm.old_title} />
          </div>
          <div class="form-group">
            <label>New Title</label>
            <input type="text" placeholder="e.g. Sound and Vision" bind:value={renameForm.new_title} />
          </div>
          <button class="rename-btn" onclick={doRename} disabled={renaming}>
            {renaming ? 'Renaming...' : 'Rename'}
          </button>
          {#if renameResult !== null}
            <p class="rename-result">{renameResult}</p>
          {/if}
        </div>
      </div>

      <div class="card">
        <h3>Rename Artist</h3>
        <p class="help-text">Rename an artist everywhere. If the target name already exists, tracks and albums are merged into it.</p>
        <div class="rename-form">
          <div class="form-group">
            <label>Old Artist Name</label>
            <input type="text" placeholder="e.g. The Lurkers" bind:value={artistRenameForm.old} />
          </div>
          <div class="form-group">
            <label>New Artist Name</label>
            <input type="text" placeholder="e.g. Lurkers" bind:value={artistRenameForm.new} />
          </div>
          <button class="rename-btn" onclick={doArtistRename} disabled={artistRenaming}>
            {artistRenaming ? 'Renaming...' : 'Rename'}
          </button>
          {#if artistRenameResult !== null}
            <p class="rename-result">{artistRenameResult}</p>
          {/if}
        </div>
      </div>

      <div class="card">
        <h3>Rename Album</h3>
        <p class="help-text">Rename an album everywhere. If the target name already exists, tracks are merged into it and the old album is deleted.</p>
        <div class="rename-form">
          <div class="form-group">
            <label>Artist</label>
            <input type="text" placeholder="e.g. The Lurkers" bind:value={albumRenameForm.artist} />
          </div>
          <div class="form-group">
            <label>Old Album Name</label>
            <input type="text" placeholder="e.g. Fulhamn Fallout" bind:value={albumRenameForm.old} />
          </div>
          <div class="form-group">
            <label>New Album Name</label>
            <input type="text" placeholder="e.g. Fulham Fallout" bind:value={albumRenameForm.new} />
          </div>
          <button class="rename-btn" onclick={doAlbumRename} disabled={albumRenaming}>
            {albumRenaming ? 'Renaming...' : 'Rename'}
          </button>
          {#if albumRenameResult !== null}
            <p class="rename-result">{albumRenameResult}</p>
          {/if}
        </div>
      </div>
    </div>
  {/if}

  <!-- ──────────────────── Track Browser Tab ──────────────────── -->
  {#if activeTab === 'tracks'}
    <div class="tracks-panel">
      <div class="card">
        <div class="tracks-search">
          <input
            type="text"
            placeholder="Search tracks by title, artist, or album…"
            bind:value={trackSearch}
            onkeydown={(e) => e.key === 'Enter' && searchTracks()}
          />
          <button onclick={searchTracks} disabled={trackSearchLoading}>
            {trackSearchLoading ? 'Searching…' : 'Search'}
          </button>
        </div>
      </div>

      {#if trackResults.length > 0}
        <div class="card">
          <p class="tracks-count">{trackResults.length} result{trackResults.length !== 1 ? 's' : ''}</p>
          <table class="data-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Artist</th>
                <th>Album</th>
                <th class="right">Plays</th>
                <th class="right">Episodes</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {#each trackResults as row}
                <tr>
                  <td class="track-title-cell">{row.title}</td>
                  <td>{row.artist}</td>
                  <td>{row.album || '—'}</td>
                  <td class="right">{row.total_plays}</td>
                  <td class="right">{row.episode_count}</td>
                  <td>
                    <button class="drill-btn" onclick={() => toggleTrackDrill(row)}>
                      {trackDrillOpen.has(row) ? '▲' : '▼'}
                    </button>
                  </td>
                </tr>
                {#if trackDrillOpen.has(row)}
                  <tr class="drill-row">
                    <td colspan="6">
                      <div class="drill-episodes">
                        {#each row.episodes as ep}
                          <a href="#/episode/{ep.broadcast ?? ep.date}" onclick={router.navigate} class="ep-chip">
                            {ep.broadcast ? `#${ep.broadcast}` : ep.date}
                          </a>
                        {/each}
                        <button class="edit-all-btn" onclick={() => editTrackFromBrowser(row)}>
                          Edit
                        </button>
                      </div>
                    </td>
                  </tr>
                {/if}
              {/each}
            </tbody>
          </table>
        </div>
      {:else if trackSearched}
        <div class="card">
          <p class="no-results">No tracks found</p>
        </div>
      {/if}
    </div>
  {/if}

  <!-- ──────────────────── Correction History Tab ──────────────────── -->
  {#if activeTab === 'history'}
    <div class="history-panel">
      <div class="card">
        <div class="history-controls">
          <button onclick={loadCorrections} disabled={correctionsLoading}>
            {correctionsLoading ? 'Loading…' : 'Refresh'}
          </button>
          {#if corrections.length > 0}
            <span class="history-count">{corrections.length} correction{corrections.length !== 1 ? 's' : ''}</span>
          {/if}
        </div>
      </div>

      {#if corrections.length > 0}
        <div class="card">
          <table class="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Episode</th>
                <th>Title</th>
                <th>Change</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {#each corrections as c}
                <tr>
                  <td class="history-date">{c.created_at?.slice(0, 16)?.replace('T', ' ')}</td>
                  <td>
                    {#if c.episode_id}
                      <a href="#/episode/{c.episode_id}" onclick={router.navigate}>#{c.episode_id}</a>
                    {:else}
                      —
                    {/if}
                  </td>
                  <td class="history-title">
                    {c.original_data?.title || c.corrected_data?.title || '—'}
                  </td>
                  <td class="history-change">
                    {#if c.original_data}
                      {#each Object.keys(c.corrected_data) as key}
                        {#if c.original_data[key] !== c.corrected_data[key]}
                          <span class="change-line">
                            <span class="change-field">{key}:</span>
                            <span class="change-old">{c.original_data[key] || '(empty)'}</span>
                            <span class="change-arrow">→</span>
                            <span class="change-new">{c.corrected_data[key]}</span>
                          </span>
                        {/if}
                      {/each}
                    {:else}
                      <span class="change-line"><span class="change-new">Added track</span></span>
                    {/if}
                  </td>
                  <td>
                    <button class="revert-btn" onclick={() => revertCorrection(c.id)} title="Revert">
                      ↩
                    </button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {:else}
        <div class="card">
          <p class="no-results">No corrections found</p>
        </div>
      {/if}
    </div>
  {/if}
</div>
{/if}

<style>
  /* ── Layout ── */
  .page { padding-bottom: 3rem; }
  .auth-gate { display: flex; justify-content: center; align-items: center; min-height: 60vh; }
  .auth-prompt { text-align: center; }
  .auth-prompt h1 { margin-bottom: 0.5rem; }
  .auth-prompt p { color: var(--color-henry-300); margin-bottom: 1.5rem; }
  .auth-prompt button { padding: 0.6rem 1.5rem; border-radius: 8px; border: 1px solid var(--color-accent); background: var(--color-accent); color: var(--color-henry-900); font-weight: 600; cursor: pointer; }
  .page-header { margin-bottom: 1.5rem; }

  /* ── Tabs ── */
  .tab-bar {
    display: flex;
    gap: 0;
    margin-bottom: 2rem;
    border-bottom: 2px solid var(--color-henry-700);
  }
  .tab-button {
    padding: 0.6rem 1.4rem;
    background: transparent;
    border: none;
    color: var(--color-henry-400);
    font-size: 0.95rem;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    transition: all 0.15s;
  }
  .tab-button:hover {
    color: var(--color-henry-200);
    background: var(--color-henry-800);
  }
  .tab-button.active {
    color: var(--color-accent);
    border-bottom-color: var(--color-accent);
    font-weight: 600;
  }

  /* ── Merge tab ── */
  .merge-panel { max-width: 900px; }

  /* ── Lonely variants ── */
  .lonely-section {
    margin-top: 2.5rem;
    border-top: 1px solid var(--color-henry-700);
    padding-top: 1.5rem;
  }
  .lonely-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 0.5rem;
  }
  .lonely-header h3 {
    margin: 0;
    font-size: 1rem;
    color: var(--color-henry-200);
  }
  .lonely-meta {
    font-size: 0.8rem;
    color: var(--color-henry-500);
  }
  .lonely-hint {
    font-size: 0.82rem;
    color: var(--color-henry-500);
    margin: 0 0 0.75rem;
  }
  .lonely-list {
    border: 1px solid var(--color-henry-700);
    border-radius: 6px;
    overflow: hidden;
  }
  .target-search-input {
    width: 160px;
    padding: 0.3rem 0.5rem;
    border-radius: 4px;
    border: 1px solid var(--color-henry-600);
    background: var(--color-henry-900);
    color: white;
    font-size: 0.8rem;
  }
  .lonely-action-group {
    gap: 0.5rem;
    flex-wrap: wrap;
  }
  .lonely-search-wrap {
    position: relative;
  }
  .lonely-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background: var(--color-henry-800);
    border: 1px solid var(--color-henry-600);
    border-radius: 6px;
    z-index: 100;
    overflow: hidden;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    margin-top: 2px;
  }
  .lonely-option {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    padding: 0.4rem 0.6rem;
    border: none;
    background: transparent;
    color: var(--color-henry-200);
    cursor: pointer;
    font-size: 0.82rem;
    text-align: left;
  }
  .lonely-option:hover {
    background: var(--color-henry-700);
  }
  .lonely-option .option-stats {
    font-size: 0.72rem;
    color: var(--color-henry-500);
  }
  .lonely-target-badge {
    font-size: 0.78rem;
    color: var(--color-accent);
    font-weight: 600;
    white-space: nowrap;
  }
  .merge-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  .cluster-summary {
    color: var(--color-henry-300);
    font-size: 0.9rem;
    margin: 0;
  }
  .merge-controls {
    display: flex;
    align-items: center;
    gap: 1rem;
  }
  .merge-controls label {
    color: var(--color-henry-400);
    font-size: 0.85rem;
  }
  .merge-controls select {
    padding: 0.3rem 0.5rem;
    border-radius: 4px;
    border: 1px solid var(--color-henry-600);
    background: var(--color-henry-900);
    color: white;
  }

  .loading-state, .empty-state {
    text-align: center;
    padding: 3rem;
    color: var(--color-henry-400);
  }

  /* ── Cluster card ── */
  .cluster-card {
    background: var(--color-henry-800);
    border: 1px solid var(--color-henry-700);
    border-radius: 10px;
    padding: 1rem 1.25rem;
    margin-bottom: 1rem;
  }
  .cluster-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 0.75rem;
  }
  .cluster-header h3 {
    margin: 0;
    font-size: 1.1rem;
    color: var(--color-henry-100);
  }
  .cluster-meta {
    font-size: 0.8rem;
    color: var(--color-henry-400);
  }

  /* ── Variant rows ── */
  .variant-list {
    border-radius: 6px;
    overflow: hidden;
    border: 1px solid var(--color-henry-700);
  }
  .variant-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--color-henry-700);
    background: var(--color-henry-850, #151525);
  }
  .variant-row:last-child {
    border-bottom: none;
  }
  .variant-row.canonical {
    background: color-mix(in srgb, var(--color-accent) 8%, var(--color-henry-850, #151525));
    border-left: 3px solid var(--color-accent);
  }
  .variant-info {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex: 1;
    min-width: 0;
  }
  .canonical-badge {
    font-size: 0.65rem;
    font-weight: 700;
    background: var(--color-accent);
    color: white;
    padding: 0.15rem 0.4rem;
    border-radius: 3px;
    flex-shrink: 0;
  }
  .merge-badge {
    font-size: 0.85rem;
    color: var(--color-henry-500);
    flex-shrink: 0;
  }
  .variant-name {
    font-size: 0.9rem;
    color: var(--color-henry-200);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .artist-inline {
    font-size: 0.78rem;
    color: var(--color-henry-500);
    margin-left: 0.25rem;
  }
  .variant-stats {
    font-size: 0.78rem;
    color: var(--color-henry-400);
    flex-shrink: 0;
  }
  .variant-actions {
    flex-shrink: 0;
    margin-left: 0.5rem;
  }
  .canonical-label {
    font-size: 0.75rem;
    color: var(--color-accent);
    font-style: italic;
  }

  .cluster-actions {
    margin-top: 0.75rem;
    display: flex;
    justify-content: flex-end;
  }

  /* ── Buttons ── */
  .btn-primary {
    padding: 0.5rem 1rem;
    background: var(--color-accent);
    border: none;
    color: white;
    border-radius: 6px;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .btn-primary:hover { opacity: 0.9; }
  .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

  .btn-secondary {
    padding: 0.4rem 0.8rem;
    background: var(--color-henry-700);
    border: 1px solid var(--color-henry-600);
    color: var(--color-henry-200);
    border-radius: 6px;
    cursor: pointer;
  }
  .btn-secondary:hover { background: var(--color-henry-600); }

  .btn-merge-single {
    padding: 0.25rem 0.6rem;
    background: transparent;
    border: 1px solid var(--color-henry-500);
    color: var(--color-henry-300);
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.78rem;
  }
  .btn-merge-single:hover {
    background: var(--color-henry-700);
    color: white;
  }

  /* ── Modal ── */
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.8);
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
    max-width: 550px;
    border: 1px solid var(--color-henry-600);
  }
  .preview-modal h3 {
    margin: 0 0 1rem;
  }
  .preview-summary {
    color: var(--color-henry-300);
    margin-bottom: 1rem;
  }
  .preview-stats {
    display: flex;
    gap: 2rem;
    margin-bottom: 1rem;
  }
  .stat {
    display: flex;
    flex-direction: column;
  }
  .stat-value {
    font-size: 1.6rem;
    font-weight: 700;
    color: var(--color-accent);
  }
  .stat-label {
    font-size: 0.8rem;
    color: var(--color-henry-400);
  }
  .preview-details {
    border: 1px solid var(--color-henry-700);
    border-radius: 6px;
    margin-bottom: 1rem;
    max-height: 200px;
    overflow-y: auto;
  }
  .preview-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0.75rem;
    border-bottom: 1px solid var(--color-henry-700);
    font-size: 0.85rem;
  }
  .preview-row:last-child { border-bottom: none; }
  .source-name { color: var(--color-henry-300); }
  .arrow { color: var(--color-accent); font-weight: 700; }
  .target-name { color: white; font-weight: 600; }
  .affected { color: var(--color-henry-500); font-size: 0.78rem; margin-left: auto; }

  .preview-actions {
    display: flex;
    gap: 1rem;
    justify-content: flex-end;
  }

  /* ── Toast ── */
  .toast {
    position: fixed;
    bottom: 2rem;
    right: 2rem;
    padding: 0.8rem 1.4rem;
    border-radius: 8px;
    font-weight: 600;
    z-index: 2000;
    animation: slideIn 0.2s ease-out;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  }
  .toast.success {
    background: #1a6b3c;
    color: white;
    border: 1px solid #2ea85c;
  }
  .toast.error {
    background: #6b1a1a;
    color: white;
    border: 1px solid #c23b3b;
  }
  .toast.info {
    background: #1a3c6b;
    color: white;
    border: 1px solid #3b7dc2;
  }
  @keyframes slideIn {
    from { transform: translateY(20px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }

  /* ── Edit tab — existing styles ── */
  .edit-panel { max-width: 900px; }
  .search-bar {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
  }
  .search-bar select {
    padding: 0.4rem;
    border-radius: 4px;
    border: 1px solid var(--color-henry-600);
    background: var(--color-henry-900);
    color: white;
  }
  .search-bar input {
    flex: 1;
    padding: 0.4rem 0.6rem;
    border-radius: 4px;
    border: 1px solid var(--color-henry-600);
    background: var(--color-henry-900);
    color: white;
  }
  .search-bar button {
    padding: 0.4rem 0.8rem;
    background: var(--color-accent);
    border: none;
    color: white;
    border-radius: 4px;
    cursor: pointer;
  }
  .card {
    background: var(--color-henry-800);
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1rem;
  }
  .card-header {
    display: flex;
    gap: 0.75rem;
    align-items: center;
    flex-wrap: wrap;
  }
  .card-header strong { color: var(--color-henry-100); }
  .card-header input {
    padding: 0.3rem 0.5rem;
    border-radius: 4px;
    border: 1px solid var(--color-henry-600);
    background: var(--color-henry-900);
    color: white;
  }
  .card-header button {
    padding: 0.3rem 0.6rem;
    background: var(--color-accent);
    border: none;
    color: white;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.85rem;
  }
  .id-label {
    color: var(--color-henry-500);
    font-weight: 400;
    font-size: 0.8rem;
  }

  /* ── Rename tab ── */
  .rename-panel { max-width: 600px; }
  .rename-panel .card { padding: 1.5rem; margin-bottom: 1rem; }
  .rename-panel h3 { margin: 0 0 0.5rem; }
  .help-text { font-size: 0.8rem; color: var(--color-henry-400); margin: 0 0 1rem; }
  .rename-form { display: flex; flex-direction: column; gap: 0.75rem; }
  .rename-form .form-group { display: flex; flex-direction: column; gap: 0.25rem; }
  .rename-form label { font-size: 0.8rem; color: var(--color-henry-400); font-weight: 500; }
  .rename-form input {
    padding: 0.5rem 0.7rem;
    border-radius: 6px;
    border: 1px solid var(--color-henry-600);
    background: var(--color-henry-900);
    color: white;
    font-size: 0.9rem;
  }
  .rename-btn {
    margin-top: 0.25rem;
    padding: 0.6rem;
    border: none;
    border-radius: 6px;
    background: var(--color-accent);
    color: white;
    font-weight: 600;
    cursor: pointer;
    font-size: 0.9rem;
  }
  .rename-btn:disabled { opacity: 0.5; }
  .rename-result {
    margin: 0;
    font-size: 0.85rem;
    font-weight: 600;
  }

  /* ── Tracks tab ── */
  .tracks-panel { max-width: 1000px; }
  .tracks-search { display: flex; gap: 0.75rem; }
  .tracks-search input {
    flex: 1;
    padding: 0.6rem 0.8rem;
    border-radius: 6px;
    border: 1px solid var(--color-henry-600);
    background: var(--color-henry-900);
    color: white;
    font-size: 0.95rem;
  }
  .tracks-search button {
    padding: 0.6rem 1.2rem;
    border-radius: 6px;
    border: none;
    background: var(--color-accent);
    color: white;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
  }
  .tracks-search button:disabled { opacity: 0.5; }
  .tracks-count { font-size: 0.8rem; color: var(--color-henry-400); margin: 0 0 0.75rem; }
  .no-results { text-align: center; color: var(--color-henry-400); padding: 2rem 0; }
  .data-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  .data-table th { text-align: left; padding: 0.5rem 0.75rem; font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-henry-300); border-bottom: 1px solid var(--color-henry-600); }
  .data-table td { padding: 0.4rem 0.75rem; border-bottom: 1px solid var(--color-henry-700); }
  .data-table .right { text-align: right; }
  .track-title-cell { font-weight: 600; }
  .drill-btn { padding: 0.2rem 0.4rem; border: none; background: transparent; color: var(--color-henry-400); cursor: pointer; font-size: 0.8rem; }
  .drill-btn:hover { color: var(--color-accent); }
  .drill-row td { background: var(--color-henry-700); }
  .drill-episodes { display: flex; flex-wrap: wrap; gap: 0.3rem; align-items: center; padding: 0.3rem 0; }
  .ep-chip { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; background: var(--color-henry-600); color: var(--color-henry-300); font-size: 0.75rem; font-weight: 600; text-decoration: none; }
  .ep-chip:hover { background: var(--color-accent); color: white; }
  .edit-all-btn { padding: 0.15rem 0.5rem; border-radius: 4px; border: 1px solid var(--color-henry-500); background: transparent; color: var(--color-henry-300); font-size: 0.75rem; cursor: pointer; margin-left: 0.5rem; }
  .edit-all-btn:hover { border-color: var(--color-accent); color: var(--color-accent); }

  /* ── History tab ── */
  .history-panel { max-width: 1000px; }
  .history-controls { display: flex; align-items: center; gap: 1rem; }
  .history-controls button { padding: 0.5rem 1rem; border-radius: 6px; border: none; background: var(--color-accent); color: white; font-weight: 600; cursor: pointer; }
  .history-controls button:disabled { opacity: 0.5; }
  .history-count { font-size: 0.8rem; color: var(--color-henry-400); }
  .history-date { font-size: 0.8rem; color: var(--color-henry-400); white-space: nowrap; }
  .history-title { font-weight: 500; max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .history-change { font-size: 0.78rem; max-width: 350px; }
  .change-line { display: block; line-height: 1.4; }
  .change-field { color: var(--color-henry-500); font-weight: 600; }
  .change-old { color: var(--color-henry-400); text-decoration: line-through; }
  .change-arrow { color: var(--color-henry-500); margin: 0 0.25rem; }
  .change-new { color: var(--color-accent); }
  .revert-btn { padding: 0.2rem 0.5rem; border: 1px solid var(--color-henry-600); border-radius: 4px; background: transparent; color: var(--color-henry-400); cursor: pointer; font-size: 0.85rem; }
  .revert-btn:hover { border-color: var(--color-accent); color: var(--color-accent); }
</style>
