import re
from typing import List, Optional

from ddgs import DDGS  # type: ignore
from pydantic import BaseModel
from scrapegraphai.graphs import SmartScraperGraph

from config import (
    area,
    location,
    nearby_area_terms,
    excluded_location_terms,
    contact_roles,
    max_contact_search_results,
    max_contact_pages_per_hotel,
    graph_config,
)

from schema import ContactResults
from url_utils import clean_url, is_bad_url, get_domain


# -----------------------------
# Text helpers
# -----------------------------

def normalize_text(value: str) -> str:
    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return " ".join(value.split())


def add_unique_alias(aliases: List[dict], alias: str, weight: int):
    alias = normalize_text(alias)

    if not alias:
        return

    if len(alias) <= 3:
        return

    for item in aliases:
        if item["alias"] == alias:
            return

    aliases.append({
        "alias": alias,
        "weight": weight,
    })


# -----------------------------
# Hotel and location matching
# -----------------------------

def build_hotel_aliases(hotel: dict) -> List[dict]:
    hotel_name = normalize_text(hotel.get("hotel_name"))

    aliases = []

    if not hotel_name:
        return aliases

    add_unique_alias(aliases, hotel_name, 35)

    words = hotel_name.split()

    # Example:
    # "pride plaza hotel aerocity new delhi"
    # -> "pride plaza hotel aerocity"
    without_city_words = [
        word for word in words
        if word not in {"new", "delhi"}
    ]

    if len(without_city_words) >= 2:
        add_unique_alias(aliases, " ".join(without_city_words), 28)

    # Example:
    # "pride plaza hotel aerocity"
    # -> "pride plaza aerocity"
    without_generic_hotel_words = [
        word for word in without_city_words
        if word not in {"hotel", "hotels", "the"}
    ]

    if len(without_generic_hotel_words) >= 2:
        add_unique_alias(aliases, " ".join(without_generic_hotel_words), 25)

    # Stronger short property name.
    # Example:
    # "pride plaza"
    property_words = [
        word for word in words
        if word not in {
            "hotel",
            "hotels",
            "the",
            "new",
            "delhi",
            "aerocity",
            "airport",
            "inn",
            "suites",
            "resort",
        }
    ]

    if len(property_words) >= 2:
        add_unique_alias(aliases, " ".join(property_words[:2]), 20)

    # Add area-combined version if useful.
    if property_words and area:
        add_unique_alias(
            aliases,
            f"{' '.join(property_words[:2])} {area}",
            28
        )

    return aliases


def build_location_aliases(hotel: dict) -> List[str]:
    values = [
        hotel.get("location"),
        hotel.get("area"),
        area,
        location,
    ]

    values.extend(nearby_area_terms)

    aliases = []

    for value in values:
        text = normalize_text(value)

        if not text:
            continue

        aliases.append(text)

    known_terms = [
        "aerocity",
        "new delhi",
        "delhi",
        "hospitality district",
        "igi",
        "igi airport",
        "rangpuri",
        "mahipalpur",
    ]

    aliases.extend(known_terms)

    clean_aliases = []

    for alias in aliases:
        alias = normalize_text(alias)

        if alias and alias not in clean_aliases:
            clean_aliases.append(alias)

    return clean_aliases


# -----------------------------
# Search query building
# -----------------------------

def build_manager_search_queries(hotel: dict) -> List[str]:
    hotel_name = hotel.get("hotel_name")
    hotel_area = hotel.get("area") or f"{area}, {location}"

    if not hotel_name:
        return []

    website = hotel.get("website") or hotel.get("source_url") or ""
    hotel_domain = get_domain(str(website))

    queries = []

    for role in contact_roles:
        # LinkedIn person profiles.
        queries.append(
            f'site:linkedin.com/in "{hotel_name}" "{role}"'
        )

        queries.append(
            f'site:linkedin.com/in "{hotel_name}" "{hotel_area}" "{role}"'
        )

        # LinkedIn/post evidence.
        queries.append(
            f'"{hotel_name}" "{hotel_area}" "{role}" LinkedIn'
        )

        queries.append(
            f'"{hotel_name}" "{role}" joined appointed promoted'
        )

        # General web/email evidence.
        queries.append(
            f'"{hotel_name}" "{role}" email'
        )

        # Official website search.
        if hotel_domain:
            queries.append(
                f'site:{hotel_domain} "{role}"'
            )

            queries.append(
                f'site:{hotel_domain} management team contact'
            )

    return queries


