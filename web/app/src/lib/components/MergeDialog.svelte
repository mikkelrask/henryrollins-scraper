<script>
  /**
   * MergeDialog — inline search-and-merge component.
   *
   * Props:
   *   entity   — the current entity { id, name, type: 'artist'|'album', ... }
   *   show     — whether the dialog is visible
   * Events:
   *   close    — user dismissed the dialog
   *   merged   — merge succeeded; detail = { target, result }
   */
  import { authFetch } from '../useAuth.svelte.js';
  let { entity, show = false, onclose, onmerged } = $props();

  let searchQuery = $state("");
  let results = $state([]);
  let selected = $state(null);
  let merging = $state(false);
  let error = $state("");
  let searchTimer = $state(null);

  let dropdownEl;

  function handleKeydown(e) {
    if (e.key === "Escape") {
      close();
    }
  }

  // Close when clicking outside
  function handleBackdrop(e) {
    if (e.target === e.currentTarget) {
      close();
    }
  }

  function close() {
    searchQuery = "";
    results = [];
    selected = null;
    error = "";
    onclose?.();
  }

  function doSearch(value) {
    searchQuery = value;
    selected = null;
    if (searchTimer) clearTimeout(searchTimer);
    if (value.length < 2) {
      results = [];
      return;
    }
    searchTimer = setTimeout(async () => {
      try {
        const res = await authFetch(
          `/api/admin/entities?type=${entity.type}&q=${encodeURIComponent(value)}`
        );
        if (!res.ok) throw new Error("Search failed");
        const data = await res.json();
        // Filter out the current entity
        results = data.filter((e) => e.id !== entity.id).slice(0, 6);
      } catch (e) {
        results = [];
      }
    }, 250);
  }

  function selectTarget(target) {
    selected = target;
    results = [];
  }

  async function doMerge() {
    if (!selected || merging) return;
    merging = true;
    error = "";
    try {
      const res = await authFetch(
        `/api/admin/merge?type=${encodeURIComponent(entity.type)}&source_ids=${entity.id}&target_id=${selected.id}`,
        { method: "POST" },
      );
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || `Server error ${res.status}`);
      }
      const result = await res.json();
      onmerged?.({ target: selected, result });
      close();
    } catch (e) {
      error = e.message;
    } finally {
      merging = false;
    }
  }
</script>

{#if show}
  <div class="merge-dialog-backdrop" onclick={handleBackdrop} onkeydown={handleKeydown}>
    <div class="merge-dialog" role="dialog" aria-label="Merge entity">
      <div class="dialog-header">
        <h3>Merge "{entity.name}"</h3>
        <button class="dialog-close" onclick={close} aria-label="Close">✕</button>
      </div>
      <p class="dialog-hint">
        Search for the {entity.type} you want to merge <strong>into</strong>.
        Tracks and data from "{entity.name}" will be reassigned to the target.
      </p>

      <div class="search-area">
        <input
          type="text"
          placeholder="Search {entity.type}s..."
          value={searchQuery}
          oninput={(e) => doSearch(e.target.value)}
          class="merge-search-input"
          autofocus
        />
        {#if results.length > 0}
          <div class="merge-dropdown" bind:this={dropdownEl}>
            {#each results as ent}
              <button class="merge-option" onclick={() => selectTarget(ent)}>
                <span class="option-name">{ent.name}</span>
                <span class="option-meta">
                  {ent.track_count} tracks
                  {#if ent.artist_name}
                    · {ent.artist_name}
                  {/if}
                </span>
              </button>
            {/each}
          </div>
        {/if}
      </div>

      {#if selected}
        <div class="selected-target">
          <span class="label">Merging into:</span>
          <span class="value">{selected.name}</span>
          {#if selected.artist_name}
            <span class="artist-hint">by {selected.artist_name}</span>
          {/if}
          <span class="track-hint">({selected.track_count} tracks)</span>
        </div>
      {/if}

      {#if error}
        <div class="merge-error">{error}</div>
      {/if}

      <div class="dialog-actions">
        <button class="btn-cancel" onclick={close}>Cancel</button>
        <button
          class="btn-merge"
          disabled={!selected || merging}
          onclick={doMerge}
        >
          {merging ? "Merging..." : "Merge → Target"}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .merge-dialog-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  .merge-dialog {
    background: #1a1a1a;
    border: 1px solid #444;
    border-radius: 12px;
    padding: 1.5rem;
    width: 460px;
    max-width: 90vw;
    box-shadow: 0 8px 30px rgba(0,0,0,0.5);
    color: #ddd;
  }
  .dialog-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }
  .dialog-header h3 {
    margin: 0;
    font-size: 1.05rem;
    color: #fff;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .dialog-close {
    background: none;
    border: none;
    color: #888;
    font-size: 1.1rem;
    cursor: pointer;
    padding: 0.2rem 0.4rem;
    border-radius: 4px;
  }
  .dialog-close:hover {
    background: #333;
    color: #fff;
  }
  .dialog-hint {
    font-size: 0.82rem;
    color: #999;
    margin: 0 0 1rem;
    line-height: 1.4;
  }
  .search-area {
    position: relative;
  }
  .merge-search-input {
    width: 100%;
    box-sizing: border-box;
    padding: 0.5rem 0.7rem;
    border-radius: 6px;
    border: 1px solid #555;
    background: #222;
    color: #fff;
    font-size: 0.9rem;
    outline: none;
  }
  .merge-search-input:focus {
    border-color: #eac117;
  }
  .merge-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background: #222;
    border: 1px solid #555;
    border-top: none;
    border-radius: 0 0 6px 6px;
    z-index: 10;
    overflow: hidden;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  }
  .merge-option {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    padding: 0.5rem 0.7rem;
    border: none;
    background: transparent;
    color: #ddd;
    cursor: pointer;
    font-size: 0.85rem;
    text-align: left;
  }
  .merge-option:hover {
    background: #333;
  }
  .merge-option .option-meta {
    font-size: 0.75rem;
    color: #888;
  }
  .selected-target {
    margin-top: 0.75rem;
    padding: 0.5rem 0.7rem;
    background: #2a2a2a;
    border-radius: 6px;
    font-size: 0.85rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    align-items: baseline;
  }
  .selected-target .label {
    color: #888;
  }
  .selected-target .value {
    color: #eac117;
    font-weight: 600;
  }
  .selected-target .artist-hint {
    color: #aaa;
    font-size: 0.8rem;
  }
  .selected-target .track-hint {
    color: #666;
    font-size: 0.78rem;
  }
  .merge-error {
    margin-top: 0.5rem;
    padding: 0.4rem 0.6rem;
    background: #4a1515;
    border-radius: 4px;
    color: #e88;
    font-size: 0.8rem;
  }
  .dialog-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-top: 1rem;
  }
  .btn-cancel {
    padding: 0.4rem 1rem;
    border: 1px solid #555;
    border-radius: 6px;
    background: transparent;
    color: #aaa;
    cursor: pointer;
    font-size: 0.85rem;
  }
  .btn-cancel:hover {
    background: #333;
    color: #fff;
  }
  .btn-merge {
    padding: 0.4rem 1rem;
    border: none;
    border-radius: 6px;
    background: #c0392b;
    color: #fff;
    cursor: pointer;
    font-size: 0.85rem;
    font-weight: 600;
  }
  .btn-merge:hover:not(:disabled) {
    background: #e74c3c;
  }
  .btn-merge:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
