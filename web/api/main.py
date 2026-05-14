"""
Henry Rollins Listens To — FastAPI Backend

Serves scraped radio show data + enriched metadata to the Svelte 5 frontend.
"""

import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import episodes, artists, albums, stats, recommends, search, tracks

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "db" / "henryrollins.db"
ENRICHMENT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "enrichment.db"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    # Store paths in app.state for routers
    app.state.db_path = str(DB_PATH)
    app.state.enrichment_path = str(ENRICHMENT_DB_PATH)
    yield


app = FastAPI(
    title="Henry Rollins Listens To",
    description="API for visualizing 496 episodes of Henry Rollins' KCRW radio show",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow the Vite dev server to access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(episodes.router, prefix="/api/episodes", tags=["Episodes"])
app.include_router(artists.router, prefix="/api/artists", tags=["Artists"])
app.include_router(albums.router, prefix="/api/albums", tags=["Albums"])
app.include_router(stats.router, prefix="/api/stats", tags=["Stats"])
app.include_router(recommends.router, prefix="/api/recommends", tags=["Recommends"])
app.include_router(search.router, prefix="/api/search", tags=["Search"])
app.include_router(tracks.router, prefix="/api/tracks", tags=["Tracks"])

# Set default state for both server mode and test mode
app.state.db_path = str(DB_PATH)
app.state.enrichment_path = str(ENRICHMENT_DB_PATH)


@app.get("/api/health")
async def health():
    return {"status": "ok", "episodes": 496, "tracks": 16914, "artists": 2678}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
