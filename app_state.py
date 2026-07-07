from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EXPORTS_DIR = BASE_DIR / "exports"

APP_SETTINGS_FILE = DATA_DIR / "app_settings.json"
ROLE_PROFILES_FILE = DATA_DIR / "role_profiles.json"
DEFAULT_CACHE_FILE = DATA_DIR / "hotel_cache.json"
DEFAULT_PURGE_FILE = DATA_DIR / "purge_list.json"


DEFAULT_SEARCH_SETTINGS = {
    "location": "Delhi",
    "area": "Aerocity",
    "hotel_type": "business hotels",
    "extra_info": "Prefer hotels with banquet halls or conference facilities.",
    "nearby_area_terms": [
        "Mahipalpur",
        "Rangpuri",
        "IGI",
        "airport",
        "hospitality district",
    ],
    "excluded_location_terms": [
        "Noida",
        "Gurgaon",
        "Gurugram",
        "Ghaziabad",
        "Faridabad",
    ],
    "max_search_results": 10,
    "max_pages_to_try": 8,
    "target_hotels": 3,
    "max_contact_search_results": 4,
    "max_contact_pages_per_hotel": 2,
}


DEFAULT_APP_SETTINGS = {
    "active_cache_file": str(DEFAULT_CACHE_FILE),
    "active_purge_file": str(DEFAULT_PURGE_FILE),
    "active_role_profile": "default",
    "last_run_type": "contacts_only",
    "save_after_each_hotel": True,
    "search_settings": DEFAULT_SEARCH_SETTINGS,
}


DEFAULT_ROLE_PROFILES = {
    "default": {
        "target_roles": [
            "general manager",
        ],
        "secondary_roles": [
            "hotel manager",
            "cluster general manager",
            "area general manager",
            "operations manager",
            "front office manager",
            "director of sales",
        ],
        "ignored_roles": [
            "chef",
            "pastry chef",
            "guest service executive",
            "human resources",
            "director of human resources",
            "sales executive",
        ],
    }
}


def get_now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_app_folders() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


def read_json_file(path: str | Path, default_value: Any) -> Any:
    path = Path(path)

    if not path.exists():
        write_json_file(path, default_value)
        return deepcopy(default_value)

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    except json.JSONDecodeError:
        backup_path = path.with_suffix(".broken.json")
        path.rename(backup_path)

        write_json_file(path, default_value)
        return deepcopy(default_value)


