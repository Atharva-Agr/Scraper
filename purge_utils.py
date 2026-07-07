from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_PURGE_LIST = {
    "blocked_urls": [],
    "blocked_domains": [],
    "soft_blocked_urls": [],
    "soft_blocked_domains": [],
    "blocked_url_contains": [],
    "soft_blocked_url_contains": [],
    "blocked_contact_names": [],
    "blocked_hotel_names": [],
    "blocked_patterns": [],
    "soft_blocked_patterns": [],
}


def get_now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def clean_url(url: Any) -> str:
    return str(url or "").strip()


def get_domain(url: Any) -> str:
    text = clean_url(url).lower()

    if not text:
        return ""

    if not text.startswith(("http://", "https://")):
        text = "https://" + text

    parsed = urlparse(text)
    domain = parsed.netloc.lower()

    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def normalize_url(url: Any) -> str:
    text = clean_url(url).lower()

    if not text:
        return ""

    return text.rstrip("/")


def get_entry_value(entry: Any, key: str) -> str:
    if isinstance(entry, dict):
        return str(entry.get(key) or "").strip()

    return str(entry or "").strip()


def make_entry(value: str, reason: str = "") -> dict:
    return {
        "value": value,
        "reason": reason,
        "created_at": get_now_stamp(),
    }


def ensure_purge_shape(purge_list: dict | None) -> dict:
    if not isinstance(purge_list, dict):
        purge_list = {}

    clean = {}

    for key, default_value in DEFAULT_PURGE_LIST.items():
        value = purge_list.get(key)

        if isinstance(value, list):
            clean[key] = value
        else:
            clean[key] = list(default_value)

    return clean


def load_purge_list(path: str | Path = "data/purge_list.json") -> dict:
    path = Path(path)

    if not path.exists():
        purge_list = ensure_purge_shape({})
        save_purge_list(purge_list, path)
        return purge_list

    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)

    except json.JSONDecodeError:
        backup_path = path.with_suffix(".broken.json")
        path.rename(backup_path)

        purge_list = ensure_purge_shape({})
        save_purge_list(purge_list, path)
        return purge_list

    return ensure_purge_shape(data)