# -----------------------------
# Candidate classification and scoring
# -----------------------------

def classify_contact_source(url: str, title: str, body: str) -> str:
    text = f"{url} {title} {body}".lower()

    if "linkedin.com/in/" in text:
        return "linkedin_person_profile"

    if "linkedin.com/posts/" in text or "linkedin.com/feed/" in text:
        if any(word in text for word in ["joined", "appointed", "promoted"]):
            return "recent_joining_post"

        if any(word in text for word in ["career", "hiring", "vacancy", "job", "apply"]):
            return "career_post"

        return "linkedin_post"

    if "linkedin.com/company/" in text:
        return "company_page"
    
    if any(site in text for site in ["zoominfo.com", "rocketreach.co", "lusha.com", "apollo.io"]):
        return "lead_database"

    if any(word in text for word in ["appoints", "appointed", "promoted as", "joins as", "joined as"]):
        return "news_or_interview"

    directory_words = [
        "booking",
        "tripadvisor",
        "makemytrip",
        "goibibo",
        "agoda",
        "expedia",
        "trivago",
        "ixigo",
        "wedding",
        "venue",
        "banquet booking",
    ]

    if any(word in text for word in directory_words):
        return "directory_page"

    if any(word in text for word in ["news", "interview", "appointment", "appointed"]):
        return "news_or_interview"

    if any(word in text for word in ["team", "leadership", "management"]):
        return "official_team_page"

    if any(word in text for word in ["contact", "contact-us", "contact us"]):
        return "official_contact_page"

    return "unknown"


ROLE_TIERS = {
    "tier_1": [
    "general manager",
    "area general manager",
    "regional general manager",
    "hotel manager",
    "owner",
    "director of operations",
    "vice president",
    "vp",
    ],
    "tier_2": [
        "operations manager",
        "hotel operations manager",
        "housekeeping manager",
        "procurement manager",
        "purchase manager",
        "front office manager",
        "director of engineering",
        "engineering director",
        "facilities manager",
    ],
    "tier_3": [
        "sales manager",
        "hr manager",
        "human resources",
        "guest relations manager",
        "assistant manager",
        "it manager",
    ],
}


def find_target_role(text: str) -> str | None:
    text = normalize_text(text)
    padded_text = f" {text} "

    for roles in ROLE_TIERS.values():
        for role in roles:
            clean_role = normalize_text(role)

            if f" {clean_role} " in padded_text:
                return role

    return None

def get_role_tier(role: str | None) -> str | None:
    if not role:
        return None

    clean_role = normalize_text(role)

    for tier_name, roles in ROLE_TIERS.items():
        for tier_role in roles:
            if normalize_text(tier_role) == clean_role:
                return tier_name

    return None

def has_historical_signal(candidate: dict) -> bool:
    reasons = candidate.get("reasons") or []

    return any(
        "Historical/old signal" in reason
        for reason in reasons
    )

def is_bad_contact_source(url: str, title: str, body: str) -> bool:
    text = f"{url} {title} {body}".lower()

    bad_markers = [
        "bing.com/aclick",
        "googleadservices",
        "doubleclick",
        "online-reservations.com",
        "tripadvisor",
        "booking.com",
        "makemytrip",
        "goibibo",
        "agoda",
        "expedia",
        "trivago",
        "ixigo",
    ]

    return any(marker in text for marker in bad_markers)

