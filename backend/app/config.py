import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

load_dotenv(PROJECT_DIR / ".env")

# Every path can be overridden by an environment variable, so the hosted server can keep its
# data on a persistent volume (e.g. FOOD_MAP_DATA_DIR=/data) while local runs use the repo.
DATA_DIR = Path(os.getenv("FOOD_MAP_EXPORTS_DIR", PROJECT_DIR / "data"))  # Muse exports
PERSONAL_DIR = Path(os.getenv("FOOD_MAP_PERSONAL_DIR", PROJECT_DIR / "personal"))  # my-log.json
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'food_map.db'}")

# The built map (npm run build). Served by the API when present, so one server runs everything.
FRONTEND_DIST = Path(os.getenv("FOOD_MAP_FRONTEND_DIST", PROJECT_DIR / "frontend" / "dist"))

# Browser origins allowed to call the API from another port (the Vite dev server).
CORS_ORIGINS = [o.strip() for o in os.getenv("FOOD_MAP_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
