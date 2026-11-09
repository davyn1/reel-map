import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app import alerts, demo
from app.config import CORS_ORIGINS, FRONTEND_DIST
from app.db import SessionLocal, init_db
from app.routers import auth, imports, places, reels


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if demo.DEMO:
        demo.reset()
    # The demo rebuilds its sample data now and then; the real app watches for Muse going quiet.
    task = asyncio.create_task(demo.reset_periodically() if demo.DEMO else _check_quiet_periodically())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def _check_quiet() -> None:
    with SessionLocal() as session:
        alerts.check_quiet(session, wait=True)


async def _check_quiet_periodically() -> None:
    """Has Muse gone quiet? Checked on start (the daily wake-up job starts the server) and every 12 h while up."""
    while True:
        try:
            await asyncio.to_thread(_check_quiet)
        except Exception as e:  # noqa: BLE001
            logging.getLogger(__name__).warning("quiet check failed: %s", e)
        await asyncio.sleep(12 * 3600)


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
app.include_router(imports.router)
app.include_router(places.router)
app.include_router(reels.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/demo")
def demo_info() -> dict[str, str]:
    """Public: the demo login for the login screen. 404 unless this server is the demo."""
    if not demo.DEMO:
        raise HTTPException(404, "not the demo")
    return {"username": demo.DEMO_USERNAME, "password": demo.DEMO_PASSWORD, "source_url": demo.SOURCE_URL}


mount_frontend(app, FRONTEND_DIST)
