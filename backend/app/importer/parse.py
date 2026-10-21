"""Load Muse export files (JSON arrays of reel objects).

Empty strings and nulls both mean "unknown". Missing or extra keys are tolerated.
A file that isn't valid JSON raises ExportParseError with the exact location;
we never try to repair it.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.config import DATA_DIR

FIELDS = ("venue", "address", "city", "post_url", "posted_by", "dish", "confidence", "note")


class ExportParseError(Exception):
    pass


@dataclass
class RawReel:
    source_file: str
    index: int
    post_url: str | None = None
    posted_by: str | None = None
    venue: str | None = None
    address: str | None = None
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    dish: str | None = None
    confidence: str | None = None
    note: str | None = None


@dataclass
class ParsedFile:
    path: Path
    reels: list[RawReel] = field(default_factory=list)
    skipped: list[tuple[int, str]] = field(default_factory=list)  # (index, reason)


def clean_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def clean_float(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


# instagram.com/reel/ID, /reels/ID, /p/ID, /tv/ID, optionally under a username, with any query string.
_IG_POST = re.compile(r"^https?://(?:www\.)?instagram\.com/(?:[\w.]+/)?(?:reels?|p|tv)/([\w-]+)", re.IGNORECASE)


def normalize_post_url(url: str) -> str:
    """One canonical form per reel, since post_url is the dedup key: https://www.instagram.com/reel/<id>/.

    "…/p/ABC/?igsh=x" and "…/reel/ABC" are the same reel; without this a re-export that formats
    links differently would import every reel twice. Non-Instagram URLs are left as they are.
    """
    m = _IG_POST.match(url.strip())
    return f"https://www.instagram.com/reel/{m.group(1)}/" if m else url.strip()


def find_export_files(path: str | Path | None = None) -> list[Path]:
    if path is not None:
        return [Path(path)]
    return sorted(DATA_DIR.glob("reels*.json"))


def load_file(path: Path) -> ParsedFile:
    text = path.read_text(encoding="utf-8-sig")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ExportParseError(f"{path}: line {e.lineno}, column {e.colno}: {e.msg}") from e
    # Also accept {"reels": [...]} (how some tools wrap a list); anything else is refused, not guessed at.
    if isinstance(data, dict) and isinstance(data.get("reels"), list):
        data = data["reels"]
    if not isinstance(data, list):
        raise ExportParseError(f"{path}: expected a JSON array (or {{\"reels\": [...]}}) at the top level, got {type(data).__name__}")

    parsed = ParsedFile(path=path)
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            parsed.skipped.append((i, f"item is a {type(item).__name__}, not an object"))
            continue
        reel = RawReel(source_file=path.name, index=i)
        for key in FIELDS:
            setattr(reel, key, clean_str(item.get(key)))
        reel.lat = clean_float(item.get("lat"))
        reel.lng = clean_float(item.get("lng"))
        if reel.confidence:
            reel.confidence = reel.confidence.lower()
        if not reel.post_url:
            parsed.skipped.append((i, f"no post_url (venue: {reel.venue or '?'})"))
            continue
        reel.post_url = normalize_post_url(reel.post_url)
        parsed.reels.append(reel)
    return parsed
