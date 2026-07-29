from ddgs import DDGS  # type: ignore

from config import (
    area,
    location,
    hotel_type,
    extra_info,
    max_search_results,
    nearby_area_terms,
)
from url_utils import clean_url, is_bad_url, is_probably_relevant

# These are patched by pipeline.apply_runtime_settings at run time.
complete_search = False
search_name = ""


def clean_term(value: str) -> str:
    return str(value or "").strip()


def unique_values(values: list[str]) -> list[str]:
    clean_values = []
    seen = set()

    for value in values:
        value = clean_term(value)

        if not value:
            continue

        key = value.lower()

        if key in seen:
            continue

        seen.add(key)
        clean_values.append(value)

    return clean_values


def get_search_areas() -> list[str]:
    """
    Complete search uses the target area plus nearby terms.
    Partial search stays tighter so the result list is easier to control.
    """
    if complete_search:
        return unique_values([area, *nearby_area_terms])

    return unique_values([area])


def get_hotel_type_terms() -> list[str]:
    selected_type = clean_term(hotel_type).lower()

    if not selected_type or selected_type in {"hotel", "all hotels", "all hotel types"}:
        return [
            "hotel",
            "business hotel",
            "independent hotel",
            "boutique hotel",
            "budget hotel",
            "luxury hotel",
            "hotel with banquet facilities",
            "hotel with conference facilities",
        ]

    return unique_values([
        hotel_type,
        "hotel",
        extra_info,
    ])


def build_search_query_groups():
    search_areas = get_search_areas()
    type_terms = get_hotel_type_terms()

    query_groups = {
        "official_area_hotels": [],
        "independent_mid_size_hotels": [],
        "chain_hotels": [],
        "banquet_business_hotels": [],
        "general_area_hotels": [],
    }

    for search_area in search_areas:
        for type_term in type_terms:
            query_groups["official_area_hotels"].extend([
                f'official website "{type_term}" "{search_area}" "{location}"',
                f'"{search_area}" "{location}" "{type_term}" hotel official website',
            ])

        query_groups["independent_mid_size_hotels"].extend([
            f'independent hotel "{search_area}" "{location}" official website',
            f'mid size hotel "{search_area}" "{location}" official website',
            f'boutique hotel "{search_area}" "{location}" official website',
            f'3 star hotel "{search_area}" "{location}" official website',
            f'4 star hotel "{search_area}" "{location}" official website',
        ])

        query_groups["banquet_business_hotels"].extend([
            f'hotel banquet hall "{search_area}" "{location}" official website',
            f'hotel conference room "{search_area}" "{location}" official website',
            f'business hotel banquet conference "{search_area}" "{location}" official website',
        ])

        query_groups["general_area_hotels"].extend([
            f'"{search_area}" "{location}" hotels official websites',
            f'all hotels in "{search_area}" "{location}"',
            f'best hotels "{search_area}" "{location}" official site',
        ])

    # Chain searches stay useful, but should not dominate selection.
    query_groups["chain_hotels"].extend([
        f'site:marriott.com "{area}" "{location}" hotel',
        f'site:ihg.com "{area}" "{location}" hotel',
        f'site:hyatt.com "{area}" "{location}" hotel',
        f'site:accor.com "{area}" "{location}" hotel',
        f'site:hilton.com "{area}" "{location}" hotel',
        f'site:radissonhotels.com "{area}" "{location}" hotel',
    ])

    if not complete_search:
        # Keep partial search smaller and predictable.
        return {
            "chain_hotels": query_groups["chain_hotels"],
            "mid_size_hotels": query_groups["independent_mid_size_hotels"][:6],
            "banquet_business_hotels": query_groups["banquet_business_hotels"][:4],
        }

    return {
        key: unique_values(values)
        for key, values in query_groups.items()
        if values
    }


def discover_candidate_urls():
    query_groups = build_search_query_groups()
    grouped_urls = {group_name: [] for group_name in query_groups}

    seen = set()
    no_new_searches = 0

    with DDGS() as ddgs:
        for group_name, queries in query_groups.items():
            for query in queries:
                print(f"\nSearching [{group_name}]: {query}")

                try:
                    results = list(ddgs.text(
                        query,
                        max_results=max_search_results,
                    ))
                except Exception as error:
                    print(f"Search skipped: {type(error).__name__}: {error}")
                    continue

                print(f"Raw results found: {len(results)}")
                new_urls_this_search = 0

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
                    new_urls_this_search += 1

                if new_urls_this_search == 0:
                    no_new_searches += 1
                else:
                    no_new_searches = 0

                # Complete search should keep going, but not waste time forever.
                if complete_search and no_new_searches >= 8:
                    print("Stopping discovery because several searches found no new URLs.")
                    return grouped_urls

    return grouped_urls