def get_role_score(role: Optional[str], source: str) -> tuple[int, str]:
    if not role:
        return 0, "No target role found"

    role_tier = get_role_tier(role)

    if source == "title":
        if role_tier == "tier_1":
            return 30, f"Tier 1 role matched in title: {role}"
        if role_tier == "tier_2":
            return 22, f"Tier 2 role matched in title: {role}"
        return 12, f"Tier 3 role matched in title: {role}"

    if role_tier == "tier_1":
        return 15, f"Tier 1 role matched in body/snippet: {role}"
    if role_tier == "tier_2":
        return 10, f"Tier 2 role matched in body/snippet: {role}"
    return 5, f"Tier 3 role matched in body/snippet: {role}"

SOURCE_SCORES = {
    "linkedin_person_profile": 25,
    "official_team_page": 20,
    "official_contact_page": 15,
    "news_or_interview": 15,
    "recent_joining_post": 12,
    "linkedin_post": 5,
    "career_post": -5,
    "company_page": 0,
    "directory_page": -35,
    "lead_database": -20,
    "unknown": 0,
}

CURRENT_SIGNALS = [
    "present",
    "currently",
    "current capacity",
    "works at",
    "working at",
    "2024",
    "2025",
    "2026",
]

HISTORICAL_SIGNALS = [
    "former",
    "ex ",
    "previously",
    "worked at",
    "10 years ago",
    "11 years ago",
    "2014",
    "2015",
    "2016",
    "2017",
    "2018",
    "2019",
    "2020",
    "2021",
    "2022",
    "2023",
    "pre opening",
    "pre-opening",
]

LOW_VALUE_SIGNALS = [
    "certificate of completion",
    "booking",
    "tripadvisor",
    "makemytrip",
    "goibibo",
    "agoda",
    "expedia",
    "ixigo",
    "wedding package",
    "banquet booking",
]


def contains_phrase(text: str, phrase: str) -> bool:
    clean_phrase = normalize_text(phrase)

    if not clean_phrase:
        return False

    return f" {clean_phrase} " in f" {text} "


def get_confidence_and_action(score: int) -> tuple[str, str]:
    if score >= 75:
        return "high", "use_or_scrape"

    if score >= 50:
        return "medium", "review_or_scrape_if_needed"

    if score >= 30:
        return "weak_lead", "store_as_weak_lead"

    return "reject", "reject"


def make_contact_candidate(url: str, title: str, body: str, query: str) -> dict:
    return {
        "url": url,
        "title": title,
        "body": body,
        "query": query,
        "score": 0,
        "evidence_type": "unknown",
        "confidence": "reject",
        "action": "reject",
        "matched_role": None,
        "title_role": None,
        "body_role": None,
        "reasons": [],
    }


def reject_candidate(candidate: dict, reason: str) -> dict:
    candidate["reasons"].append(reason)
    return candidate

