from __future__ import annotations

import csv
import importlib
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel

from app_state import (
    get_active_cache_path,
    get_active_ignored_roles,
    get_active_purge_path,
    get_active_secondary_roles,
    get_active_target_roles,
    get_search_settings,
    load_app_settings,
    load_role_profiles,
)

from cache_utils import (
    dedupe_hotels,
    load_hotels_from_cache,
    save_hotels_to_cache,
)

from purge_utils import (
    get_purge_decision_for_hotel,
    get_purge_decision_for_url,
    load_purge_list,
)


def get_now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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


def parse_csv_text(value: str) -> list[str]:
    return clean_string_list(str(value or "").split(","))



def estimate_hotel_count_from_urls(candidate_urls: list[str], url_utils_module) -> int:
    """
    Estimate the complete-search target from the actual URLs discovered.

    This avoids hardcoded city/area assumptions. The estimate is based on how
    many unique hotel-looking sources the current search found, plus a small
    buffer because some pages will fail validation or scraping.
    """
    scored_urls = []

    for url in candidate_urls:
        try:
            score = url_utils_module.score_url(url)
        except Exception:
            score = 0

        if score >= 25:
            scored_urls.append((url, score))

    useful_count = len(scored_urls)
    high_confidence_count = sum(1 for _, score in scored_urls if score >= 75)

    if useful_count == 0:
        return 15

    buffer = max(5, useful_count // 4)
    confidence_bonus = min(high_confidence_count // 3, 10)

    return min(max(useful_count + buffer + confidence_bonus, 15), 150)


def make_fallback_hotel_from_url(url: str, settings: dict, source_type: str = "unknown") -> dict:
    parsed = urlparse(str(url or ""))
    domain = parsed.netloc.replace("www.", "")

    name_seed = domain.split(".")[0]
    name_seed = name_seed.replace("-", " ").replace("_", " ").strip()
    guessed_name = " ".join(word.capitalize() for word in name_seed.split())

    return ensure_hotel_app_fields(
        {
            "hotel_name": guessed_name or domain or "High Confidence Hotel",
            "location": f"{settings.get('area')}, {settings.get('location')}",
            "area": settings.get("area"),
            "website": url,
            "source_url": url,
            "phone": None,
            "email": None,
            "hotel_type": settings.get("hotel_type"),
            "chain_or_independent": None,
            "rating": None,
            "review_summary": "High-confidence hotel source found, but full scraping failed.",
            "room_types": [],
            "room_pricing": [],
            "facilities": [],
            "review_status": "needs_review",
            "scrape_status": "failed_high_confidence_source",
            "source_type": source_type,
            "search_name": settings.get("search_name"),
            "search_mode": "complete" if settings.get("complete_search") else "partial",
            "estimated_hotel_count": settings.get("estimated_hotel_count"),
        }
    )


def normalize_settings(settings: dict | None = None) -> dict:
    base_settings = get_search_settings()

    if isinstance(settings, dict):
        merged = deepcopy(base_settings)
        merged.update(settings)
        settings = merged
    else:
        settings = base_settings

    settings["nearby_area_terms"] = clean_string_list(
        settings.get("nearby_area_terms") or []
    )
    settings["excluded_location_terms"] = clean_string_list(
        settings.get("excluded_location_terms") or []
    )

    int_fields = [
        "max_search_results",
        "max_pages_to_try",
        "target_hotels",
        "max_contact_search_results",
        "max_contact_pages_per_hotel",
    ]

    for field in int_fields:
        try:
            settings[field] = int(settings.get(field) or base_settings[field])
        except (TypeError, ValueError):
            settings[field] = base_settings[field]

        if settings[field] < 1:
            settings[field] = base_settings[field]

    return settings


def get_backend_modules() -> dict:
    """
    Lazy-import backend modules.

    Important:
    Your current config.py still asks CLI questions on import.
    This file is ready for the desktop app, but the next backend step should
    make config.py import-safe.
    """

    modules = {
        "config": importlib.import_module("config"),
        "discovery": importlib.import_module("discovery"),
        "url_utils": importlib.import_module("url_utils"),
        "hotel_scraper": importlib.import_module("hotel_scraper"),
        "validation": importlib.import_module("validation"),
        "contacts": importlib.import_module("contacts"),
    }

    return modules


def apply_runtime_settings(
    settings: dict | None = None,
    target_roles: list[str] | None = None,
) -> dict:
    settings = normalize_settings(settings)

    app_settings = load_app_settings()
    role_profiles = load_role_profiles()

    if target_roles is None:
        target_roles = settings.get("target_roles") or get_active_target_roles(
            app_settings,
            role_profiles,
        )

    secondary_roles = settings.get("secondary_roles") or get_active_secondary_roles(
        app_settings,
        role_profiles,
    )
    ignored_roles = settings.get("ignored_roles") or get_active_ignored_roles(
        app_settings,
        role_profiles,
    )

    target_roles = clean_string_list(target_roles)
    secondary_roles = clean_string_list(secondary_roles)
    ignored_roles = clean_string_list(ignored_roles)

    if not target_roles:
        target_roles = ["general manager"]

    all_contact_roles = clean_string_list(target_roles + secondary_roles)

    modules = get_backend_modules()

    runtime_values = {
        "location": settings["location"],
        "area": settings["area"],
        "hotel_type": settings["hotel_type"],
        "extra_info": settings["extra_info"],
        "nearby_area_terms": settings["nearby_area_terms"],
        "excluded_location_terms": settings["excluded_location_terms"],
        "max_search_results": settings["max_search_results"],
        "max_pages_to_try": settings["max_pages_to_try"],
        "target_hotels": settings["target_hotels"],
        "max_contact_search_results": settings["max_contact_search_results"],
        "max_contact_pages_per_hotel": settings["max_contact_pages_per_hotel"],
        "contact_roles": target_roles,
        "secondary_contact_roles": secondary_roles,
        "ignored_contact_roles": ignored_roles,
        "all_contact_roles": all_contact_roles,
    }

    for module in modules.values():
        for name, value in runtime_values.items():
            if hasattr(module, name):
                setattr(module, name, value)

    return modules


def ensure_hotel_app_fields(hotel: dict) -> dict:
    hotel = dict(hotel)

    hotel.setdefault("review_status", "new")
    hotel.setdefault("notes", "")
    hotel.setdefault("last_updated", get_now_stamp())
    hotel.setdefault("manager_contacts", hotel.get("manager_contacts") or [])
    hotel.setdefault("contact_leads", hotel.get("contact_leads") or [])
    hotel.setdefault(
        "contact_debug_candidates",
        hotel.get("contact_debug_candidates") or [],
    )

    return hotel


def ensure_contact_app_fields(contact: dict, default_status: str = "new") -> dict:
    contact = dict(contact)

    contact.setdefault("review_status", default_status)
    contact.setdefault("notes", "")
    contact.setdefault("last_updated", get_now_stamp())

    return contact


def normalize_hotel_list_for_app(hotels: list[dict]) -> list[dict]:
    clean_hotels = []

    for hotel in hotels:
        hotel = ensure_hotel_app_fields(hotel)

        hotel["manager_contacts"] = [
            ensure_contact_app_fields(contact, "confirmed")
            for contact in hotel.get("manager_contacts", [])
        ]

        hotel["contact_leads"] = [
            ensure_contact_app_fields(contact, "lead")
            for contact in hotel.get("contact_leads", [])
        ]

        hotel["contact_debug_candidates"] = [
            ensure_contact_app_fields(contact, "debug")
            for contact in hotel.get("contact_debug_candidates", [])
        ]

        clean_hotels.append(hotel)

    return clean_hotels


def load_cache(cache_path: str | Path | None = None) -> list[dict]:
    if cache_path is None:
        cache_path = get_active_cache_path()

    cache_path = Path(cache_path)

    if not cache_path.exists():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        save_hotels_to_cache([], cache_path)
        return []

    hotels = load_hotels_from_cache(cache_path)
    hotels = dedupe_hotels(hotels)
    hotels = normalize_hotel_list_for_app(hotels)

    return hotels


def save_cache(
    hotels: list[dict],
    cache_path: str | Path | None = None,
) -> None:
    if cache_path is None:
        cache_path = get_active_cache_path()

    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    hotels = dedupe_hotels(hotels)
    hotels = normalize_hotel_list_for_app(hotels)

    save_hotels_to_cache(hotels, cache_path)


def backup_cache(cache_path: str | Path | None = None) -> Path:
    if cache_path is None:
        cache_path = get_active_cache_path()

    cache_path = Path(cache_path)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = cache_path.with_name(f"{cache_path.stem}_backup_{timestamp}.json")

    hotels = load_cache(cache_path)
    save_cache(hotels, backup_path)

    return backup_path


def add_hotel_to_cache(
    hotel: dict,
    cache_path: str | Path | None = None,
) -> list[dict]:
    hotels = load_cache(cache_path)

    hotel = ensure_hotel_app_fields(hotel)
    hotel["review_status"] = hotel.get("review_status") or "manual"

    hotels.append(hotel)
    hotels = dedupe_hotels(hotels)

    save_cache(hotels, cache_path)

    return hotels


def update_hotel_status(
    hotel_index: int,
    status: str,
    cache_path: str | Path | None = None,
) -> list[dict]:
    hotels = load_cache(cache_path)

    if 0 <= hotel_index < len(hotels):
        hotels[hotel_index]["review_status"] = status
        hotels[hotel_index]["last_updated"] = get_now_stamp()

    save_cache(hotels, cache_path)

    return hotels


def update_contact_status(
    hotel_index: int,
    bucket: str,
    contact_index: int,
    status: str,
    cache_path: str | Path | None = None,
) -> list[dict]:
    hotels = load_cache(cache_path)

    valid_buckets = {
        "manager_contacts",
        "contact_leads",
        "contact_debug_candidates",
    }

    if bucket not in valid_buckets:
        return hotels

    if 0 <= hotel_index < len(hotels):
        contacts = hotels[hotel_index].get(bucket) or []

        if 0 <= contact_index < len(contacts):
            contacts[contact_index]["review_status"] = status
            contacts[contact_index]["last_updated"] = get_now_stamp()

    save_cache(hotels, cache_path)

    return hotels


def move_contact_between_buckets(
    hotel_index: int,
    source_bucket: str,
    contact_index: int,
    target_bucket: str,
    cache_path: str | Path | None = None,
) -> list[dict]:
    hotels = load_cache(cache_path)

    valid_buckets = {
        "manager_contacts",
        "contact_leads",
        "contact_debug_candidates",
    }

    if source_bucket not in valid_buckets:
        return hotels

    if target_bucket not in valid_buckets:
        return hotels

    if not (0 <= hotel_index < len(hotels)):
        return hotels

    source_contacts = hotels[hotel_index].get(source_bucket) or []

    if not (0 <= contact_index < len(source_contacts)):
        return hotels

    contact = source_contacts.pop(contact_index)

    if target_bucket == "manager_contacts":
        contact["review_status"] = "confirmed"
    elif target_bucket == "contact_leads":
        contact["review_status"] = "lead"
    else:
        contact["review_status"] = "debug"

    contact["last_updated"] = get_now_stamp()

    target_contacts = hotels[hotel_index].get(target_bucket) or []
    target_contacts.append(contact)

    hotels[hotel_index][source_bucket] = source_contacts
    hotels[hotel_index][target_bucket] = target_contacts

    save_cache(hotels, cache_path)

    return hotels


def run_hotel_discovery(
    settings: dict | None = None,
    target_roles: list[str] | None = None,
    cache_path: str | Path | None = None,
    purge_path: str | Path | None = None,
    save_results: bool = True,
) -> list[dict]:
    settings = normalize_settings(settings)

    if settings.get("complete_search"):
        # Complete search should be wider, but the final target is estimated
        # after real candidate URLs are discovered. No city/area assumptions.
        settings["max_search_results"] = max(int(settings.get("max_search_results") or 0), 20)

    modules = apply_runtime_settings(settings, target_roles)

    discovery = modules["discovery"]
    url_utils = modules["url_utils"]
    hotel_scraper = modules["hotel_scraper"]
    validation = modules["validation"]

    if purge_path is None:
        purge_path = get_active_purge_path()

    purge_list = load_purge_list(purge_path)

    grouped_urls = discovery.discover_candidate_urls()

    candidate_urls = url_utils.select_balanced_urls(
        grouped_urls,
        complete_search=bool(settings.get("complete_search")),
        target_count=settings.get("target_hotels"),
    )

    if settings.get("complete_search"):
        estimated_count = estimate_hotel_count_from_urls(candidate_urls, url_utils)
        settings["estimated_hotel_count"] = estimated_count
        settings["target_hotels"] = max(int(settings.get("target_hotels") or 0), estimated_count)
        settings["max_pages_to_try"] = max(int(settings.get("max_pages_to_try") or 0), estimated_count * 2)
        print(f"Complete search estimate from discovered sources: about {estimated_count} hotels")

    clean_candidate_urls = []

    for url in candidate_urls:
        decision = get_purge_decision_for_url(url, purge_list)

        if decision["blocked"]:
            print("Skipped purged URL:", url)
            print("Reasons:", decision["reasons"])
            continue

        clean_candidate_urls.append(url)

    print("\n---------------- Balanced Candidate URLs ----------------")

    for url in clean_candidate_urls:
        print(url_utils.score_url(url), url_utils.classify_url(url), url)

    final_hotels = []

    for url in clean_candidate_urls[:settings["max_pages_to_try"]]:
        if len(final_hotels) >= settings["target_hotels"]:
            break

        try:
            result = hotel_scraper.scrape_hotel_page(url)
            data = validation.unwrap_result(result)

            if isinstance(data, BaseModel):
                data = data.model_dump()

            data = validation.normalize_hotel_record(data, url)

            if not validation.is_valid_hotel_record(data):
                print("Rejected result from:", url)
                print(data)
                continue

            hotel_decision = get_purge_decision_for_hotel(data, purge_list)

            if hotel_decision["blocked"]:
                print("Skipped purged hotel:", data.get("hotel_name"))
                print("Reasons:", hotel_decision["reasons"])
                continue

            data = ensure_hotel_app_fields(data)
            data["review_status"] = "approved"
            data["search_name"] = settings.get("search_name")
            data["search_mode"] = "complete" if settings.get("complete_search") else "partial"
            data["estimated_hotel_count"] = settings.get("estimated_hotel_count")

            final_hotels.append(data)
            print("Accepted hotel:", data.get("hotel_name"))

        except Exception as error:
            print("Failed to scrape:", url)
            print("Error:", error)

            try:
                candidate_score = url_utils.score_url(url)
                source_type = url_utils.classify_url(url)
            except Exception:
                candidate_score = 0
                source_type = "unknown"

            if candidate_score >= 80:
                fallback_hotel = make_fallback_hotel_from_url(url, settings, source_type)
                final_hotels.append(fallback_hotel)
                print("Kept high-confidence hotel for review/contact search:", fallback_hotel.get("hotel_name"))

    final_hotels = dedupe_hotels(final_hotels)
    final_hotels = normalize_hotel_list_for_app(final_hotels)

    if save_results:
        save_cache(final_hotels, cache_path)

    return final_hotels


def run_contact_enrichment(
    hotels: list[dict] | None = None,
    settings: dict | None = None,
    target_roles: list[str] | None = None,
    cache_path: str | Path | None = None,
    save_after_each_hotel: bool = True,
) -> list[dict]:
    settings = normalize_settings(settings)

    modules = apply_runtime_settings(settings, target_roles)
    contacts = modules["contacts"]

    if hotels is None:
        hotels = load_cache(cache_path)

    hotels = normalize_hotel_list_for_app(hotels)

    enriched_hotels = []

    for hotel in hotels:
        status = str(hotel.get("review_status") or "").lower()

        if status in {"rejected", "duplicate", "purged"}:
            enriched_hotels.append(hotel)
            continue

        hotel["target_contact_count"] = int(
            settings.get("target_contact_count")
            or settings.get("contact_count")
            or 1
        )

        enriched_hotel = contacts.enrich_hotel_with_contacts(hotel)
        enriched_hotel = ensure_hotel_app_fields(enriched_hotel)
        enriched_hotel["review_status"] = "enriched"
        enriched_hotel["last_enriched"] = get_now_stamp()
        enriched_hotel["last_updated"] = get_now_stamp()

        enriched_hotel["manager_contacts"] = [
            ensure_contact_app_fields(contact, "confirmed")
            for contact in enriched_hotel.get("manager_contacts", [])
        ]

        enriched_hotel["contact_leads"] = [
            ensure_contact_app_fields(contact, "lead")
            for contact in enriched_hotel.get("contact_leads", [])
        ]

        enriched_hotel["contact_debug_candidates"] = [
            ensure_contact_app_fields(contact, "debug")
            for contact in enriched_hotel.get("contact_debug_candidates", [])
        ]

        enriched_hotels.append(enriched_hotel)

        if save_after_each_hotel:
            partial_hotels = enriched_hotels + hotels[len(enriched_hotels):]
            save_cache(partial_hotels, cache_path)

    enriched_hotels = dedupe_hotels(enriched_hotels)
    enriched_hotels = normalize_hotel_list_for_app(enriched_hotels)

    save_cache(enriched_hotels, cache_path)

    return enriched_hotels


def run_full_pipeline(
    settings: dict | None = None,
    target_roles: list[str] | None = None,
    cache_path: str | Path | None = None,
    purge_path: str | Path | None = None,
) -> list[dict]:
    hotels = run_hotel_discovery(
        settings=settings,
        target_roles=target_roles,
        cache_path=cache_path,
        purge_path=purge_path,
        save_results=True,
    )

    hotels = run_contact_enrichment(
        hotels=hotels,
        settings=settings,
        target_roles=target_roles,
        cache_path=cache_path,
        save_after_each_hotel=True,
    )

    return hotels


def get_hotel_summary_rows(hotels: list[dict]) -> list[dict]:
    rows = []

    for index, hotel in enumerate(hotels):
        manager_contacts = hotel.get("manager_contacts") or []
        contact_leads = hotel.get("contact_leads") or []
        debug_candidates = hotel.get("contact_debug_candidates") or []

        rows.append(
            {
                "index": index,
                "hotel_name": hotel.get("hotel_name"),
                "location": hotel.get("location") or hotel.get("area"),
                "website": hotel.get("website"),
                "source_url": hotel.get("source_url"),
                "review_status": hotel.get("review_status"),
                "confirmed_contacts": len(manager_contacts),
                "contact_leads": len(contact_leads),
                "debug_candidates": len(debug_candidates),
                "last_updated": hotel.get("last_updated"),
            }
        )

    return rows


def get_contact_rows(hotels: list[dict], bucket: str = "manager_contacts") -> list[dict]:
    rows = []

    for hotel_index, hotel in enumerate(hotels):
        contacts = hotel.get(bucket) or []

        for contact_index, contact in enumerate(contacts):
            rows.append(
                {
                    "hotel_index": hotel_index,
                    "contact_index": contact_index,
                    "bucket": bucket,
                    "hotel_name": hotel.get("hotel_name"),
                    "hotel_location": hotel.get("location") or hotel.get("area"),
                    "hotel_website": hotel.get("website") or hotel.get("source_url"),
                    "name": contact.get("name"),
                    "role": contact.get("role") or contact.get("matched_role"),
                    "email": contact.get("email"),
                    "linkedin_url": contact.get("linkedin_url"),
                    "profile_url": contact.get("profile_url"),
                    "source_url": contact.get("source_url") or contact.get("url"),
                    "confidence": contact.get("confidence"),
                    "evidence_type": contact.get("evidence_type"),
                    "score": contact.get("score"),
                    "review_status": contact.get("review_status"),
                    "notes": contact.get("notes"),
                }
            )

    return rows


def export_rows_to_csv(rows: list[dict], export_path: str | Path) -> Path:
    export_path = Path(export_path)
    export_path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        with open(export_path, "w", newline="", encoding="utf-8") as file:
            file.write("")

        return export_path

    fieldnames = list(rows[0].keys())

    with open(export_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return export_path


def export_hotels_csv(
    hotels: list[dict] | None = None,
    export_path: str | Path = "exports/hotels.csv",
    cache_path: str | Path | None = None,
) -> Path:
    if hotels is None:
        hotels = load_cache(cache_path)

    rows = get_hotel_summary_rows(hotels)

    return export_rows_to_csv(rows, export_path)


def export_contacts_csv(
    hotels: list[dict] | None = None,
    export_path: str | Path = "exports/contacts.csv",
    cache_path: str | Path | None = None,
) -> Path:
    if hotels is None:
        hotels = load_cache(cache_path)

    rows = get_contact_rows(hotels, "manager_contacts")

    return export_rows_to_csv(rows, export_path)


def export_leads_csv(
    hotels: list[dict] | None = None,
    export_path: str | Path = "exports/contact_leads.csv",
    cache_path: str | Path | None = None,
) -> Path:
    if hotels is None:
        hotels = load_cache(cache_path)

    rows = get_contact_rows(hotels, "contact_leads")

    return export_rows_to_csv(rows, export_path)


def print_hotel_summary(hotels: list[dict]) -> None:
    print("\n---------------- Run Summary ----------------")

    for index, hotel in enumerate(hotels, start=1):
        hotel_name = hotel.get("hotel_name", "Unknown hotel")
        location = hotel.get("location") or hotel.get("area") or "Unknown location"

        manager_contacts = hotel.get("manager_contacts") or []
        contact_leads = hotel.get("contact_leads") or []

        print(f"\n{index}. {hotel_name}")
        print(f"   Location: {location}")
        print(f"   Status: {hotel.get('review_status', 'unknown')}")
        print(f"   Confirmed contacts: {len(manager_contacts)}")
        print(f"   Contact leads: {len(contact_leads)}")

        if manager_contacts:
            print("   Managers:")

            for contact in manager_contacts:
                name = contact.get("name", "Unknown")
                role = contact.get("role", "Unknown role")
                source = contact.get("source_url") or contact.get("profile_url") or ""

                print(f"   - {name} | {role}")

                if source:
                    print(f"     Source: {source}")