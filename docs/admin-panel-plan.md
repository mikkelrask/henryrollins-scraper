# Admin Panel v2 — Auth, Inline Editing, Track Browser, Correction History

## Goal

The old admin had merge/edit buttons scattered across public pages with zero auth.
We need to (1) gate all admin functionality behind auth, (2) bring the most-used
workflow (album detail → fix track titles to match MusicBrainz) into a 0-hop
inline experience, and (3) add proactive tools for bulk cleaning.

## Auth Layer

- `ADMIN_API_KEY` env var — optional (no auth) in dev, required in prod
- `GET /api/admin/check` — 200 if `X-Admin-Key` matches, 401 otherwise
- Frontend `useAuth()` store — password prompt on first admin access, stores key in
  sessionStorage, attaches `X-Admin-Key` header to all `/api/admin/*` calls
- All admin buttons (merge ✂️ on artist/album pages, edit ✏️ on episode page,
  admin page itself) gated behind `{#if authed}`
- CF Access protects `/api/admin/*` at the edge as a secondary layer

## Phase 1 ✅ — Auth Implementation

**Backend (`web/api/routers/admin.py`, `web/api/main.py`):**
- `ADMIN_API_KEY` loaded from env in lifespan
- `GET /api/admin/check` endpoint
- `require_admin()` dependency for all other admin endpoints
- CORS config allows admin header in dev

**Frontend (`web/app/src/lib/useAuth.svelte.js`):**
- Svelte 5 runes store: `authed`, `key`
- `prompt()` on first access, stores in sessionStorage
- `authFetch(url, opts)` — wraps fetch with `X-Admin-Key` header
- Exported `authed` state — components use `{#if authed}` to show/hide buttons

**Gated components:**
- `ArtistDetail.svelte` — Merge button only if authed
- `AlbumDetail.svelte` — Merge button + inline edit ✏️ only if authed
- `EpisodeDetail.svelte` — Edit/Add Track buttons only if authed
- `Admin.svelte` — Password gate before rendering tabs

## Phase 2 ✅ — Album Detail Inline Editing (Centerpiece)

**Problem:** Album page → see wrong title → find episode → click through → edit → save → back. 3 hops.

**After:** Album page → ✏️ on track → pick MB suggestion → save. 0 hops.

**Implementation (`web/app/src/routes/AlbumDetail.svelte`, `web/app/src/lib/components/TrackEditor.svelte`):**

- ✏️ button on each track accordion row (only renders if authed)
- Click opens TrackEditor modal inline on the album page
- TrackEditor gets new optional prop `suggestions: string[]` — the "Not played
  from this album" MB title list
- Suggestions rendered as clickable chips below the title input; clicking one
  fills the title field
- Pass the latest played episode's broadcast ID as `episodeId` for the correction
  anchor
- On save, re-fetch album data so corrected rows + updated "Not played" list
  reflect immediately

## Phase 3 (Next) — Track Browser

Instead of a new admin tab for Phase 3, I'm building a **dedicated admin frontend
page** — a sidecar Svelte app served at `/admin` (or a separate dev server).
This keeps the admin UX unconstrained by the public app's layout and prevents
admin code from shipping to public users.

## Phase 4 (Next) — Correction History

- `GET /api/admin/corrections` — list all from enrichment DB with timestamps
- `POST /api/admin/corrections/{id}/revert` — remove a correction, re-apply
  remaining ones for that track to roll back cleanly
- Tab in the standalone admin frontend: table of all corrections with revert
  buttons, filterable by episode/artist/album
