from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()


# -----------------------------
# Paths
# -----------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

HOTEL_CACHE_FILE = BASE_DIR / "hotel_cache.json"
PURGE_LIST_FILE = DATA_DIR / "purge_list.json"


# -----------------------------
# Fixed/default contact roles
# -----------------------------

CONTACT_ROLES = [
    "general manager",
    "hotel manager",
    "resident manager",
    "operations manager",
    "director of operations",
    "rooms division manager",
    "director of rooms",
    "executive housekeeper",
    "housekeeping manager",
    "procurement manager",
    "purchasing manager",
    "purchase manager",
    "director of procurement",
]

SECONDARY_CONTACT_ROLES = [
    "owner",
    "managing director",
    "cluster general manager",
    "area general manager",
    "regional general manager",
    "director of sales",
    "director of sales and marketing",
    "sales manager",
    "events manager",
    "event manager",
    "banquet manager",
    "catering sales manager",
    "director of food and beverage",
    "food and beverage manager",
    "front office manager",
    "facilities manager",
    "engineering manager",
    "director of engineering",
    "finance manager",
]

IGNORED_CONTACT_ROLES = [
    "chef",
    "executive chef",
    "sous chef",
    "pastry chef",
    "human resources",
    "director of human resources",
    "hr manager",
    "talent acquisition",
    "recruiter",
    "front desk agent",
    "receptionist",
    "guest service executive",
    "guest relations executive",
    "concierge",
    "security manager",
    "spa manager",
    "marketing executive",
    "sales executive",
    "reservations agent",
    "reservation agent",
    "intern",
    "trainee",
]


# -----------------------------
# Testing defaults
# -----------------------------

TESTING_SETTINGS = {
    "location": "",
    "area": "",
    "hotel_type": "Business hotel",
    "extra_info": "",

    "nearby_area_terms": [],
    "excluded_location_terms": [],

    "max_search_results": 10,
    "max_pages_to_try": 8,
    "target_hotels": 3,

    "max_contact_search_results": 4,
    "max_contact_pages_per_hotel": 2,

    "RUN_PHASE_1": True,
    "RUN_PHASE_2": True,
    "USE_CACHED_HOTELS": False,
}


# -----------------------------
# Runtime exported defaults
# -----------------------------

settings = deepcopy(TESTING_SETTINGS)

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

contact_roles = list(CONTACT_ROLES)
secondary_contact_roles = list(SECONDARY_CONTACT_ROLES)
ignored_contact_roles = list(IGNORED_CONTACT_ROLES)
all_contact_roles = list(CONTACT_ROLES) + list(SECONDARY_CONTACT_ROLES)

RUN_PHASE_1 = settings["RUN_PHASE_1"]
RUN_PHASE_2 = settings["RUN_PHASE_2"]
USE_CACHED_HOTELS = settings["USE_CACHED_HOTELS"]


# -----------------------------
# ScrapeGraph config
# -----------------------------

LLM_MODEL = os.getenv("LINENGRASS_LLM_MODEL", "ollama/qwen2.5:7b")
LLM_TOKENS = int(os.getenv("LINENGRASS_LLM_TOKENS", "8192"))


graph_config = {
    "llm": {
        "model": LLM_MODEL,
        "temperature": 0,
        "format": "json",
        "model_tokens": LLM_TOKENS,
    },
    "verbose": True,
    "timeout": 660,
}


# -----------------------------
# Input helpers
# -----------------------------

def ask_text(prompt: str, default: str = "", required: bool = False) -> str:
    while True:
        answer = input(f"{prompt} [{default}]: ").strip()
        value = answer or default

        if value:
            return value

        if not required:
            return ""

        print("This field is required.")


def ask_int(prompt: str, default: int, minimum: int = 1) -> int:
    answer = input(f"{prompt} [{default}]: ").strip()

    if not answer:
        return default

    try:
        value = int(answer)

    except ValueError:
        print(f"Invalid number. Using default: {default}")
        return default

    if value < minimum:
        print(f"Value too small. Using default: {default}")
        return default

    return value


def ask_bool(prompt: str, default: bool) -> bool:
    suffix = "Y/n" if default else "y/N"

    while True:
        answer = input(f"{prompt} [{suffix}]: ").strip().lower()

        if not answer:
            return default

        if answer in {"y", "yes"}:
            return True

        if answer in {"n", "no"}:
            return False

        print("Please enter y or n.")


def ask_choice(prompt: str, valid_choices: list[str], default: str) -> str:
    while True:
        answer = input(f"{prompt} [{default}]: ").strip() or default

        if answer in valid_choices:
            return answer

        print(f"Invalid choice. Choose one of: {', '.join(valid_choices)}")


def ask_list(prompt: str, default: list[str], example: str) -> list[str]:
    print(f"\n{prompt}")
    print(f"Example: {example}")

    answer = input("Enter comma-separated values or press Enter for default: ").strip()

    if not answer:
        return list(default)

    values = []
    seen = set()

    for item in answer.split(","):
        value = item.strip()

        if not value:
            continue

        key = value.lower()

        if key in seen:
            continue

        seen.add(key)
        values.append(value)

    return values


