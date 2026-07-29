from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


DATA_DIR = Path("data")
SEARCH_CACHE_FILE = DATA_DIR / "search_cache.json"
SCRAPE_CACHE_FILE = DATA_DIR / "scrape_cache.json"


def get_now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def make_cache_key(*parts: Any) -> str:
    raw = "||".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_json_cache(path: str | Path) -> dict:
    path = Path(path)

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        save_json_cache(path, {})
        return {}

    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)

    except json.JSONDecodeError:
        broken_path = path.with_suffix(".broken.json")
        path.rename(broken_path)

        save_json_cache(path, {})
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def save_json_cache(path: str | Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_suffix(".tmp")

    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

    temp_path.replace(path)


def is_fresh(entry: dict, max_age_hours: int) -> bool:
    searched_at = parse_time(entry.get("saved_at"))

    if not searched_at:
        return False

    return datetime.now() - searched_at <= timedelta(hours=max_age_hours)


# -----------------------------
# Search cache
# -----------------------------

def get_cached_search_results(
    query: str,
    settings_key: str = "default",
    max_age_hours: int = 24,
) -> list[dict] | None:
    cache = load_json_cache(SEARCH_CACHE_FILE)
    key = make_cache_key(settings_key, query)

    entry = cache.get(key)

    if not isinstance(entry, dict):
        return None

    if not is_fresh(entry, max_age_hours):
        return None

    results = entry.get("results")

    if not isinstance(results, list):
        return None

    return results


def set_cached_search_results(
    query: str,
    results: list[dict],
    settings_key: str = "default",
) -> None:
    cache = load_json_cache(SEARCH_CACHE_FILE)
    key = make_cache_key(settings_key, query)

    cache[key] = {
        "query": query,
        "settings_key": settings_key,
        "saved_at": get_now_iso(),
        "results": results,
    }

    save_json_cache(SEARCH_CACHE_FILE, cache)


# -----------------------------
# Scrape cache
# -----------------------------

def get_cached_scrape_result(
    url: str,
    max_age_hours: int = 168,
) -> dict | None:
    cache = load_json_cache(SCRAPE_CACHE_FILE)
    key = make_cache_key(url)

    entry = cache.get(key)

    if not isinstance(entry, dict):
        return None

    if not is_fresh(entry, max_age_hours):
        return None

    return entry


def set_cached_scrape_result(
    url: str,
    status: str,
    result: Any = None,
    error: str = "",
) -> None:
    cache = load_json_cache(SCRAPE_CACHE_FILE)
    key = make_cache_key(url)

    cache[key] = {
        "url": url,
        "status": status,
        "saved_at": get_now_iso(),
        "result": result,
        "error": error,
    }

    save_json_cache(SCRAPE_CACHE_FILE, cache)