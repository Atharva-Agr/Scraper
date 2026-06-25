from typing import List, Optional
from urllib.parse import urlparse
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from ddgs import DDGS # type: ignore

from scrapegraphai.graphs import SmartScraperGraph

load_dotenv()


# -----------------------------
# User inputs
# -----------------------------

location = "Delhi"
area = "Aerocity"
hotel_type = "business hotels"
extra_info = "Prefer hotels with banquet halls or conference facilities."

contact_roles = [
    "general manager",
    "operations manager",
    "housekeeping manager",
    "procurement manager",
    "purchase manager",
    "front office manager",
    "owner",
    "director",
]

max_contact_search_results = 5
max_contact_pages_per_hotel = 8

nearby_area_terms = [
    "Mahipalpur",
    "Rangpuri",
    "IGI",
    "airport",
    "hospitality district"
]

excluded_location_terms = [
    "Noida",
    "Gurgaon",
    "Gurugram",
    "Ghaziabad",
    "Faridabad"
]

max_search_results = 10

# Try up to this many pages total
max_pages_to_try = 25

# Stop once this many valid hotels are accepted
target_hotels = 10


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
    "timeout": 4800
}


# -----------------------------
# Output schema
# -----------------------------

class HotelInfo(BaseModel):
    hotel_name: Optional[str] = Field(default=None)
    location: Optional[str] = Field(default=None)
    area: Optional[str] = Field(default=None)
    chain_or_independent: Optional[str] = Field(default=None)
    hotel_type: Optional[str] = Field(default=None)
    website: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    rating: Optional[str] = Field(default=None)
    review_summary: Optional[str] = Field(default=None)
    room_types: List[str] = Field(default_factory=list)
    room_pricing: List[str] = Field(default_factory=list)
    facilities: List[str] = Field(default_factory=list)
    source_url: Optional[str] = Field(default=None)

class ContactInfo(BaseModel):
    name: Optional[str] = Field(default=None)
    role: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    linkedin_url: Optional[str] = Field(default=None)
    profile_url: Optional[str] = Field(default=None)
    source_url: Optional[str] = Field(default=None)


class ContactResults(BaseModel):
    contacts: List[ContactInfo] = Field(default_factory=list)


# -----------------------------
# URL filtering
# -----------------------------

BAD_DOMAINS = [
    # social / video
    "facebook",
    "instagram",
    "youtube",
    "twitter",
    "x.com",

    # booking / directory / review sources
    "justdial",
    "makemytrip",
    "goibibo",
    "tripadvisor",
    "agoda",
    "trivago",
    "yandex",
    "google.com/travel",
    "virtualtourist",
    "bag2bag",
    "brevistay",
    "weddingz",
    "venuelook",
    "venuepool",
    "eventmandi",
    "thevenuez",
    "hotelplanner",
    "cleartrip",
    "booking.com",
    "hotels.com",
    "fabhotels",
    "oyorooms",
    "holidify",

    # blogs / random pages
    "happyfares",
    "scanx.trade",
    "soniroy",
    "-magazine",
    "anamikamishra",
    "northguwahati",
    "queknow",
    "bookmark4you",
    "escort",
    "adult",
    "incall",
    "callgirl",
    "callgirls",
    "trip.com",
    "qantas.com/hotels",
    "expedia",
    "kayak",
    "skyscanner",

    # presentation / document / content farms
    "slideserve",
    "slideshare",
    "powerpoint",
    "ppt-presentation",

    # mirror / SEO hotel pages
    "hotels-of-",
    "hotels-in-",
    "tophotel",
    "ihotel",
]


BAD_EXTENSIONS = [
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".pdf",
    ".mp4",
    ".zip",
]