# -----------------------------
# Settings builders
# -----------------------------

def get_testing_settings() -> dict:
    return deepcopy(TESTING_SETTINGS)


def get_custom_settings() -> dict:
    print("\nCustom search setup")
    print("-------------------")
    print("Press Enter to use the recommended default shown in brackets.\n")

    return {
        "location": ask_text("Location / city", "", required=True),
        "area": ask_text("Area / neighborhood", ""),
        "hotel_type": ask_text("Hotel type", "Business hotel"),
        "extra_info": ask_text(
            "Extra info",
            "",
        ),

        "nearby_area_terms": ask_list(
            "Nearby area terms help match hotels close to the target area.",
            [],
            "",
        ),

        "excluded_location_terms": ask_list(
            "Excluded location terms help avoid nearby but wrong locations.",
            [],
            "",
        ),

        "max_search_results": ask_int("Search results per query", 10),
        "max_pages_to_try": ask_int("Max hotel pages to try", 8),
        "target_hotels": ask_int("Target valid hotels to accept", 3),

        "max_contact_search_results": ask_int("Contact search results per query", 4),
        "max_contact_pages_per_hotel": ask_int("Contact pages to scrape per hotel", 2),

        "RUN_PHASE_1": True,
        "RUN_PHASE_2": True,
        "USE_CACHED_HOTELS": False,
    }


def apply_phase_settings(runtime_settings: dict, use_testing: bool) -> None:
    print("\nChoose run type")
    print("---------------")
    print("1. Full run: discover hotels + enrich contacts")
    print("2. Contacts only: use cached hotels + enrich contacts")
    print("3. Hotel discovery only: discover hotels, no contact enrichment")

    default_choice = "2" if use_testing else "1"
    run_choice = ask_choice("Choose run type", ["1", "2", "3"], default_choice)

    if run_choice == "1":
        runtime_settings["RUN_PHASE_1"] = True
        runtime_settings["RUN_PHASE_2"] = True
        runtime_settings["USE_CACHED_HOTELS"] = False

    elif run_choice == "2":
        runtime_settings["RUN_PHASE_1"] = False
        runtime_settings["RUN_PHASE_2"] = True
        runtime_settings["USE_CACHED_HOTELS"] = True

    elif run_choice == "3":
        runtime_settings["RUN_PHASE_1"] = True
        runtime_settings["RUN_PHASE_2"] = False
        runtime_settings["USE_CACHED_HOTELS"] = False


def print_settings_summary(runtime_settings: dict) -> None:
    print("\nSelected settings")
    print("-----------------")
    print(f"Location: {runtime_settings['location']}")
    print(f"Area: {runtime_settings['area']}")
    print(f"Hotel type: {runtime_settings['hotel_type']}")
    print(f"Extra info: {runtime_settings['extra_info']}")
    print(f"Contact roles: {', '.join(CONTACT_ROLES)}")
    print(f"Run Phase 1: {runtime_settings['RUN_PHASE_1']}")
    print(f"Run Phase 2: {runtime_settings['RUN_PHASE_2']}")
    print(f"Use cached hotels: {runtime_settings['USE_CACHED_HOTELS']}")
    print(f"Target hotels: {runtime_settings['target_hotels']}")
    print(f"Hotel pages to try: {runtime_settings['max_pages_to_try']}")
    print(f"Search results per query: {runtime_settings['max_search_results']}")
    print(f"Contact results per query: {runtime_settings['max_contact_search_results']}")
    print(f"Contact pages per hotel: {runtime_settings['max_contact_pages_per_hotel']}")


def apply_settings_to_globals(runtime_settings: dict) -> None:
    global settings
    global location
    global area
    global hotel_type
    global extra_info
    global nearby_area_terms
    global excluded_location_terms
    global max_search_results
    global max_pages_to_try
    global target_hotels
    global max_contact_search_results
    global max_contact_pages_per_hotel
    global contact_roles
    global secondary_contact_roles
    global ignored_contact_roles
    global all_contact_roles
    global RUN_PHASE_1
    global RUN_PHASE_2
    global USE_CACHED_HOTELS

    settings = deepcopy(runtime_settings)

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

    contact_roles = list(CONTACT_ROLES)
    secondary_contact_roles = list(SECONDARY_CONTACT_ROLES)
    ignored_contact_roles = list(IGNORED_CONTACT_ROLES)
    all_contact_roles = list(CONTACT_ROLES) + list(SECONDARY_CONTACT_ROLES)

    RUN_PHASE_1 = settings["RUN_PHASE_1"]
    RUN_PHASE_2 = settings["RUN_PHASE_2"]
    USE_CACHED_HOTELS = settings["USE_CACHED_HOTELS"]


def configure_from_cli() -> dict:
    use_testing_settings = ask_bool("Use testing settings?", default=True)

    if use_testing_settings:
        runtime_settings = get_testing_settings()
    else:
        runtime_settings = get_custom_settings()

    apply_phase_settings(runtime_settings, use_testing_settings)
    apply_settings_to_globals(runtime_settings)
    print_settings_summary(runtime_settings)

    return runtime_settings