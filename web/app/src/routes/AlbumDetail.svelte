<script>
  import { onMount } from 'svelte';
  import { api } from '../lib/api.js';
  import { router, urlSegment } from '../lib/router.svelte.js';
  import MergeDialog from '../lib/components/MergeDialog.svelte';
  import TrackSearchLinks from '../lib/components/TrackSearchLinks.svelte';
  import TrackEditor from '../lib/components/TrackEditor.svelte';
  import { auth, authFetch } from '../lib/useAuth.svelte.js';

  let { params = {} } = $props();
  let albumName = $derived(params.name);
  let albumArtist = $derived(params.artist);

  let album = $state(null);
  let heatmapData = $state([]);
  let loading = $state(true);
  let showMerge = $state(false);
  let showAlbumEdit = $state(false);
  let expanded = $state({});
  let editor = $state({ show: false, track: null });
  let albumEditForm = $state({ name: '', mbid: '', release_group_mbid: '' });

  function editTrack(track) {
    editor = { show: true, track: {
      ...track,
      artist: album.artist,
      album: album.album,
      album_mbid: album.mbid,
      album_release_group_mbid: album.release_group_mbid,
    }};
  }

  async function reloadAlbum() {
    try {
      const alb = await api.album(albumName, albumArtist);
      album = alb;
      heatmapData = alb.heatmap || [];
    } catch (e) {
      console.error(e);
    }
  }

  async function saveAlbumEdit() {
    const res = await authFetch('/api/admin/edit-album', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        artist: album.artist,
        old_name: album.album,
        name: albumEditForm.name || album.album,
        mbid: albumEditForm.mbid || null,
        release_group_mbid: albumEditForm.release_group_mbid || null,
      }),
    });
    if (res.ok) {
      showAlbumEdit = false;
      if (albumEditForm.name && albumEditForm.name !== album.album) {
        // Album renamed — navigate to new URL
        router.goto(`/album/${urlSegment(album.artist)}/${urlSegment(albumEditForm.name)}`);
      } else {
        reloadAlbum();
      }
    }
  }

  function getEpisodeId(track) {
    const play = track.broadcasts?.[0];
    if (!play) return null;
    return play.broadcast ?? play.date;
  }

  onMount(async () => {
    try {
      const alb = await api.album(albumName, albumArtist);
      album = alb;
      heatmapData = alb.heatmap || [];
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  });

  // Trend pulse logic (matches artist page)
  let heatmapCells = $derived.by(() => {
    if (!heatmapData.length) return [];
    const cells = [];
    const maxPlays = Math.max(...heatmapData.map(d => d.plays), 1);
    for (const item of heatmapData) {
      const intensity = item.plays / maxPlays;
      const level = intensity > 0.7 ? 4 : intensity > 0.4 ? 3 : intensity > 0.15 ? 2 : intensity > 0 ? 1 : 0;
      cells.push({ ...item, level });
    }
    return cells;
  });

  let years = $derived([...new Set(heatmapCells.map(c => c.year))].sort());

  function back(e) {
    e.preventDefault();
    router.goto('/albums');
  }
</script>

{#if loading}
  <div class="loading-pulse"><div class="pulse-block" style="height:400px"></div></div>
{:else if album}
  <div class="page">
    <header class="album-header-new">
      <div class="header-top">
        <div class="header-identity">
          <a href="#/albums" onclick={back} class="back-link-new">← All Albums</a>

          <div class="album-title-row">
            {#if album.artwork_url_large || album.artwork_url}
              <img src={album.artwork_url_large || album.artwork_url} alt={album.album} class="album-art" loading="lazy" />
            {:else}
              <div class="album-art-placeholder">💿</div>
            {/if}
            <div class="title-artist">
              <h1 class="album-name">{album.album}</h1>
              <p class="album-artist-line">
                by <a href="#/artist/{urlSegment(album.artist)}" onclick={router.navigate} class="artist-link">{album.artist}</a>
              </p>
              {#if album.release_date}
                <p class="release-info">Released: {album.release_date}</p>
              {/if}
              {#if album.release_group_mbid || album.mbid}
                <p class="release-info">
                  <a href="https://musicbrainz.org/release-group/{album.release_group_mbid || album.mbid}" target="_blank" rel="noopener" class="mbid-link">🧠 MusicBrainz</a>
                </p>
              {/if}
            </div>
          </div>
        </div>

        <div class="header-stats-new">
          <div class="stat-box">
            <span class="stat-val">{album.plays}</span>
            <span class="stat-label">Plays</span>
          </div>
          <div class="stat-box">
            <span class="stat-val">{album.distinct_tracks}</span>
            <span class="stat-label">Tracks</span>
          </div>
          <div class="stat-box">
            <span class="stat-val">{album.episodes}</span>
            <span class="stat-label">Episodes</span>
          </div>
          {#if auth.authed}
          <button class="btn-merge-icon" onclick={() => { albumEditForm = { name: album.album, mbid: album.mbid || '', release_group_mbid: album.release_group_mbid || '' }; showAlbumEdit = true; }} title="Edit album name and MBIDs">
            Edit
          </button>
          <button class="btn-merge-icon" onclick={() => showMerge = true} title="Merge this album into another">
            Merge
          </button>
          {/if}
        </div>
      </div>

      <!-- Integrated Trend Timeline (same as artist page) -->
      {#if heatmapCells.length > 0}
        <div class="integrated-trend-container">
          <div class="trend-meta">
            <span class="trend-label">Fanatic History</span>
            <div class="trend-legend">
              <span class="legend-text">Rare</span>
              <div class="legend-pip level-1"></div>
              <div class="legend-pip level-2"></div>
              <div class="legend-pip level-3"></div>
              <div class="legend-pip level-4"></div>
              <span class="legend-text">Heavy</span>
            </div>
          </div>
          <div class="trend-strip">
            {#each heatmapCells as cell}
              <div
                class="trend-pip level-{cell.level}"
                title="{cell.plays} plays in {cell.month}/{cell.year}"
              ></div>
            {/each}
          </div>
          <div class="trend-years">
            {#each years as year, i}
              {#if i === 0 || i === years.length - 1 || i % 3 === 0}
                <span class="trend-year-label">{year}</span>
              {/if}
            {/each}
          </div>
        </div>
      {/if}
    </header>

    <!-- Tracks Played -->
    <section class="card">
      <h2 class="section-title">Tracks Played ({album.tracks.length})</h2>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th></th>
              <th>Track</th>
              <th class="right">Plays</th>
              <th>Last Played</th>
              <th class="right">Listen</th>
              {#if auth.authed}<th></th>{/if}
            </tr>
          </thead>
          <tbody>
            {#each album.tracks as track}
              <tr>
                <td>
                  <button class="chevron" onclick={() => expanded[track.title] = !expanded[track.title]} title="Show all plays">
                    <svg class="chevron-icon {expanded[track.title] ? 'open' : ''}" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
                  </button>
                </td>
                <td class="track-name">{track.title}</td>
                <td class="right bold">{track.plays} play{track.plays !== 1 ? 's' : ''}</td>
                <td>
                  {#if track.last_broadcast}
                    <a href="#/episode/{track.last_broadcast}" onclick={router.navigate} class="track-last-link">#{track.last_broadcast}</a>
                  {:else if track.last_played}
                    <a href="#/episode/{track.last_played}" onclick={router.navigate} class="track-last-link">{track.last_played}</a>
                  {:else}
                    <span class="muted">—</span>
                  {/if}
                </td>
                <td class="right">
                  <TrackSearchLinks artist={album.artist} title={track.title} />
                </td>
                {#if auth.authed}
                  <td>
                    <button class="edit-btn-inline" onclick={() => editTrack(track)} title="Edit track">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                    </button>
                  </td>
                {/if}
              </tr>
              {#if expanded[track.title]}
                <tr class="drill-row">
                  <td colspan="6">
                    <div class="track-plays">
                      {#each track.broadcasts as play}
                        <a href="#/episode/{play.broadcast ?? play.date}" onclick={router.navigate} class="play-chip">{play.broadcast ? `#${play.broadcast}` : play.date}</a>
                      {/each}
                    </div>
                  </td>
                </tr>
              {/if}
            {/each}
          </tbody>
        </table>
      </div>
    </section>

    {#if album.releases?.length}
      <section class="card">
        <h2 class="section-title">Release version ({album.releases.length})</h2>
        <div class="release-grid">
          {#each album.releases as rel}
            <a href="https://musicbrainz.org/release/{rel.mbid}" target="_blank" rel="noopener" class="release-card">
              <div class="release-format">{rel.format || "—"}</div>
              {#if rel.country || rel.date}
                <div class="release-meta">
                  {#if rel.country}<span class="release-country">{rel.country}</span>{/if}
                  {#if rel.date}<span class="release-date">{rel.date}</span>{/if}
                </div>
              {/if}
              {#if rel.status}
                <div class="release-status">{rel.status}</div>
              {/if}
              {#if rel.label}
                <div class="release-label">{rel.label}</div>
              {/if}
            </a>
          {/each}
        </div>
      </section>
    {/if}

    {#if album.unplayed_tracks?.length}
      <section class="card dim">
        <h2 class="section-title">Unplayed Tracks From This Album ({album.unplayed_tracks.length})</h2>
        <div class="top-list">
          {#each album.unplayed_tracks as title}
            <div class="top-row">
              <span class="track-name unplayed">{title}</span>
              <span class="track-stat muted">never played</span>
            </div>
          {/each}
        </div>
      </section>
    {/if}
  </div>

  <TrackEditor
    show={editor.show}
    onshowchange={(val) => editor.show = val}
    track={editor.track}
    episodeId={editor.track ? getEpisodeId(editor.track) : null}
    onSave={reloadAlbum}
    suggestions={album?.unplayed_tracks || []}
  />

  <MergeDialog
    show={showMerge}
    entity={{ id: album.id, name: album.album, type: 'album' }}
    onclose={() => showMerge = false}
    onmerged={(detail) => {
      router.goto(`/album/${urlSegment(detail.target.artist)}/${urlSegment(detail.target.name)}`);
    }}
  />

  {#if showAlbumEdit}
  <div class="modal-overlay" role="button" tabindex="0" onclick={() => showAlbumEdit = false} onkeydown={(e) => e.key === 'Escape' && (showAlbumEdit = false)}>
    <div class="modal-content" role="dialog" aria-modal="true" onclick={(e) => e.stopPropagation()}>
      <h3>Edit Album</h3>

      <div class="ae-form-group">
        <label for="ae-name">Name</label>
        <input id="ae-name" type="text" bind:value={albumEditForm.name} />
      </div>
      <div class="ae-form-group">
        <label for="ae-mbid">MBID</label>
        <input id="ae-mbid" type="text" bind:value={albumEditForm.mbid} placeholder="Release MBID (enables artwork)" />
      </div>
      <div class="ae-form-group">
        <label for="ae-rgmbid">Release Group MBID</label>
        <input id="ae-rgmbid" type="text" bind:value={albumEditForm.release_group_mbid} placeholder="Release Group MBID (links MusicBrainz)" />
      </div>

      <div class="ae-actions">
        <button onclick={() => showAlbumEdit = false}>Cancel</button>
        <button class="ae-save" onclick={saveAlbumEdit}>Save</button>
      </div>
    </div>
  </div>
  {/if}
{/if}

<style>
  .page { animation: fadeIn 0.3s ease-out; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

  .album-header-new {
    margin-bottom: 2rem;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }

  .header-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 2rem;
    flex-wrap: wrap;
  }

  .header-identity { flex: 1; min-width: 300px; }
  .back-link-new {
    color: var(--color-henry-400);
    text-decoration: none;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 0.5rem;
    display: block;
  }
  .back-link-new:hover { color: var(--color-accent); }

  .album-title-row { display: flex; align-items: flex-start; gap: 1.25rem; margin-bottom: 0.75rem; }
  .album-art {
    width: 100px;
    height: 100px;
    border-radius: 8px;
    object-fit: cover;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    flex-shrink: 0;
  }
  .album-art-placeholder {
    width: 100px;
    height: 100px;
    border-radius: 8px;
    background: var(--color-henry-700);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 2rem;
    flex-shrink: 0;
  }
  .title-artist { min-width: 0; }
  .album-name { font-size: 2.2rem; font-weight: 900; margin: 0; line-height: 1.1; letter-spacing: -0.02em; word-break: break-word; }
  .album-artist-line { font-size: 1rem; margin: 0.4rem 0 0; color: var(--color-henry-300); }
  .artist-link { color: var(--color-henry-200); text-decoration: none; font-weight: 600; }
  .artist-link:hover { color: var(--color-accent); text-decoration: underline; }
  .release-info { font-size: 0.8rem; color: var(--color-henry-400); margin: 0.3rem 0 0; }
  .mbid-link { color: var(--color-henry-400); text-decoration: none; font-size: 0.8rem; }
  .mbid-link:hover { color: var(--color-accent); text-decoration: underline; }

  .header-stats-new {
    display: flex;
    gap: 2.5rem;
    padding-bottom: 0.5rem;
  }
  .stat-box { display: flex; flex-direction: column; align-items: flex-end; }
  .btn-merge-icon {
    margin-top: 0.5rem;
    padding: 0.3rem 0.6rem;
    border: 1px solid #555;
    border-radius: 6px;
    background: transparent;
    color: #aaa;
    cursor: pointer;
    font-size: 0.78rem;
  }
  .btn-merge-icon:hover { background: #333; color: #eac117; border-color: #eac117; }
  .stat-val { font-size: 2.2rem; font-weight: 900; line-height: 1; }
  .stat-label { font-size: 0.65rem; color: var(--color-henry-400); text-transform: uppercase; letter-spacing: 0.1em; margin-top: 0.4rem; }

  /* Integrated Trend Strip (matches artist page) */
  .integrated-trend-container {
    padding: 1.5rem 0;
    border-top: 1px solid rgba(255,255,255,0.05);
    border-bottom: 1px solid rgba(255,255,255,0.05);
  }
  .trend-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }
  .trend-label { font-size: 0.7rem; font-weight: 800; text-transform: uppercase; color: var(--color-henry-500); letter-spacing: 0.2em; }
  .trend-legend { display: flex; align-items: center; gap: 4px; }
  .legend-text { font-size: 0.6rem; color: var(--color-henry-500); text-transform: uppercase; margin: 0 4px; }
  .legend-pip { width: 8px; height: 8px; border-radius: 1px; }

  .trend-strip {
    display: flex;
    gap: 3px;
    height: 32px;
    width: 100%;
  }
  .trend-pip {
    flex: 1;
    height: 100%;
    border-radius: 2px;
    transition: all 0.2s;
  }
  .trend-pip:hover {
    transform: scaleY(1.3);
    z-index: 10;
    box-shadow: 0 0 10px var(--color-accent);
  }

  .trend-years {
    display: flex;
    justify-content: space-between;
    margin-top: 0.5rem;
    padding: 0 2px;
  }
  .trend-year-label { font-size: 0.65rem; font-weight: 600; color: var(--color-henry-500); }

  .level-0 { background: rgba(255,255,255,0.03); }
  .level-1 { background: #4a2c1a; }
  .level-2 { background: #8a4a2a; }
  .level-3 { background: var(--color-accent); }
  .level-4 { background: var(--color-gold); box-shadow: 0 0 8px rgba(255, 215, 0, 0.2); }

  .card {
    background: var(--color-henry-800);
    border: 1px solid var(--color-henry-600);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
  }
  .card.dim { opacity: 0.65; }
  .section-title { font-size: 1.1rem; font-weight: 700; margin: 0 0 1rem; }
  .table-wrap { overflow-x: auto; }
  .data-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  .data-table th { text-align: left; padding: 0.5rem 0.75rem; font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-henry-300); border-bottom: 1px solid var(--color-henry-600); white-space: nowrap; }
  .data-table td { padding: 0.4rem 0.75rem; border-bottom: 1px solid var(--color-henry-700); vertical-align: middle; white-space: nowrap; }
  .data-table tr:last-child td { border-bottom: none; }
  .data-table tr:hover { background: var(--color-henry-700); }
  .data-table .right { text-align: right; }
  .data-table .bold { font-weight: 700; color: var(--color-accent); }
  .drill-row td { background: var(--color-henry-700); }
  .chevron {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-henry-400);
    cursor: pointer;
    flex-shrink: 0;
    border-radius: 3px;
    transition: all 0.15s;
  }
  .chevron:hover {
    background: var(--color-henry-600);
    color: var(--color-henry-200);
  }
  .chevron-icon {
    transition: transform 0.2s;
  }
  .chevron-icon.open {
    transform: rotate(180deg);
  }
  .track-name { font-weight: 500; }
  .track-name.unplayed { color: var(--color-henry-400); text-decoration: line-through; }
  .track-last-link {
    font-size: 0.8rem;
    white-space: nowrap;
    color: var(--color-henry-300);
    text-decoration: none;
    transition: color 0.15s;
  }
  .track-last-link:hover { color: var(--color-accent); text-decoration: underline; }
  .edit-btn-inline {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-henry-500);
    cursor: pointer;
    flex-shrink: 0;
    border-radius: 3px;
    transition: all 0.15s;
  }
  .edit-btn-inline:hover { background: var(--color-henry-600); color: var(--color-accent); }
  .muted { color: var(--color-henry-300); }
  .track-plays {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    padding: 0.3rem 0;
  }
  .play-chip {
    display: inline-flex;
    padding: 0.15rem 0.55rem;
    border-radius: 4px;
    background: var(--color-henry-700);
    color: var(--color-henry-300);
    font-size: 0.75rem;
    font-weight: 600;
    text-decoration: none;
    transition: all 0.15s;
  }
  .play-chip:hover {
    background: var(--color-accent);
    color: #fff;
  }

  .release-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 0.75rem;
  }
  .release-card {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    padding: 0.75rem 1rem;
    border-radius: 8px;
    background: var(--color-henry-700);
    border: 1px solid var(--color-henry-600);
    text-decoration: none;
    color: var(--color-henry-200);
    transition: all 0.2s;
  }
  .release-card:hover {
    border-color: var(--color-accent);
    background: var(--color-henry-600);
    transform: translateY(-2px);
  }
  .release-format {
    font-weight: 700;
    font-size: 0.9rem;
    color: var(--color-henry-100);
  }
  .release-meta {
    display: flex;
    gap: 0.5rem;
    font-size: 0.78rem;
    color: var(--color-henry-300);
  }
  .release-country {
    font-weight: 600;
  }
  .release-date {
    color: var(--color-henry-400);
  }
  .release-status {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--color-henry-400);
  }
  .release-label {
    font-size: 0.75rem;
    color: var(--color-henry-400);
  }

  .loading-pulse { padding: 2rem 0; }
  .pulse-block { background: var(--color-henry-800); border-radius: 12px; animation: pulse 1.5s ease-in-out infinite; }
  @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.7; } }

  /* Album edit modal */
  .modal-overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.8);
    display: flex; align-items: center; justify-content: center; z-index: 1000;
  }
  .modal-content {
    background: var(--color-henry-800); padding: 2rem; border-radius: 12px;
    width: 100%; max-width: 480px; border: 1px solid var(--color-henry-600);
  }
  .modal-content h3 { margin: 0 0 1.5rem; }
  .ae-form-group { margin-bottom: 1rem; }
  .ae-form-group label { display: block; font-size: 0.8rem; color: var(--color-henry-400); margin-bottom: 0.25rem; }
  .ae-form-group input {
    width: 100%; padding: 0.6rem; border-radius: 6px;
    border: 1px solid var(--color-henry-600); background: var(--color-henry-900); color: white;
    box-sizing: border-box;
  }
  .ae-actions { display: flex; gap: 1rem; margin-top: 1.5rem; justify-content: flex-end; }
  .ae-actions button {
    padding: 0.5rem 1rem; border-radius: 6px;
    border: 1px solid var(--color-henry-600); background: transparent;
    color: var(--color-henry-200); cursor: pointer;
  }
  .ae-actions .ae-save { background: var(--color-accent); border: none; color: white; }
</style>