def write_json_file(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def merge_missing_defaults(data: dict, defaults: dict) -> dict:
    if not isinstance(data, dict):
        data = {}

    merged = deepcopy(defaults)

    for key, value in data.items():
        if (
            isinstance(value, dict)
            and isinstance(merged.get(key), dict)
        ):
            merged[key] = merge_missing_defaults(value, merged[key])
        else:
            merged[key] = value

    return merged


def load_app_settings() -> dict:
    ensure_app_folders()

    data = read_json_file(APP_SETTINGS_FILE, DEFAULT_APP_SETTINGS)
    settings = merge_missing_defaults(data, DEFAULT_APP_SETTINGS)

    save_app_settings(settings)

    return settings


def save_app_settings(settings: dict) -> None:
    ensure_app_folders()

    settings = merge_missing_defaults(settings, DEFAULT_APP_SETTINGS)
    settings["last_saved_at"] = get_now_stamp()

    write_json_file(APP_SETTINGS_FILE, settings)


def load_role_profiles() -> dict:
    ensure_app_folders()

    data = read_json_file(ROLE_PROFILES_FILE, DEFAULT_ROLE_PROFILES)

    if not isinstance(data, dict):
        data = deepcopy(DEFAULT_ROLE_PROFILES)

    if "default" not in data:
        data["default"] = deepcopy(DEFAULT_ROLE_PROFILES["default"])

    save_role_profiles(data)

    return data


def save_role_profiles(role_profiles: dict) -> None:
    ensure_app_folders()

    if not isinstance(role_profiles, dict):
        role_profiles = deepcopy(DEFAULT_ROLE_PROFILES)

    if "default" not in role_profiles:
        role_profiles["default"] = deepcopy(DEFAULT_ROLE_PROFILES["default"])

    write_json_file(ROLE_PROFILES_FILE, role_profiles)


def get_active_role_profile(
    settings: dict | None = None,
    role_profiles: dict | None = None,
) -> dict:
    if settings is None:
        settings = load_app_settings()

    if role_profiles is None:
        role_profiles = load_role_profiles()

    profile_name = settings.get("active_role_profile", "default")

    return role_profiles.get(profile_name) or role_profiles["default"]


def get_active_target_roles(
    settings: dict | None = None,
    role_profiles: dict | None = None,
) -> list[str]:
    profile = get_active_role_profile(settings, role_profiles)

    roles = profile.get("target_roles") or []

    return clean_string_list(roles)


def get_active_secondary_roles(
    settings: dict | None = None,
    role_profiles: dict | None = None,
) -> list[str]:
    profile = get_active_role_profile(settings, role_profiles)

    roles = profile.get("secondary_roles") or []

    return clean_string_list(roles)


def get_active_ignored_roles(
    settings: dict | None = None,
    role_profiles: dict | None = None,
) -> list[str]:
    profile = get_active_role_profile(settings, role_profiles)

    roles = profile.get("ignored_roles") or []

    return clean_string_list(roles)


def clean_string_list(values: list[Any]) -> list[str]:
    clean_values = []
    seen = set()

    for value in values:
        text = str(value or "").strip()

        if not text:
            continue

        key = text.lower()

        if key in seen:
            continue

        seen.add(key)
        clean_values.append(text)

    return clean_values


def save_role_profile(
    profile_name: str,
    target_roles: list[str],
    secondary_roles: list[str] | None = None,
    ignored_roles: list[str] | None = None,
) -> dict:
    role_profiles = load_role_profiles()

    profile_name = str(profile_name or "").strip()

    if not profile_name:
        profile_name = "default"

    role_profiles[profile_name] = {
        "target_roles": clean_string_list(target_roles),
        "secondary_roles": clean_string_list(secondary_roles or []),
        "ignored_roles": clean_string_list(ignored_roles or []),
    }

    save_role_profiles(role_profiles)

    return role_profiles[profile_name]


def delete_role_profile(profile_name: str) -> bool:
    profile_name = str(profile_name or "").strip()

    if not profile_name or profile_name == "default":
        return False

    role_profiles = load_role_profiles()

    if profile_name not in role_profiles:
        return False

    del role_profiles[profile_name]
    save_role_profiles(role_profiles)

    settings = load_app_settings()

    if settings.get("active_role_profile") == profile_name:
        settings["active_role_profile"] = "default"
        save_app_settings(settings)

    return True


def set_active_role_profile(profile_name: str) -> None:
    profile_name = str(profile_name or "").strip()

    if not profile_name:
        profile_name = "default"

    role_profiles = load_role_profiles()

    if profile_name not in role_profiles:
        role_profiles[profile_name] = deepcopy(DEFAULT_ROLE_PROFILES["default"])
        save_role_profiles(role_profiles)

    settings = load_app_settings()
    settings["active_role_profile"] = profile_name
    save_app_settings(settings)


def get_active_cache_path(settings: dict | None = None) -> Path:
    if settings is None:
        settings = load_app_settings()

    return Path(settings.get("active_cache_file") or DEFAULT_CACHE_FILE)


def set_active_cache_path(path: str | Path) -> None:
    settings = load_app_settings()
    settings["active_cache_file"] = str(Path(path))
    save_app_settings(settings)


def get_active_purge_path(settings: dict | None = None) -> Path:
    if settings is None:
        settings = load_app_settings()

    return Path(settings.get("active_purge_file") or DEFAULT_PURGE_FILE)


def set_active_purge_path(path: str | Path) -> None:
    settings = load_app_settings()
    settings["active_purge_file"] = str(Path(path))
    save_app_settings(settings)


def get_search_settings(settings: dict | None = None) -> dict:
    if settings is None:
        settings = load_app_settings()

    search_settings = settings.get("search_settings") or {}

    return merge_missing_defaults(search_settings, DEFAULT_SEARCH_SETTINGS)


def save_search_settings(search_settings: dict) -> None:
    settings = load_app_settings()
    settings["search_settings"] = merge_missing_defaults(
        search_settings,
        DEFAULT_SEARCH_SETTINGS,
    )

    save_app_settings(settings)


def reset_app_settings() -> dict:
    settings = deepcopy(DEFAULT_APP_SETTINGS)
    save_app_settings(settings)

    return settings


def reset_role_profiles() -> dict:
    role_profiles = deepcopy(DEFAULT_ROLE_PROFILES)
    save_role_profiles(role_profiles)

    return role_profiles