def score_contact_result(item: dict, hotel: dict, query: str = "") -> dict:
    url = clean_url(item.get("href") or item.get("url") or item.get("link") or "")
    title = str(item.get("title") or "")
    body = str(item.get("body") or "")

    candidate = make_contact_candidate(url, title, body, query)

    if not url:
        return reject_candidate(candidate, "Missing URL")

    if is_bad_contact_source(url, title, body):
        return reject_candidate(candidate, "Bad contact source/ad/directory")

    if is_bad_url(url):
        return reject_candidate(candidate, "Blocked by bad URL filter")

    text = normalize_text(f"{url} {title} {body}")
    score = 0
    reasons = []

    evidence_type = classify_contact_source(url, title, body)
    candidate["evidence_type"] = evidence_type

    # -----------------------------
    # Official domain check
    # -----------------------------

    website = hotel.get("website") or hotel.get("source_url") or ""
    official_domain = get_domain(str(website))
    result_domain = get_domain(url)

    is_official_domain = bool(
        official_domain
        and result_domain
        and official_domain == result_domain
    )

    # -----------------------------
    # Hotel/property match
    # -----------------------------

    hotel_aliases = build_hotel_aliases(hotel)

    matched_aliases = [
        alias_item
        for alias_item in hotel_aliases
        if contains_phrase(text, alias_item["alias"])
    ]

    best_alias_weight = 0

    if matched_aliases:
        best_alias = max(matched_aliases, key=lambda alias_item: alias_item["weight"])
        best_alias_weight = best_alias["weight"]

        score += best_alias_weight
        reasons.append(f"Hotel alias matched: {best_alias['alias']}")

    elif is_official_domain:
        score += 15
        reasons.append("Official hotel domain matched")

    else:
        return reject_candidate(candidate, "No hotel/property match")

    # -----------------------------
    # Target location match
    # Generic replacement for wrong_locations
    # -----------------------------

    location_aliases = build_location_aliases(hotel)

    matched_locations = [
        location_alias
        for location_alias in location_aliases
        if contains_phrase(text, location_alias)
    ]

    has_target_location = bool(matched_locations)

    if has_target_location:
        score += 20
        reasons.append(f"Location matched: {matched_locations[:2]}")
    else:
        reasons.append("No target location match")

        if not is_official_domain and best_alias_weight < 28:
            score -= 15
            reasons.append("Weak hotel match without target location")

    # -----------------------------
    # Role match
    # -----------------------------

    title_role = find_target_role(title)
    body_role = find_target_role(body)
    matched_role = title_role or body_role

    candidate["title_role"] = title_role
    candidate["body_role"] = body_role
    candidate["matched_role"] = matched_role

    if title_role:
        role_score, role_reason = get_role_score(title_role, "title")
        score += role_score
        reasons.append(role_reason)

    elif body_role:
        role_score, role_reason = get_role_score(body_role, "body")
        score += role_score
        reasons.append(role_reason)

    else:
        reasons.append("No target role found")

    # -----------------------------
    # Source type score
    # -----------------------------

    score += SOURCE_SCORES.get(evidence_type, 0)
    reasons.append(f"Evidence type: {evidence_type}")

    # -----------------------------
    # Current / historical signals
    # -----------------------------

    if any(contains_phrase(text, signal) for signal in CURRENT_SIGNALS):
        score += 15
        reasons.append("Current/recent signal found")

    if any(contains_phrase(text, signal) for signal in HISTORICAL_SIGNALS):
        score -= 25
        reasons.append("Historical/old signal found")

    # -----------------------------
    # Low-value signals
    # -----------------------------

    if any(contains_phrase(text, signal) for signal in LOW_VALUE_SIGNALS):
        score -= 25
        reasons.append("Bad low-value source signal")

    # -----------------------------
    # Caps / guardrails
    # -----------------------------

    if evidence_type == "linkedin_person_profile" and not matched_role:
        score = min(score, 45)
        reasons.append("LinkedIn profile capped because no target role matched")

    if evidence_type == "linkedin_person_profile" and not title_role and body_role:
        score = min(score, 65)
        reasons.append("LinkedIn profile capped because role only appeared in snippet")

    if evidence_type == "career_post":
        score = min(score, 45)
        reasons.append("Career post capped as weak lead")

    if evidence_type == "lead_database":
        score = min(score, 45)
        reasons.append("Lead database capped as weak/medium lead")

    if not matched_role:
        score = min(score, 45)
        reasons.append("Candidate capped because no target role matched")

    if not is_official_domain and not has_target_location and best_alias_weight < 35:
        score = min(score, 55)
        reasons.append("Candidate capped because target location was not found")

    # -----------------------------
    # Final result
    # -----------------------------

    confidence, action = get_confidence_and_action(score)

    candidate["score"] = score
    candidate["confidence"] = confidence
    candidate["action"] = action
    candidate["reasons"] = reasons

    return candidate

def discover_contact_candidates(hotel: dict) -> List[dict]:
    candidates = []
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
                url = clean_url(item.get("href") or item.get("url") or item.get("link") or "")

                if not url:
                    continue

                if url in seen:
                    continue

                seen.add(url)

                candidate = score_contact_result(item, hotel, query)
                candidates.append(candidate)

                print(
                    candidate["score"],
                    candidate["confidence"],
                    candidate["evidence_type"],
                    candidate["url"]
                )

    candidates = sorted(
        candidates,
        key=lambda item: item["score"],
        reverse=True
    )

    return candidates


# -----------------------------
# Direct extraction from search metadata
# -----------------------------

