from ddgs import DDGS  # type: ignore
from config import area, location, max_search_results
from url_utils import clean_url, is_bad_url, is_probably_relevant

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
            f"business hotel near {location} {area} official website",

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