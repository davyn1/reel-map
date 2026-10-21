from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import CORS_ORIGINS, FRONTEND_DIST
from app.db import init_db
from app.routers import auth, places, reels


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def mount_frontend(app: FastAPI, dist: Path) -> bool:
    """Serve the built map at / when it exists. Mounted last, so /api/* routes win."""
    if not (dist / "index.html").is_file():
        return False
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return True


app = FastAPI(title="food-map", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)  # the map bundle is ~1.2 MB raw, ~340 KB gzipped
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(places.router)
app.include_router(reels.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


mount_frontend(app, FRONTEND_DIST)
