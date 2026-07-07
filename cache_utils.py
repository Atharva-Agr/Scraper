import json
import re


def save_hotels_to_cache(hotels, filename="hotel_cache.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(hotels, f, indent=4, ensure_ascii=False)


def load_hotels_from_cache(filename="hotel_cache.json"):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_hotel_key(value: str) -> str:
    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()

    return value


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
    ]

    for field in useful_fields:
        if hotel.get(field):
            score += 10

    if hotel.get("room_types"):
        score += 10

    if hotel.get("facilities"):
        score += 10

    source_url = str(
        hotel.get("source_url") or hotel.get("website") or ""
    ).lower()

    mirror_signals = [
        "sg-singapore.com",
        "singapore-sg.com",
        "hotelsingapore.info",
        "singaporehotels365.com",
        "hotel-rn.com",
    ]

    if any(signal in source_url for signal in mirror_signals):
        score -= 30

    return score


def dedupe_hotels(hotels: list[dict]) -> list[dict]:
    best_by_name = {}

    for hotel in hotels:
        hotel_name = hotel.get("hotel_name")

        if not hotel_name:
            continue

        key = normalize_hotel_key(hotel_name)

        if key not in best_by_name:
            best_by_name[key] = hotel
            continue

        current_best = best_by_name[key]

        if hotel_record_score(hotel) > hotel_record_score(current_best):
            best_by_name[key] = hotel

    return list(best_by_name.values())