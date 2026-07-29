from __future__ import annotations

import json
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def get_now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_text(value) -> str:
    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_hotel_key(value: str) -> str:
    return normalize_text(value)


def normalize_phone(value) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def get_domain(url: str) -> str:
    text = str(url or "").strip().lower()

    if not text:
        return ""

    if not text.startswith(("http://", "https://")):
        text = "https://" + text

    domain = urlparse(text).netloc.lower()

    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def is_empty_value(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def atomic_write_json(path: str | Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        encoding="utf-8",
        dir=path.parent,
        suffix=".tmp",
    ) as temp_file:
        json.dump(data, temp_file, indent=4, ensure_ascii=False, default=str)
        temp_path = Path(temp_file.name)

    temp_path.replace(path)


def backup_file(path: str | Path) -> Path | None:
    path = Path(path)

    if not path.exists():
        return None

    backup_dir = path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{path.stem}_backup_{timestamp}{path.suffix}"
    shutil.copy2(path, backup_path)

    return backup_path


def save_hotels_to_cache(hotels, filename="hotel_cache.json", make_backup: bool = False):
    filename = Path(filename)

    if make_backup:
        backup_file(filename)

    atomic_write_json(filename, hotels)


def load_hotels_from_cache(filename="hotel_cache.json"):
    filename = Path(filename)

    if not filename.exists():
        save_hotels_to_cache([], filename)
        return []

    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)

    except json.JSONDecodeError:
        broken_path = filename.with_suffix(".broken.json")
        filename.rename(broken_path)
        save_hotels_to_cache([], filename)
        return []

    if not isinstance(data, list):
        return []

    return data


def is_likely_mirror_site(url: str) -> bool:
    domain = get_domain(url)

    if not domain:
        return False

    strong_mirror_terms = [
        "hotel-rn",
        "hotelmix",
        "booked",
        "all-hotels",
        "hotels-in",
        "hotels-of",
        "tophotel",
        "ihotel",
    ]

    if any(term in domain for term in strong_mirror_terms):
        return True

    main_domain = domain.split(".")[0]
    words = main_domain.split("-")
    generic_hotel_words = {"hotel", "hotels", "stay", "rooms"}

    if len(words) >= 2 and any(word in generic_hotel_words for word in words):
        return True

    return False


def hotel_record_score(hotel: dict) -> int:
    score = 0

    useful_fields = [
        "hotel_name",
        "location",
        "area",
        "website",
        "phone",
        "email",
        "rating",
        "review_summary",
        "chain_or_independent",
        "hotel_type",
    ]

    for field in useful_fields:
        if hotel.get(field):
            score += 10

    if hotel.get("room_types"):
        score += 10

    if hotel.get("room_pricing"):
        score += 10

    if hotel.get("facilities"):
        score += 10

    if hotel.get("manager_contacts"):
        score += 20

    if hotel.get("contact_leads"):
        score += 8

    source_url = str(hotel.get("source_url") or hotel.get("website") or "")

    if is_likely_mirror_site(source_url):
        score -= 30

    return score


def get_hotel_identity_parts(hotel: dict) -> dict:
    website = hotel.get("website") or hotel.get("source_url") or ""

    return {
        "name": normalize_text(hotel.get("hotel_name")),
        "domain": get_domain(str(website)),
        "location": normalize_text(hotel.get("location") or hotel.get("area")),
        "phone": normalize_phone(hotel.get("phone")),
    }


def location_words_overlap(a: str, b: str) -> bool:
    a_words = {word for word in normalize_text(a).split() if len(word) > 2}
    b_words = {word for word in normalize_text(b).split() if len(word) > 2}

    if not a_words or not b_words:
        return False

    return bool(a_words & b_words)


def are_same_hotel(left: dict, right: dict) -> bool:
    left_id = get_hotel_identity_parts(left)
    right_id = get_hotel_identity_parts(right)

    if not left_id["name"] or not right_id["name"]:
        return False

    same_name = left_id["name"] == right_id["name"]

    if same_name and left_id["domain"] and left_id["domain"] == right_id["domain"]:
        return True

    if same_name and left_id["phone"] and left_id["phone"] == right_id["phone"]:
        return True

    if same_name and location_words_overlap(left_id["location"], right_id["location"]):
        return True

    return False


def merge_lists(left_value, right_value):
    merged = []
    seen = set()

    for value in (left_value or []) + (right_value or []):
        key = normalize_text(value)

        if not key or key in seen:
            continue

        seen.add(key)
        merged.append(value)

    return merged


def merge_contacts(left_value, right_value):
    merged = []
    seen = set()

    for contact in (left_value or []) + (right_value or []):
        if not isinstance(contact, dict):
            continue

        key = (
            normalize_text(contact.get("name")),
            normalize_text(contact.get("role") or contact.get("matched_role")),
            normalize_text(
                contact.get("linkedin_url")
                or contact.get("profile_url")
                or contact.get("source_url")
                or contact.get("url")
            ),
        )

        if key in seen:
            continue

        seen.add(key)
        merged.append(contact)

    return merged


def merge_hotel_records(existing: dict, incoming: dict) -> dict:
    existing = dict(existing or {})
    incoming = dict(incoming or {})
    manual_overrides = set(existing.get("manual_overrides") or [])
    merged = dict(existing)

    for key, value in incoming.items():
        if key in manual_overrides:
            continue

        if key in ["room_types", "room_pricing", "facilities"]:
            merged[key] = merge_lists(existing.get(key), value)
            continue

        if key in ["manager_contacts", "contact_leads", "contact_debug_candidates"]:
            merged[key] = merge_contacts(existing.get(key), value)
            continue

        if is_empty_value(existing.get(key)) and not is_empty_value(value):
            merged[key] = value

    for field in ["review_status", "notes", "manual_overrides", "first_discovered", "search_name"]:
        if field in existing:
            merged[field] = existing[field]

    merged["last_updated"] = get_now_stamp()
    return merged


def dedupe_hotels(hotels: list[dict]) -> list[dict]:
    unique_hotels = []

    for hotel in hotels:
        if not isinstance(hotel, dict):
            continue

        if not hotel.get("hotel_name"):
            continue

        matched_index = None

        for index, existing_hotel in enumerate(unique_hotels):
            if are_same_hotel(existing_hotel, hotel):
                matched_index = index
                break

        if matched_index is None:
            unique_hotels.append(hotel)
            continue

        existing_hotel = unique_hotels[matched_index]
        merged = merge_hotel_records(existing_hotel, hotel)

        if hotel_record_score(hotel) > hotel_record_score(existing_hotel):
            merged = merge_hotel_records(hotel, existing_hotel)

        unique_hotels[matched_index] = merged

    return unique_hotels
