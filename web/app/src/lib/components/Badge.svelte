<script>
  let { type = 'regular' } = $props();
  
  const badges = {
    fanatic_favorite: { label: 'Fanatic Favorite', color: '#ff3d1a' },
    signature_artist: { label: 'Signature Artist', color: '#ffcc00' },
    deep_cut: { label: 'Deep Cut', color: '#3fb37f' },
    regular: { label: 'Regular', color: '#9c9c9c' },
  };

  let badge = $derived(badges[type] || badges.regular);
</script>

<span class="badge" style="--badge-color: {badge.color}">
  {badge.label}
</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    padding: 0.2rem 0.5rem;
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    background: var(--badge-color);
    color: #090909;
    border: 1px solid var(--badge-color);
    white-space: nowrap;
  }
</style>