def clean_search_title(title: str) -> str:
    title = title.replace("| LinkedIn", "")
    title = title.split("...")[0]
    title = title.split(" - LinkedIn")[0]
    return title.strip()


def format_role(role: str) -> str:
    return " ".join(word.capitalize() for word in role.split())


def contact_from_linkedin_search_result(candidate: dict) -> Optional[dict]:
    url = candidate.get("url") or ""
    title = candidate.get("title") or ""

    if "linkedin.com/in/" not in url.lower():
        return None

    matched_role = candidate.get("matched_role")
    role_tier = get_role_tier(matched_role)

    if not matched_role:
        return None

    # Only Tier 1 and Tier 2 become confirmed contacts from LinkedIn.
    # Tier 3 stays as a lead.
    if role_tier not in ["tier_1", "tier_2"]:
        return None

    # Require strong score.
    if candidate.get("score", 0) < 75:
        return None

    # Historical LinkedIn evidence should be a lead, not confirmed.
    if has_historical_signal(candidate):
        return None

    # If there is a wrong city/property warning, do not confirm directly.
    reasons = candidate.get("reasons") or []
    if any("Possible wrong city/property" in reason for reason in reasons):
        return None

    clean_title = clean_search_title(title)

    parts = [
        part.strip()
        for part in clean_title.split("-")
        if part.strip()
    ]

    if len(parts) < 2:
        return None

    name = parts[0].strip()

    if not name:
        return None

    return {
        "name": name,
        "role": format_role(matched_role),
        "email": None,
        "linkedin_url": url,
        "profile_url": url,
        "source_url": url,
        "confidence": candidate.get("confidence"),
        "evidence_type": candidate.get("evidence_type"),
        "evidence_reasons": candidate.get("reasons"),
    }

def get_candidates_to_scrape(candidates: List[dict]) -> List[dict]:
    scrape_candidates = []

    for candidate in candidates:
        url = str(candidate.get("url") or "").lower()

        if candidate.get("score", 0) < 70:
            continue

        if "linkedin.com" in url:
            continue

        if candidate.get("evidence_type") in [
            "lead_database",
            "directory_page",
            "career_post",
            "company_page",
            "news_or_interview",
            "recent_joining_post",
        ]:
            continue

        if candidate.get("evidence_type") in [
            "official_team_page",
            "official_contact_page",
        ]:
            scrape_candidates.append(candidate)

    return scrape_candidates[:max_contact_pages_per_hotel]


# -----------------------------
# AI scrape for selected pages only
# -----------------------------

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

        profile_url = str(contact.get("profile_url") or "")
        if "linkedin.com" in profile_url and not contact.get("linkedin_url"):
            contact["linkedin_url"] = profile_url

        normalized_contacts.append(contact)

    return normalized_contacts


def is_valid_person_contact(contact: dict) -> bool:
    name = contact.get("name")
    role = contact.get("role")
    email = contact.get("email")
    linkedin_url = str(contact.get("linkedin_url") or "")
    profile_url = str(contact.get("profile_url") or "")

    if not name:
        return False

    if not role:
        return False

    # Reject LinkedIn share/company URLs as person contacts.
    if linkedin_url:
        if "linkedin.com/share" in linkedin_url.lower():
            return False

        if "linkedin.com/company" in linkedin_url.lower():
            return False

    if not email and not linkedin_url and not profile_url:
        return False

    return True

