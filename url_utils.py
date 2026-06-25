from urllib.parse import urlparse
from config import area, location

BAD_DOMAINS = [
    #################----------------------------- could get user to add
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