def get_domain(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")


def has_bad_extension(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in BAD_EXTENSIONS)


def is_bad_url(url: str) -> bool:
    url_lower = url.lower()
    domain = get_domain(url)

    if not url_lower.startswith(("http://", "https://")):
        return True

    if any(bad in url_lower for bad in BAD_DOMAINS):
        return True

    if has_bad_extension(url):
        return True

    # Avoid foreign mirror sites for now.
    if domain.endswith(".cn"):
        return True

    return False


def is_probably_relevant(url: str) -> bool:
    url_lower = url.lower()

    useful_words = [
        "hotel",
        "hotels",
        "inn",
        "suites",
        "resort",
        "rooms",
        "stay",
        "contact",
        "meetings",
        "events",
        "conference",
        "banquet",
        area.lower(),
        location.lower(),
    ]

    return any(
        word and word in url_lower
        for word in useful_words
    )


def clean_url(url: str) -> str:
    return url.strip()

def classify_url(url: str) -> str:
    url_lower = url.lower()
    domain = get_domain(url)

    chain_words = [
        "marriott", "hyatt", "ihg", "accor", "radisson",
        "hilton", "sheraton", "novotel", "pullman", "ibis",
        "holidayinn", "lemontree"
    ]

    directory_words = [
        "venue", "banquet", "wedding", "travel", "tour",
        "guide", "booking", "trip", "qantas", "rooms.com",
        "hotels-of", "hotels-in", "tophotel", "ihotel"
    ]

    hotel_words = [
        "hotel", "inn", "suites", "resort", "stay",
        "plaza", "palace", "hospitality"
    ]

    # Check directory first so "hotels-of-new-delhi.com"
    # does not get treated as an official hotel site.
    if any(word in domain or word in url_lower for word in directory_words):
        return "directory"

    if any(word in domain for word in chain_words):
        return "chain"

    if any(word in domain for word in hotel_words):
        return "direct_hotel_site"

    return "unknown"

def score_url(url: str) -> int:
    url_lower = url.lower()

    if is_bad_url(url):
        return -9999

    source_type = classify_url(url)
    score = 0

    if source_type == "direct_hotel_site":
        score += 100
    elif source_type == "chain":
        score += 55
    elif source_type == "directory":
        score += 15
    else:
        score += 5

    location_terms = [
        area.lower(),
        location.lower(),
        "airport",
        "hospitality district",
        "business district"
    ]

    for term in location_terms:
        if term and term in url_lower:
            score += 15

    good_paths = [
        "contact", "contact-us", "overview", "hotel",
        "rooms", "meeting", "meetings", "events", "facilities"
    ]

    for path in good_paths:
        if path in url_lower:
            score += 10

    weak_paths = [
        "photos", "gallery", "review", "reviews", "blog",
        "blogs", "offers", "careers", "reservation", "dining"
    ]

    bad_content_words = [
        "powerpoint",
        "ppt",
        "presentation",
        "review",
        "blog",
        "article",
        "guide",
        "list-of",
        "top-10",
        "best-hotels",
    ]

    for word in bad_content_words:
        if word in url_lower:
            score -= 30

    for path in weak_paths:
        if path in url_lower:
            score -= 20

    path = urlparse(url).path.strip("/")
    if path == "":
        score -= 30

    return score

# -----------------------------
# Search for candidate URLs
# -----------------------------

def build_search_query_groups():
    return {
        "chain_hotels": [
            f"site:marriott.com {area} {location} hotel",
            f"site:ihg.com {area} {location} hotel",
            f"site:hyatt.com {area} {location} hotel",
            f"site:accor.com {area} {location} hotel",
            f"site:roseatehotels.com {area} {location} hotel",
            f"site:lemontreehotels.com {area} {location} hotel",
        ],

        "mid_size_hotels": [
            f"independent hotel {area} {location} official website",
            f"mid size hotel {area} {location} official website",
            f"3 star hotel {area} {location} official website",
            f"4 star hotel {area} {location} official website",
            f"business hotel near Delhi airport official website",

        ],

        "banquet_business_hotels": [
            f"hotel banquet hall {area} {location} official website",
            f"hotel conference room {area} {location} official website",
            f"business hotel banquet conference {area} {location} official website",
        ],
    }


def discover_candidate_urls():
    grouped_urls = {
        "chain_hotels": [],
        "mid_size_hotels": [],
        "banquet_business_hotels": [],
    }

    seen = set()
    query_groups = build_search_query_groups()

    with DDGS() as ddgs:
        for group_name, queries in query_groups.items():
            for query in queries:
                print(f"\nSearching [{group_name}]: {query}")

                results = list(ddgs.text(
                    query,
                    max_results=max_search_results
                ))

                print(f"Raw results found: {len(results)}")

                for item in results:
                    url = item.get("href") or item.get("url") or item.get("link")

                    if not url:
                        continue

                    url = clean_url(url)

                    if url in seen:
                        continue

                    if is_bad_url(url):
                        continue

                    if not is_probably_relevant(url):
                        continue

                    print("Accepted:", url)
                    seen.add(url)
                    grouped_urls[group_name].append(url)

    return grouped_urls


# -----------------------------
# Scrape one URL with SmartScraperGraph
# -----------------------------

def build_hotel_extract_prompt(url: str) -> str:
    return f"""
Extract hotel information from this webpage only.

Target area:
{area}, {location}

Extra requirement:
{extra_info}

Extract:
- hotel_name
- location
- area
- chain_or_independent
- hotel_type
- website
- phone
- email
- rating
- review_summary
- room_types
- room_pricing
- facilities
- source_url

Rules:
- Use only information visible on this webpage.
- Do not guess.
- Do not create example hotels.
- If the page is not about a real hotel, return null fields.
- If a value is missing, use null or an empty list.
- source_url must be: {url}
- Keep the answer in English.
"""


def scrape_hotel_page(url: str):
    print(f"\nScraping: {url}")

    prompt = build_hotel_extract_prompt(url)

    graph = SmartScraperGraph(
        prompt=prompt,
        source=url,
        config=graph_config,
        schema=HotelInfo
    )

    return graph.run()

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

# -----------------------------
# Validate output
# -----------------------------

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
        "business hotel aerocity",
        "delhi business plaza",
        "aerocity business inn",
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

# -----------------------------
# Balance urls
# -----------------------------

def select_balanced_urls(grouped_urls):
    selected = []
    seen = set()

    limits = {
        "mid_size_hotels": 8,
        "chain_hotels": 3,
        "banquet_business_hotels": 3,
    }

    for group_name, limit in limits.items():
        urls = grouped_urls.get(group_name, [])

        # Sort best URLs first inside each bucket.
        urls = sorted(urls, key=score_url, reverse=True)

        count = 0

        for url in urls:
            if url in seen:
                continue

            if score_url(url) < 60:
                continue

            selected.append(url)
            seen.add(url)
            count += 1

            if count >= limit:
                break

    return selected


# -----------------------------
# Manager search
# -----------------------------

def build_manager_search_queries(hotel: dict) -> List[str]:
    hotel_name = hotel.get("hotel_name")
    hotel_location = hotel.get("location") or hotel.get("area") or f"{area}, {location}"

    if not hotel_name:
        return []

    queries = []

    for role in contact_roles:
        queries.append(f'"{hotel_name}" "{hotel_location}" "{role}" LinkedIn')
        queries.append(f'"{hotel_name}" "{hotel_location}" "{role}" email')
        queries.append(f'"{hotel_name}" "{role}" "{location}" LinkedIn')
        queries.append(f'"{hotel_name}" "{role}" "{location}" email')

    return queries

def is_contact_url_relevant(url: str) -> bool:
    url_lower = url.lower()

    if is_bad_url(url):
        return False

    useful_words = [
        "contact",
        "about",
        "team",
        "management",
        "manager",
        "staff",
        "hotel",
        "linkedin",
        "profile",
    ]

    return any(word in url_lower for word in useful_words)

def discover_contact_urls(hotel: dict) -> List[str]:
    urls = []
    seen = set()

    queries = build_manager_search_queries(hotel)

    with DDGS() as ddgs:
        for query in queries:
            print(f"\nContact search: {query}")

            results = list(ddgs.text(
                query,
                max_results=max_contact_search_results
            ))

            for item in results:
                url = item.get("href") or item.get("url") or item.get("link")

                if not url:
                    continue

                url = clean_url(url)

                if url in seen:
                    continue

                if not is_contact_url_relevant(url):
                    continue

                seen.add(url)
                urls.append(url)

                if len(urls) >= max_contact_pages_per_hotel:
                    return urls

    return urls

def build_contact_extract_prompt(hotel: dict, url: str) -> str:
    hotel_name = hotel.get("hotel_name")
    hotel_location = hotel.get("location") or hotel.get("area") or f"{area}, {location}"

    return f"""
Extract public manager or staff contact information from this webpage only.

Target hotel:
{hotel_name}

Target hotel location:
{hotel_location}

Target roles:
{contact_roles}

Extract:
- name
- role
- email
- linkedin_url
- profile_url
- source_url

Rules:
- Use only information visible on this webpage.
- Do not guess.
- Do not create fake people.
- Only include contacts connected to the target hotel.
- A valid contact must have name, role, and either email or LinkedIn/profile URL.
- If email is not visible, use null.
- If LinkedIn is visible, include it as linkedin_url.
- source_url must be: {url}
- Keep the answer in English.
"""

def scrape_contact_page(hotel: dict, url: str):
    print(f"\nScraping contact page: {url}")

    prompt = build_contact_extract_prompt(hotel, url)

    graph = SmartScraperGraph(
        prompt=prompt,
        source=url,
        config=graph_config,
        schema=ContactResults
    )

    return graph.run()

def normalize_contact_results(data, source_url: str) -> List[dict]:
    if isinstance(data, BaseModel):
        data = data.model_dump()

    if isinstance(data, dict) and "content" in data:
        data = data["content"]

    if isinstance(data, dict) and "contacts" in data:
        contacts = data["contacts"]
    elif isinstance(data, list):
        contacts = data
    else:
        contacts = []

    normalized_contacts = []

    for contact in contacts:
        if isinstance(contact, BaseModel):
            contact = contact.model_dump()

        if not isinstance(contact, dict):
            continue

        contact["source_url"] = contact.get("source_url") or source_url

        # If model puts LinkedIn into profile_url, copy it to linkedin_url
        profile_url = str(contact.get("profile_url") or "")
        if "linkedin.com" in profile_url and not contact.get("linkedin_url"):
            contact["linkedin_url"] = profile_url

        normalized_contacts.append(contact)

    return normalized_contacts

def is_valid_person_contact(contact: dict) -> bool:
    name = contact.get("name")
    role = contact.get("role")
    email = contact.get("email")
    linkedin_url = contact.get("linkedin_url")
    profile_url = contact.get("profile_url")

    if not name:
        return False

    if not role:
        return False

    if not email and not linkedin_url and not profile_url:
        return False

    return True

def enrich_hotel_with_contacts(hotel: dict) -> dict:
    print(f"\n================ Contact enrichment for: {hotel.get('hotel_name')} ================")

    contact_urls = discover_contact_urls(hotel)

    print("\nCandidate contact URLs:")
    for url in contact_urls:
        print(url)

    contacts = []

    for url in contact_urls:
        try:
            result = scrape_contact_page(hotel, url)
            found_contacts = normalize_contact_results(result, url)

            for contact in found_contacts:
                if is_valid_person_contact(contact):
                    contacts.append(contact)

        except Exception as e:
            print("Failed contact scrape:", url)
            print("Error:", e)

    hotel["manager_contacts"] = contacts

    return hotel

# -----------------------------
# 9. Main flow
# -----------------------------

def main():
    grouped_urls = discover_candidate_urls()
    candidate_urls = select_balanced_urls(grouped_urls)

    print("\n---------------- Balanced Candidate URLs ----------------")
    for url in candidate_urls:
        print(url)

    final_hotels = []

    for url in candidate_urls[:max_pages_to_try]:
        if len(final_hotels) >= target_hotels:  
            break

        try:
            result = scrape_hotel_page(url)
            data = unwrap_result(result)

            if isinstance(data, BaseModel):
                data = data.model_dump()

            data = normalize_hotel_record(data, url)

            if is_valid_hotel_record(data):
                final_hotels.append(data)
                print("Accepted hotel:", data.get("hotel_name"))
            else:
                print("Rejected result from:", url)
                print(data)

        except Exception as e:
            print("Failed to scrape:", url)
            print("Error:", e)

    print("\n---------------- Final Hotels ----------------")
    print(final_hotels)

    print("\n---------------- Balanced Candidate URLs ----------------")
    for url in candidate_urls:
        print(score_url(url), classify_url(url), url)

    enriched_hotels = []

    for hotel in final_hotels:
        enriched_hotel = enrich_hotel_with_contacts(hotel)
        enriched_hotels.append(enriched_hotel)

    print("\n---------------- Enriched Hotels With Manager Contacts ----------------")
    print(enriched_hotels)


if __name__ == "__main__":
    main()