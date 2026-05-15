<script>
  let { type = 'regular' } = $props();
  
  const badges = {
    fanatic_favorite: { label: 'Fanatic Favorite', icon: '🔥', color: '#ff6b35' },
    signature_artist: { label: 'Signature Artist', icon: '🏆', color: '#ffd700' },
    deep_cut: { label: 'Deep Cut', icon: '💎', color: '#50c878' },
    regular: { label: 'Regular', icon: '🎵', color: '#7c7cba' },
  };
  
  let badge = $derived(badges[type] || badges.regular);
</script>

<span class="badge" style="--badge-color: {badge.color}">
  {badge.icon} {badge.label}
</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.2rem 0.6rem;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
    background: color-mix(in srgb, var(--badge-color) 15%, transparent);
    color: var(--badge-color);
    border: 1px solid color-mix(in srgb, var(--badge-color) 30%, transparent);
    white-space: nowrap;
  }
</style>
