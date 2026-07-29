from urllib.parse import urlparse
from config import area, location, nearby_area_terms
import re

BAD_DOMAINS = [
    "facebook",
    "instagram",
    "youtube",
    "twitter",
    "x.com",
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
    "slideserve",
    "slideshare",
    "powerpoint",
    "ppt-presentation",
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

SOFT_BAD_DOMAIN_PATTERNS = [
    r"^hotels?-[a-z0-9-]+\.(com|net)$",
    r"^hotel[a-z0-9-]+\.net$",
]


def get_domain(url: str) -> str:
    return urlparse(str(url or "")).netloc.lower().replace("www.", "")


def is_likely_hotel_mirror_domain(url: str) -> bool:
    domain = get_domain(url)

    if not domain:
        return False

    return any(
        re.match(pattern, domain)
        for pattern in SOFT_BAD_DOMAIN_PATTERNS
    )


def has_bad_extension(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in BAD_EXTENSIONS)


def is_bad_url(url: str) -> bool:
    url_lower = str(url or "").lower()
    domain = get_domain(url)

    if not url_lower.startswith(("http://", "https://")):
        return True

    if any(bad in url_lower for bad in BAD_DOMAINS):
        return True

    if has_bad_extension(url):
        return True

    if domain.endswith(".cn"):
        return True

    return False


def is_probably_relevant(url: str) -> bool:
    url_lower = str(url or "").lower()

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
    return str(url or "").strip()


def classify_url(url: str) -> str:
    url_lower = str(url or "").lower()
    domain = get_domain(url)

    chain_words = [
        "marriott", "hyatt", "ihg", "accor", "radisson",
        "hilton", "sheraton", "novotel", "pullman", "ibis",
        "holidayinn", "lemontree", "wyndham", "millennium",
        "fourseasons", "shangri", "mandarinoriental",
    ]

    directory_words = [
        "venue", "banquet", "wedding", "travel", "tour",
        "guide", "booking", "trip", "qantas", "rooms.com",
        "hotels-of", "hotels-in", "tophotel", "ihotel"
    ]

    hotel_words = [
        "hotel", "inn", "suites", "resort", "stay",
        "plaza", "palace", "hospitality", "motel", "lodge"
    ]

    if any(word in domain or word in url_lower for word in directory_words):
        return "directory"

    if any(word in domain for word in chain_words):
        return "chain"

    if any(word in domain for word in hotel_words):
        return "direct_hotel_site"

    return "unknown"


def score_url(url: str) -> int:
    url_lower = str(url or "").lower()

    if is_bad_url(url):
        return -9999

    source_type = classify_url(url)
    score = 0

    if source_type == "direct_hotel_site":
        score += 100
    elif source_type == "chain":
        score += 75
    elif source_type == "directory":
        score += 15
    else:
        score += 10

    location_terms = [
        area.lower(),
        location.lower(),
        *[str(term or "").lower() for term in nearby_area_terms],
    ]

    for term in location_terms:
        if term and term in url_lower:
            score += 15

    good_paths = [
        "contact", "contact-us", "overview", "hotel",
        "rooms", "meeting", "meetings", "events", "facilities",
        "accommodation", "about",
    ]

    for path in good_paths:
        if path in url_lower:
            score += 8

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
            score -= 15

    path = urlparse(str(url or "")).path.strip("/")
    if path == "":
        score -= 15

    if is_likely_hotel_mirror_domain(url):
        score -= 50

    return score


# -----------------------------
# Balance urls
# -----------------------------

def select_balanced_urls(grouped_urls, complete_search: bool = False, target_count: int | None = None):
    selected = []
    seen = set()

    if complete_search:
        all_urls = []

        for group_name, urls in (grouped_urls or {}).items():
            for url in urls:
                if url in seen:
                    continue

                seen.add(url)
                all_urls.append((group_name, url, score_url(url)))

        # Complete search should include more high-confidence sources, not only
        # the small balanced sample used for partial searches.
        all_urls = [item for item in all_urls if item[2] >= 25]
        all_urls = sorted(all_urls, key=lambda item: item[2], reverse=True)

        if target_count is None:
            target_count = len(all_urls)

        # Try enough URLs to approach the estimate, while leaving room for failed scrapes.
        limit = max(target_count * 2, target_count + 20)

        return [url for _, url, _ in all_urls[:limit]]

    limits = {
        "mid_size_hotels": 8,
        "independent_mid_size_hotels": 8,
        "official_area_hotels": 8,
        "chain_hotels": 3,
        "banquet_business_hotels": 3,
        "general_area_hotels": 3,
    }

    for group_name, limit in limits.items():
        urls = (grouped_urls or {}).get(group_name, [])
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
