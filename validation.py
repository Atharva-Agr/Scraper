from pydantic import BaseModel

from config import area, location, nearby_area_terms, excluded_location_terms
from url_utils import is_bad_url, get_domain
from typing import List


def unwrap_result(result):
    if isinstance(result, dict) and "content" in result:
        return result["content"]
    return result


def is_target_location(record: dict) -> bool:
    combined = " ".join([
        str(record.get("hotel_name") or ""),
        str(record.get("location") or ""),
        str(record.get("area") or ""),
        str(record.get("website") or ""),
        str(record.get("source_url") or ""),
    ]).lower()

    target_terms = [
        area.lower(),
        location.lower(),
    ]

    target_terms += [
        term.lower()
        for term in nearby_area_terms
        if term
    ]

    bad_location_terms = [
        term.lower()
        for term in excluded_location_terms
        if term
    ]

    if any(bad in combined for bad in bad_location_terms):
        return False

    return any(term in combined for term in target_terms)



def looks_like_hotel(record: dict) -> bool:
    hotel_name = str(record.get("hotel_name") or "").lower()
    hotel_type = str(record.get("hotel_type") or "").lower()
    website = str(record.get("website") or "").lower()
    source_url = str(record.get("source_url") or "").lower()

    combined = " ".join([hotel_name, hotel_type, website, source_url])

    hotel_words = [
        "hotel",
        "inn",
        "resort",
        "plaza",
        "palace",
        "premier",
        "residences",
        "suites",
        "marriott",
        "hyatt",
        "holiday inn",
        "novotel",
        "pullman",
        "ibis",
        "lemon tree",
        "roseate",
        "radisson",
        "pride",
        "aloft",
        "ihg",  
    ]

    if any(word in combined for word in hotel_words):
        return True

    return False


def is_valid_hotel_record(record) -> bool:
    if not isinstance(record, dict):
        return False

    hotel_name = record.get("hotel_name")
    source_url = record.get("source_url") or record.get("website")

    if not hotel_name:
        return False

    if not source_url:
        return False

    if is_bad_url(str(source_url)):
        return False

    fake_names = [
        f"business hotel {area.lower()}",
        f"{location.lower()} business plaza",
        f"{area.lower()} business inn",
        "example hotel",
    ]

    if str(hotel_name).lower().strip() in fake_names:
        return False

    # Reject banquet-only venues unless they are clearly hotels.
    if "banquet" in str(hotel_name).lower() and not looks_like_hotel(record):
        return False

    if not looks_like_hotel(record):
        return False

    if not is_target_location(record):
        return False

    return True

def normalize_hotel_record(data: dict, source_url: str) -> dict:
    if not isinstance(data, dict):
        return data

    normalized = dict(data)

    if not normalized.get("hotel_name") and normalized.get("name"):
        normalized["hotel_name"] = normalized.get("name")

    if isinstance(normalized.get("location"), dict):
        normalized["location"] = normalized["location"].get("address")

    if isinstance(normalized.get("contact"), dict):
        contact = normalized["contact"]
        normalized["phone"] = normalized.get("phone") or contact.get("phone")
        normalized["email"] = normalized.get("email") or contact.get("email")

    if not normalized.get("facilities") and normalized.get("amenities"):
        normalized["facilities"] = normalized.get("amenities")

    if isinstance(normalized.get("rating"), dict):
        normalized["rating"] = str(normalized["rating"])

    normalized["source_url"] = normalized.get("source_url") or source_url

    return normalized


def normalize_text(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def dedupe_hotels(hotels: List[dict]) -> List[dict]:
    seen = set()
    unique_hotels = []

    for hotel in hotels:
        hotel_name = normalize_text(hotel.get("hotel_name"))
        website = hotel.get("website") or hotel.get("source_url") or ""
        domain = get_domain(str(website))

        domain = domain.replace("www.", "")

        key = f"{hotel_name}|{domain}"

        if key in seen:
            continue

        seen.add(key)
        unique_hotels.append(hotel)

    return unique_hotels