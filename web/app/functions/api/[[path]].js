/**
 * Proxy /api/* requests to the Hono Worker backend.
 * This replaces a _redirects rule which was being overridden by the SPA fallback.
 */
export async function onRequest(context) {
	const url = new URL(context.request.url);
	const apiUrl = `https://henryrollins-api.terminal-share.workers.dev${url.pathname}${url.search}`;

	const proxyRequest = new Request(apiUrl, {
		method: context.request.method,
		headers: context.request.headers,
		body: ["GET", "HEAD"].includes(context.request.method)
			? null
			: context.request.body,
	});

	return fetch(proxyRequest);
}