def save_purge_list(
    purge_list: dict,
    path: str | Path = "data/purge_list.json",
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    clean = ensure_purge_shape(purge_list)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(clean, file, indent=4, ensure_ascii=False)


def add_unique_entry(
    purge_list: dict,
    section: str,
    value: str,
    reason: str = "",
) -> dict:
    purge_list = ensure_purge_shape(purge_list)

    value = str(value or "").strip()

    if not value:
        return purge_list

    existing_values = {
        get_entry_value(entry, "value").lower()
        for entry in purge_list[section]
    }

    if value.lower() not in existing_values:
        purge_list[section].append(make_entry(value, reason))

    return purge_list


def add_blocked_url(purge_list: dict, url: str, reason: str = "") -> dict:
    return add_unique_entry(purge_list, "blocked_urls", normalize_url(url), reason)


def add_soft_blocked_url(purge_list: dict, url: str, reason: str = "") -> dict:
    return add_unique_entry(purge_list, "soft_blocked_urls", normalize_url(url), reason)


def add_blocked_domain(purge_list: dict, url_or_domain: str, reason: str = "") -> dict:
    domain = get_domain(url_or_domain) or str(url_or_domain or "").strip().lower()
    return add_unique_entry(purge_list, "blocked_domains", domain, reason)


def add_soft_blocked_domain(
    purge_list: dict,
    url_or_domain: str,
    reason: str = "",
) -> dict:
    domain = get_domain(url_or_domain) or str(url_or_domain or "").strip().lower()
    return add_unique_entry(purge_list, "soft_blocked_domains", domain, reason)


def add_blocked_url_contains(purge_list: dict, pattern: str, reason: str = "") -> dict:
    return add_unique_entry(purge_list, "blocked_url_contains", pattern.lower(), reason)


def add_soft_blocked_url_contains(
    purge_list: dict,
    pattern: str,
    reason: str = "",
) -> dict:
    return add_unique_entry(
        purge_list,
        "soft_blocked_url_contains",
        pattern.lower(),
        reason,
    )


def add_blocked_contact_name(purge_list: dict, name: str, reason: str = "") -> dict:
    return add_unique_entry(
        purge_list,
        "blocked_contact_names",
        normalize_text(name),
        reason,
    )


def add_blocked_hotel_name(purge_list: dict, name: str, reason: str = "") -> dict:
    return add_unique_entry(
        purge_list,
        "blocked_hotel_names",
        normalize_text(name),
        reason,
    )


def add_blocked_pattern(purge_list: dict, pattern: str, reason: str = "") -> dict:
    return add_unique_entry(
        purge_list,
        "blocked_patterns",
        normalize_text(pattern),
        reason,
    )


def add_soft_blocked_pattern(purge_list: dict, pattern: str, reason: str = "") -> dict:
    return add_unique_entry(
        purge_list,
        "soft_blocked_patterns",
        normalize_text(pattern),
        reason,
    )


def remove_entry(purge_list: dict, section: str, value: str) -> dict:
    purge_list = ensure_purge_shape(purge_list)

    if section not in purge_list:
        return purge_list

    clean_value = str(value or "").strip().lower()

    purge_list[section] = [
        entry
        for entry in purge_list[section]
        if get_entry_value(entry, "value").lower() != clean_value
    ]

    return purge_list


def domain_matches(domain: str, blocked_domain: str) -> bool:
    domain = str(domain or "").lower()
    blocked_domain = str(blocked_domain or "").lower()

    if not domain or not blocked_domain:
        return False

    return domain == blocked_domain or domain.endswith("." + blocked_domain)


def text_contains_pattern(text: str, pattern: str) -> bool:
    text = normalize_text(text)
    pattern = normalize_text(pattern)

    if not text or not pattern:
        return False

    return pattern in text


def get_purge_decision_for_url(
    url: str,
    purge_list: dict | None = None,
) -> dict:
    purge_list = ensure_purge_shape(purge_list)

    normalized_url = normalize_url(url)
    domain = get_domain(url)

    reasons = []
    penalty = 0

    for entry in purge_list["blocked_urls"]:
        blocked_url = normalize_url(get_entry_value(entry, "value"))

        if normalized_url == blocked_url:
            reasons.append(f"Hard purge URL match: {blocked_url}")
            return {
                "blocked": True,
                "penalty": 0,
                "reasons": reasons,
            }

    for entry in purge_list["blocked_domains"]:
        blocked_domain = get_entry_value(entry, "value").lower()

        if domain_matches(domain, blocked_domain):
            reasons.append(f"Hard purge domain match: {blocked_domain}")
            return {
                "blocked": True,
                "penalty": 0,
                "reasons": reasons,
            }

    for entry in purge_list["blocked_url_contains"]:
        pattern = get_entry_value(entry, "value").lower()

        if pattern and pattern in normalized_url:
            reasons.append(f"Hard purge URL pattern match: {pattern}")
            return {
                "blocked": True,
                "penalty": 0,
                "reasons": reasons,
            }

    for entry in purge_list["soft_blocked_urls"]:
        soft_url = normalize_url(get_entry_value(entry, "value"))

        if normalized_url == soft_url:
            penalty -= 40
            reasons.append(f"Soft purge URL penalty: {soft_url}")

    for entry in purge_list["soft_blocked_domains"]:
        soft_domain = get_entry_value(entry, "value").lower()

        if domain_matches(domain, soft_domain):
            penalty -= 30
            reasons.append(f"Soft purge domain penalty: {soft_domain}")

    for entry in purge_list["soft_blocked_url_contains"]:
        pattern = get_entry_value(entry, "value").lower()

        if pattern and pattern in normalized_url:
            penalty -= 25
            reasons.append(f"Soft purge URL pattern penalty: {pattern}")

    return {
        "blocked": False,
        "penalty": penalty,
        "reasons": reasons,
    }


def get_purge_decision_for_hotel(
    hotel: dict,
    purge_list: dict | None = None,
) -> dict:
    purge_list = ensure_purge_shape(purge_list)

    hotel_name = normalize_text(hotel.get("hotel_name"))
    url = hotel.get("source_url") or hotel.get("website") or ""

    url_decision = get_purge_decision_for_url(url, purge_list)

    if url_decision["blocked"]:
        return url_decision

    reasons = list(url_decision["reasons"])
    penalty = url_decision["penalty"]

    for entry in purge_list["blocked_hotel_names"]:
        blocked_name = normalize_text(get_entry_value(entry, "value"))

        if blocked_name and blocked_name == hotel_name:
            reasons.append(f"Hard purge hotel name match: {blocked_name}")
            return {
                "blocked": True,
                "penalty": 0,
                "reasons": reasons,
            }

    return {
        "blocked": False,
        "penalty": penalty,
        "reasons": reasons,
    }


def get_purge_decision_for_candidate(
    candidate: dict,
    purge_list: dict | None = None,
) -> dict:
    purge_list = ensure_purge_shape(purge_list)

    url = candidate.get("url") or candidate.get("source_url") or ""
    title = candidate.get("title") or ""
    body = candidate.get("body") or ""
    name = candidate.get("name") or ""
    role = candidate.get("role") or candidate.get("matched_role") or ""

    url_decision = get_purge_decision_for_url(url, purge_list)

    if url_decision["blocked"]:
        return url_decision

    text = normalize_text(f"{url} {title} {body} {name} {role}")

    reasons = list(url_decision["reasons"])
    penalty = url_decision["penalty"]

    for entry in purge_list["blocked_contact_names"]:
        blocked_name = normalize_text(get_entry_value(entry, "value"))

        if blocked_name and blocked_name in text:
            reasons.append(f"Hard purge contact name match: {blocked_name}")
            return {
                "blocked": True,
                "penalty": 0,
                "reasons": reasons,
            }

    for entry in purge_list["blocked_patterns"]:
        pattern = normalize_text(get_entry_value(entry, "value"))

        if pattern and pattern in text:
            reasons.append(f"Hard purge text pattern match: {pattern}")
            return {
                "blocked": True,
                "penalty": 0,
                "reasons": reasons,
            }

    for entry in purge_list["soft_blocked_patterns"]:
        pattern = normalize_text(get_entry_value(entry, "value"))

        if pattern and pattern in text:
            penalty -= 20
            reasons.append(f"Soft purge text pattern penalty: {pattern}")

    return {
        "blocked": False,
        "penalty": penalty,
        "reasons": reasons,
    }


def apply_purge_to_candidate(
    candidate: dict,
    purge_list: dict | None = None,
) -> dict:
    decision = get_purge_decision_for_candidate(candidate, purge_list)

    candidate = dict(candidate)

    candidate["purge_blocked"] = decision["blocked"]
    candidate["purge_penalty"] = decision["penalty"]
    candidate["purge_reasons"] = decision["reasons"]

    if decision["blocked"]:
        candidate["score"] = 0
        candidate["confidence"] = "reject"
        candidate["action"] = "reject"

        reasons = candidate.get("reasons") or []
        reasons.extend(decision["reasons"])
        candidate["reasons"] = reasons

    else:
        score = int(candidate.get("score") or 0)
        candidate["score"] = score + decision["penalty"]

        reasons = candidate.get("reasons") or []
        reasons.extend(decision["reasons"])
        candidate["reasons"] = reasons

    return candidate


def filter_purged_urls(
    urls: list[str],
    purge_list: dict | None = None,
) -> list[str]:
    clean_urls = []

    for url in urls:
        decision = get_purge_decision_for_url(url, purge_list)

        if decision["blocked"]:
            continue

        clean_urls.append(url)

    return clean_urls


def filter_purged_hotels(
    hotels: list[dict],
    purge_list: dict | None = None,
) -> list[dict]:
    clean_hotels = []

    for hotel in hotels:
        decision = get_purge_decision_for_hotel(hotel, purge_list)

        if decision["blocked"]:
            continue

        clean_hotels.append(hotel)

    return clean_hotels