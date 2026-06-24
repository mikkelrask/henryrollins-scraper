import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";

// Hardcoded for Cloudflare Pages production
const API_BASE = '/api';

export default defineConfig({
	plugins: [tailwindcss(), svelte()],
	base: './',
	server: {
		proxy: {
			"/api": {
				target: "http://localhost:8000",
				changeOrigin: true,
			},
		},
	},
});
