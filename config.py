from dotenv import load_dotenv
from pathlib import Path
from copy import deepcopy

load_dotenv()


# -----------------------------
# Testing defaults
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
}


# -----------------------------
# Input helpers
# -----------------------------

def ask_text(prompt: str, default: str = "", required: bool = False) -> str:
    while True:
        answer = input(f"{prompt} [{default}]: ").strip()
        value = answer or default

        if value or not required:
            return value

        print("This field is required.")


def ask_int(prompt: str, default: int, minimum: int = 1) -> int:
    answer = input(f"{prompt} [{default}]: ").strip()

    if not answer:
        return default

    try:
        value = int(answer)

        if value < minimum:
            print(f"Value too small. Using default: {default}")
            return default

        return value

    except ValueError:
        print(f"Invalid number. Using default: {default}")
        return default


def ask_bool(prompt: str, default: bool) -> bool:
    suffix = "Y/n" if default else "y/N"

    while True:
        answer = input(f"{prompt} [{suffix}]: ").strip().lower()

        if not answer:
            return default

        if answer in ["y", "yes"]:
            return True

        if answer in ["n", "no"]:
            return False

        print("Please enter y or n.")


def ask_list(prompt: str, default: list[str], example: str) -> list[str]:
    print(f"\n{prompt}")
    print(f"Example: {example}")

    answer = input("Enter comma-separated values or press Enter for default: ").strip()

    if not answer:
        return default

    values = [
        item.strip()
        for item in answer.split(",")
        if item.strip()
    ]

    return values or default


def ask_choice(prompt: str, valid_choices: list[str], default: str) -> str:
    while True:
        answer = input(f"{prompt} [{default}]: ").strip() or default

        if answer in valid_choices:
            return answer

        print(f"Invalid choice. Choose one of: {', '.join(valid_choices)}")


# -----------------------------
# Settings setup
# -----------------------------

use_testing = ask_bool("Use testing settings?", default=True)

if use_testing:
    settings = deepcopy(TESTING_SETTINGS)

else:
    print("\nCustom search setup")
    print("-------------------")
    print("Press Enter to use the recommended default shown in brackets.\n")

    settings = {
        "location": ask_text("Location / city", "Delhi", required=True),
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
    }


# -----------------------------
# Phase setup
# -----------------------------

print("\nChoose run type")
print("---------------")
print("1. Full run: discover hotels + enrich contacts")
print("2. Contacts only: use cached hotels + enrich contacts")
print("3. Hotel discovery only: discover hotels, no contact enrichment")

default_run_choice = "2" if use_testing else "1"
run_choice = ask_choice("Choose run type", ["1", "2", "3"], default_run_choice)

if run_choice == "1":
    settings["RUN_PHASE_1"] = True
    settings["RUN_PHASE_2"] = True
    settings["USE_CACHED_HOTELS"] = False

elif run_choice == "2":
    settings["RUN_PHASE_1"] = False
    settings["RUN_PHASE_2"] = True
    settings["USE_CACHED_HOTELS"] = True

elif run_choice == "3":
    settings["RUN_PHASE_1"] = True
    settings["RUN_PHASE_2"] = False
    settings["USE_CACHED_HOTELS"] = False


# -----------------------------
# Summary
# -----------------------------

print("\nSelected settings")
print("-----------------")
print(f"Location: {settings['location']}")
print(f"Area: {settings['area']}")
print(f"Hotel type: {settings['hotel_type']}")
print(f"Run Phase 1: {settings['RUN_PHASE_1']}")
print(f"Run Phase 2: {settings['RUN_PHASE_2']}")
print(f"Use cached hotels: {settings['USE_CACHED_HOTELS']}")
print(f"Target hotels: {settings['target_hotels']}")
print(f"Hotel pages to try: {settings['max_pages_to_try']}")
print(f"Search results per query: {settings['max_search_results']}")
print(f"Contact results per query: {settings['max_contact_search_results']}")
print(f"Contact pages per hotel: {settings['max_contact_pages_per_hotel']}")


# -----------------------------
# Export settings for other files
# -----------------------------

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


# -----------------------------
# Paths
# -----------------------------

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
        "model_tokens": 8192,
    },
    "verbose": True,
    "timeout": 660,
}