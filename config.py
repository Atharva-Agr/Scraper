from dotenv import load_dotenv
from pathlib import Path
load_dotenv()


# -----------------------------
# User inputs
# -----------------------------

# -----------------------------
# Search input settings
# -----------------------------

# -----------------------------
# Search settings
# -----------------------------

TESTING_SETTINGS = {
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

    "RUN_PHASE_1": False,
    "RUN_PHASE_2": True,
    "USE_CACHED_HOTELS": True,
}


def ask_text(prompt: str, default: str = "") -> str:
    answer = input(f"{prompt} [{default}]: ").strip()
    return answer or default


def ask_int(prompt: str, default: int) -> int:
    answer = input(f"{prompt} [{default}]: ").strip()

    if not answer:
        return default

    try:
        return int(answer)
    except ValueError:
        print(f"Invalid number. Using default: {default}")
        return default


def ask_bool(prompt: str, default: bool) -> bool:
    suffix = "Y/n" if default else "y/N"
    answer = input(f"{prompt} [{suffix}]: ").strip().lower()

    if not answer:
        return default

    return answer in ["y", "yes"]


def ask_list(prompt: str, default: list[str], example: str) -> list[str]:
    print(f"{prompt}")
    print(f"Example: {example}")

    answer = input(f"Enter comma-separated values or press Enter for default: ").strip()

    if not answer:
        return default

    return [
        item.strip()
        for item in answer.split(",")
        if item.strip()
    ]


use_testing = ask_bool("Use testing settings?", default=True)

if use_testing:
    settings = TESTING_SETTINGS

else:
    print("\nCustom search setup")
    print("-------------------")

    settings = {
        "location": ask_text("Location / city", "Delhi"),
        "area": ask_text("Area / neighborhood", "Aerocity"),
        "hotel_type": ask_text("Hotel type", "business hotels"),
        "extra_info": ask_text(
            "Extra info",
            "Prefer hotels with banquet halls or conference facilities.",
        ),

        "nearby_area_terms": ask_list(
            "Nearby area terms help match hotels close to the target area.",
            ["airport", "hospitality district"],
            "Mahipalpur, Rangpuri, IGI, airport",
        ),

        "excluded_location_terms": ask_list(
            "Excluded location terms help avoid nearby but wrong locations.",
            [],
            "Noida, Gurgaon, Ghaziabad",
        ),

        "max_search_results": ask_int("Search results per query", 10),
        "max_pages_to_try": ask_int("Max hotel pages to try", 8),
        "target_hotels": ask_int("Target valid hotels to accept", 3),

        "max_contact_search_results": ask_int("Contact search results per query", 4),
        "max_contact_pages_per_hotel": ask_int("Contact pages to scrape per hotel", 2),

        "USE_CACHED_HOTELS": ask_bool("Use cached hotels?", default=False),
        "RUN_PHASE_1": True,
        "RUN_PHASE_2": True,
    }

    if settings["USE_CACHED_HOTELS"]:
        settings["RUN_PHASE_1"] = False


location = settings["location"]
area = settings["area"]
hotel_type = settings["hotel_type"]
extra_info = settings["extra_info"]

nearby_area_terms = settings["nearby_area_terms"]
excluded_location_terms = settings["excluded_location_terms"]

max_search_results = settings["max_search_results"]
max_pages_to_try = settings["max_pages_to_try"]
target_hotels = settings["target_hotels"]

max_contact_search_results = settings["max_contact_search_results"]
max_contact_pages_per_hotel = settings["max_contact_pages_per_hotel"]

RUN_PHASE_1 = settings["RUN_PHASE_1"]
RUN_PHASE_2 = settings["RUN_PHASE_2"]
USE_CACHED_HOTELS = settings["USE_CACHED_HOTELS"]

BASE_DIR = Path(__file__).resolve().parent
HOTEL_CACHE_FILE = BASE_DIR / "hotel_cache.json"
# -----------------------------
# ScrapeGraph config
# -----------------------------


graph_config = {
    "llm": {
        "model": "ollama/qwen2.5:7b",
        "temperature": 0,
        "format": "json",
        "model_tokens": 8192
    },
    "verbose": True,
    "timeout": 660 #user can change maybe
}

