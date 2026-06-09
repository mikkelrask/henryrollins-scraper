/**
 * Minimal hash-based router for Svelte 5 (runes mode).
 *
 * Usage in +layout.svelte or App.svelte:
 *   import { router } from './lib/router.svelte.js';
 *   <a href="#/artists" onclick={router.navigate}>Artists</a>
 *
 *   {#key router.navCount}
 *     <RouterOutlet route={router.current} />
 *   {/key}
 */

import { tick } from "svelte";

// Route definitions
const routes = {
	"/": () => import("../routes/Home.svelte"),
	"/artists": () => import("../routes/Artists.svelte"),
	"/artist/:name": (params) => import("../routes/ArtistDetail.svelte"),
	"/artist/:name/albums": (params) => import("../routes/ArtistAlbums.svelte"),
	"/albums": () => import("../routes/Albums.svelte"),
	"/album/:artist/:name": (params) => import("../routes/AlbumDetail.svelte"),
	"/episodes": () => import("../routes/Episodes.svelte"),
	"/episode/:broadcast": (params) => import("../routes/EpisodeDetail.svelte"),
	"/tracks": () => import("../routes/Tracks.svelte"),
	"/recommends": () => import("../routes/Recommends.svelte"),
	"/insights": () => import("../routes/Insights.svelte"),
	"/admin": () => import("../routes/Admin.svelte"),
	"/search/:query": (params) => import("../routes/Search.svelte"),
};

// ── URL-safe segment encoding (handles `/` in names) ──
// Browser can decode %2F in hash fragments, breaking path matching.
// We replace %2F with ~~ which is URL-safe and never decoded.
export function urlSegment(value) {
	return encodeURIComponent(value).replace(/%2F/g, "~~");
}
function fromUrlSegment(value) {
	return decodeURIComponent(value).replace(/~~/g, "/");
}

// Parse query string from hash path (e.g. "/artists?country=US")
function parseQuery(rawPath) {
	const decoded = rawPath.replace(/%3[Ff]/g, "?");
	const idx = decoded.indexOf("?");
	if (idx === -1) return { cleanPath: decoded, query: {} };
	const q = new URLSearchParams(decoded.slice(idx + 1));
	const query = {};
	for (const [k, v] of q) query[k] = v;
	return { cleanPath: decoded.slice(0, idx), query };
}

// Simple path matching
function matchRoute(hash) {
	const rawPath = hash.replace(/^#/, "") || "/";
	const { cleanPath, query } = parseQuery(rawPath);

	for (const [pattern, loader] of Object.entries(routes)) {
		const paramNames = [];
		const regexStr = pattern.replace(/:([^/]+)/g, (_, name) => {
			paramNames.push(name);
			return "([^/]+)";
		});
		const regex = new RegExp(`^${regexStr}$`);
		const match = cleanPath.match(regex);

		if (match) {
			const params = {};
			paramNames.forEach((name, i) => {
				params[name] = fromUrlSegment(match[i + 1]);
			});
			return { path: rawPath, pattern, params, query, loader };
		}
	}

	// 404 fallback
	return { path: rawPath, pattern: "/", params: {}, query, loader: routes["/"] };
}

// Reactive router state
let _route = $state(matchRoute(window.location.hash));
let _component = $state(null);
let _componentParams = $state({});
let _loading = $state(false);
let _navCount = $state(0);

export const router = {
	get current() {
		return _route;
	},
	get component() {
		return _component;
	},
	get params() {
		return _componentParams;
	},
	get loading() {
		return _loading;
	},
	get navCount() {
		return _navCount;
	},

	async navigate(event) {
		event.preventDefault();
		const href = event.currentTarget.getAttribute("href");
		window.location.hash = href;
	},

	async goto(path) {
		window.location.hash = path;
	},
};

// Listen for hash changes
if (typeof window !== "undefined") {
	window.addEventListener("hashchange", async () => {
		_loading = true;
		_route = matchRoute(window.location.hash);
		_navCount++;

		try {
			const mod = await _route.loader(_route.params);
			_component = mod.default;
			_componentParams = { ..._route.query, ..._route.params };
		} catch (e) {
			console.error("Route load failed:", e);
			_component = null;
		}

		_loading = false;
		await tick();
		window.scrollTo(0, 0);
	});

	// Initial load
	(async () => {
		_loading = true;
		try {
			const mod = await _route.loader(_route.params);
			_component = mod.default;
			_componentParams = { ..._route.query, ..._route.params };
		} catch (e) {
			console.error("Initial route load failed:", e);
		}
		_loading = false;
		_navCount++;
	})();
}
