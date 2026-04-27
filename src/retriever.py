import json
from pathlib import Path

_GUIDES_PATH = Path(__file__).parent.parent / "data" / "genre_guides.json"
_cache: dict | None = None


def retrieve_genre_guide(genre: str) -> str | None:
    """Return the genre description for the given genre string, or None if not found.

    Results are cached after the first load so the file is only read once per process.
    """
    global _cache
    if _cache is None:
        with _GUIDES_PATH.open(encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache.get(genre.lower())
