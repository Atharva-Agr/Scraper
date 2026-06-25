import json


def save_hotels_to_cache(hotels, filename="hotel_cache.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(hotels, f, indent=4, ensure_ascii=False)


def load_hotels_from_cache(filename="hotel_cache.json"):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)