def contact_from_evidence_result(candidate: dict) -> Optional[dict]:
    evidence_type = candidate.get("evidence_type")
    title = candidate.get("title") or ""
    body = candidate.get("body") or ""
    url = candidate.get("url") or ""

    if evidence_type not in ["news_or_interview", "recent_joining_post"]:
        return None

    if candidate.get("score", 0) < 70:
        return None

    if has_historical_signal(candidate):
        return None

    role = candidate.get("matched_role") or find_target_role(f"{title} {body}")

    if not role:
        return None

    role_tier = get_role_tier(role)

    if role_tier not in ["tier_1", "tier_2"]:
        return None

    text = f"{title} {body}"

    patterns = [
        r"appoints\s+(?:mr\.?\s+|mrs\.?\s+|ms\.?\s+)?([A-Z][A-Za-z\s\.]+?)\s+as\s+",
        r"appointed\s+(?:mr\.?\s+|mrs\.?\s+|ms\.?\s+)?([A-Z][A-Za-z\s\.]+?)\s+as\s+",
        r"promotes\s+(?:mr\.?\s+|mrs\.?\s+|ms\.?\s+)?([A-Z][A-Za-z\s\.]+?)\s+as\s+",
        r"promoted\s+(?:mr\.?\s+|mrs\.?\s+|ms\.?\s+)?([A-Z][A-Za-z\s\.]+?)\s+as\s+",
        r"([A-Z][A-Za-z\s\.]+?)\s+appointed\s+new\s+",
        r"([A-Z][A-Za-z\s\.]+?)\s+appointed\s+as\s+",
    ]

    name = None

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            name = match.group(1).strip()
            break

    if not name:
        return None

    name = " ".join(name.split())

    return {
        "name": name,
        "role": format_role(role),
        "email": None,
        "linkedin_url": url if "linkedin.com" in url.lower() else None,
        "profile_url": url,
        "source_url": url,
        "confidence": candidate.get("confidence"),
        "evidence_type": candidate.get("evidence_type"),
        "evidence_reasons": candidate.get("reasons"),
    }


def extract_contacts_from_candidates(candidates: List[dict]) -> List[dict]:
    contacts = []

    extractors = [
        contact_from_linkedin_search_result,
        contact_from_evidence_result,
    ]

    for candidate in candidates:
        for extractor in extractors:
            contact = extractor(candidate)

            if contact and is_valid_person_contact(contact):
                contacts.append(contact)

    return contacts

def scrape_contacts_from_candidates(hotel: dict, candidates: List[dict]) -> List[dict]:
    contacts = []
    scrape_candidates = get_candidates_to_scrape(candidates)

    print("\nScrape candidates:")
    for candidate in scrape_candidates:
        print(candidate["score"], candidate["evidence_type"], candidate["url"])

    for candidate in scrape_candidates:
        url = candidate["url"]

        try:
            result = scrape_contact_page(hotel, url)
            found_contacts = normalize_contact_results(result, url)

            for contact in found_contacts:
                if is_valid_person_contact(contact):
                    contact["confidence"] = candidate.get("confidence")
                    contact["evidence_type"] = candidate.get("evidence_type")
                    contact["evidence_reasons"] = candidate.get("reasons")
                    contacts.append(contact)

        except Exception as error:
            print("Failed contact scrape:", url)
            print("Error:", error)

    return contacts

def get_contact_leads(candidates: List[dict]) -> List[dict]:
    return [
        candidate
        for candidate in candidates
        if candidate.get("confidence") in ["weak_lead", "medium"]
    ]

def enrich_hotel_with_contacts(hotel: dict) -> dict:
    print(f"\n================ Contact enrichment for: {hotel.get('hotel_name')} ================")

    candidates = discover_contact_candidates(hotel)

    print("\nTop contact candidates:")
    for candidate in candidates[:10]:
        print(
            candidate["score"],
            candidate["confidence"],
            candidate["evidence_type"],
            candidate["url"],
        )
        print("Reasons:", candidate["reasons"])

    metadata_contacts = extract_contacts_from_candidates(candidates)
    scraped_contacts = scrape_contacts_from_candidates(hotel, candidates)

    contacts = metadata_contacts + scraped_contacts

    hotel["manager_contacts"] = dedupe_contacts(contacts)
    hotel["contact_leads"] = get_contact_leads(candidates)
    hotel["contact_debug_candidates"] = candidates[:20]

    return hotel


def dedupe_contacts(contacts: List[dict]) -> List[dict]:
    seen = set()
    unique_contacts = []

    for contact in contacts:
        key = (
            normalize_text(contact.get("name")),
            normalize_text(contact.get("role")),
            normalize_text(contact.get("linkedin_url") or contact.get("profile_url") or ""),
        )

        if key in seen:
            continue

        seen.add(key)
        unique_contacts.append(contact)

    return unique_contacts

