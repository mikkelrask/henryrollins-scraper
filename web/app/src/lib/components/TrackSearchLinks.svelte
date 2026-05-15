<script>
	/**
	 * Renders the search links for Mono and YouTube.
	 */
	let { artist, title } = $props();

	const monoUrl = $derived(
		`https://mono.squid.wtf/search/${encodeURIComponent(artist + " " + title)}`,
	);
	const youtubeUrl = $derived(
		`https://www.youtube.com/results?q=${encodeURIComponent(artist + " " + title)}`,
	);
</script>

<div class="search-links">
	<a href={monoUrl} target="_blank" rel="noopener" class="link-btn mono" title="Search on Mono">
		<svg viewBox="0 0 24 24" fill="currentColor">
			<path d="M8 5v14l11-7z" />
		</svg>
	</a>
	<a href={youtubeUrl} target="_blank" rel="noopener" class="link-btn youtube" title="Search on YouTube">
		<svg viewBox="0 0 24 24" fill="currentColor">
			<path d="M19.615 3.184c-3.604-.246-11.631-.245-15.23 0-3.897.266-4.356 2.62-4.385 8.816.029 6.185.484 8.549 4.385 8.816 3.6.245 11.626.246 15.23 0 3.897-.266 4.356-2.62 4.385-8.816-.029-6.185-.484-8.549-4.385-8.816zm-10.615 12.816v-8l8 3.993-8 4.007z" />
		</svg>
	</a>
</div>

<style>
	.search-links {
		display: inline-flex;
		gap: 0.5rem;
		align-items: center;
	}
	.link-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 24px;
		height: 24px;
		border-radius: 4px;
		transition: all 0.2s;
		color: var(--color-henry-400);
		background: var(--color-henry-700);
	}
	.link-btn:hover {
		color: white;
		transform: scale(1.1);
	}
	.mono:hover { background: var(--color-accent); }
	.youtube:hover { background: #ff0000; }
	svg { width: 14px; height: 14px; }
</style>
