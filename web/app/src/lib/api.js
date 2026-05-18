/**
 * API client for the Henry Rollins backend.
 * All calls go through Vite's proxy (/api → localhost:8000).
 */

const BASE = "/api";

async function fetchJson(url, options = {}) {
	const res = await fetch(`${BASE}${url}`, {
		headers: { Accept: "application/json", ...options.headers },
		...options,
	});
	if (!res.ok) {
		throw new Error(`API error: ${res.status} ${res.statusText}`);
	}
	return res.json();
}

export const api = {
	// ── Stats / Dashboard ──
	overview: () => fetchJson("/stats/overview"),
	topArtists: (limit = 10, metric = "plays") =>
		fetchJson(`/stats/top-artists?limit=${limit}&metric=${metric}`),
	topAlbums: (limit = 10) => fetchJson(`/stats/top-albums?limit=${limit}`),
	topTracks: (limit = 10) => fetchJson(`/stats/top-tracks?limit=${limit}`),
	heatmap: () => fetchJson("/stats/heatmap"),
	recentEpisodes: (limit = 5) =>
		fetchJson(`/stats/recent-episodes?limit=${limit}`),

	// ── Episodes ──
	episodes: (page = 1, perPage = 20, sort = "-broadcast") =>
		fetchJson(`/episodes?page=${page}&per_page=${perPage}&sort=${sort}`),
	episode: (broadcast) => fetchJson(`/episodes/${broadcast}`),

	// ── Artists ──
	artists: (page = 1, perPage = 50, sort = "-plays", search = "") => {
		let url = `/artists?page=${page}&per_page=${perPage}&sort=${sort}`;
		if (search) url += `&search=${encodeURIComponent(search)}`;
		return fetchJson(url);
	},
	artist: (name) => fetchJson(`/artists/${encodeURIComponent(name)}`),
	artistTracks: (name, page = 1) =>
		fetchJson(
			`/artists/tracks/${encodeURIComponent(name)}?page=${page}&per_page=50`,
		),
	artistTimeline: (name) =>
		fetchJson(`/artists/timeline/${encodeURIComponent(name)}`),
	artistHeatmap: (name) =>
		fetchJson(`/artists/heatmap/${encodeURIComponent(name)}`),
	topArtistsList: (limit = 20, metric = "plays") =>
		fetchJson(`/artists/top?limit=${limit}&metric=${metric}`),

	// ── Albums ──
	albums: (page = 1, perPage = 50, sort = "-plays", search = "") => {
		let url = `/albums?page=${page}&per_page=${perPage}&sort=${sort}`;
		if (search) url += `&search=${encodeURIComponent(search)}`;
		return fetchJson(url);
	},
	album: (name) => fetchJson(`/albums/${encodeURIComponent(name)}`),
	albumHeatmap: (name) => fetchJson(`/albums/heatmap/${encodeURIComponent(name)}`),

	// ── Recommends (Bandcamp) ──
	recommends: (
		page = 1,
		perPage = 30,
		sort = "-episode_count",
		linkType = "album",
	) =>
		fetchJson(
			`/recommends?page=${page}&per_page=${perPage}&sort=${sort}&link_type=${linkType}`,
		),
	recommendArtists: () => fetchJson("/recommends/artists"),

	// ── Tracks ──
	tracks: (page = 1, perPage = 50, sort = "-plays", search = "") => {
		let url = `/tracks?page=${page}&per_page=${perPage}&sort=${sort}`;
		if (search) url += `&search=${encodeURIComponent(search)}`;
		return fetchJson(url);
	},

	// ── Artist Albums ──
	artistAlbums: (name) => fetchJson(`/artists/albums/${encodeURIComponent(name)}`),

	// ── Search ──
	search: (q) => fetchJson(`/search?q=${encodeURIComponent(q)}`),
};
