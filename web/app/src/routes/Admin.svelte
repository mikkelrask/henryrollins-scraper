<script>
  import { api } from '../lib/api.js';
  import { router } from '../lib/router.svelte.js';
  import EntityIntelligence from '../lib/components/EntityIntelligence.svelte';
  import TrackEditor from '../lib/components/TrackEditor.svelte';

  let entityType = $state('artist');
  let searchTerm = $state('');
  let results = $state([]);
  let loading = $state(false);
  let editor = $state({ show: false, mode: 'edit', track: null });
  let targets = $state({});

  async function search() {
    loading = true;
    const res = await fetch(`/api/admin/entities?type=${entityType}&q=${encodeURIComponent(searchTerm)}`);
    results = await res.json();
    loading = false;
  }

  async function reassign(sourceId) {
    const targetId = targets[sourceId];
    if (!targetId || !confirm('Reassign records to ID ' + targetId + '?')) return;
    
    try {
        const res = await fetch(`/api/admin/reassign?type=${entityType}&source_id=${sourceId}&target_id=${targetId}`, { method: 'POST' });
        if (res.ok) { 
            alert('Reassigned!'); 
            search(); 
        } else {
            const err = await res.text();
            alert('Error: ' + err);
        }
    } catch (e) {
        alert('Reassign failed: ' + e.message);
    }
  }
</script>

<TrackEditor 
  show={editor.show} 
  onshowchange={(val) => editor.show = val} 
  mode={editor.mode} 
  track={editor.track} 
  onSave={search} 
/>

<div class="page">
  <header class="page-header">
    <h1>Admin Center</h1>
  </header>

  <div class="admin-panel">
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
            <strong>{entity.name} (ID: {entity.id})</strong>
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
</div>

<style>
  .card { background: var(--color-henry-800); border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
  .card-header { display: flex; gap: 1rem; align-items: center; }
  .controls { margin-bottom: 2rem; }
  input { padding: 0.4rem; border-radius: 4px; border: 1px solid var(--color-henry-600); background: var(--color-henry-900); color: white; }
  button { padding: 0.4rem 0.8rem; background: var(--color-accent); border: none; color: white; border-radius: 4px; cursor: pointer; }
</style>
