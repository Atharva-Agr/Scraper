from pydantic import BaseModel

from config import (
    RUN_PHASE_1,
    RUN_PHASE_2,
    USE_CACHED_HOTELS,
    HOTEL_CACHE_FILE,
    max_pages_to_try,
    target_hotels,
)

from discovery import discover_candidate_urls
from url_utils import select_balanced_urls, score_url, classify_url
from hotel_scraper import scrape_hotel_page
from validation import unwrap_result, normalize_hotel_record, is_valid_hotel_record, dedupe_hotels
from contacts import enrich_hotel_with_contacts
from cache_utils import save_hotels_to_cache, load_hotels_from_cache # type: ignore


def run_phase_1_hotels():
    grouped_urls = discover_candidate_urls()
    candidate_urls = select_balanced_urls(grouped_urls)

    print("\n---------------- Balanced Candidate URLs ----------------")
    for url in candidate_urls:
        print(score_url(url), classify_url(url), url)

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

        except Exception as error:
            print("Failed to scrape:", url)
            print("Error:", error)

    return final_hotels


def run_phase_2_contacts(final_hotels):
    enriched_hotels = []

    for hotel in final_hotels[:1]:
        enriched_hotel = enrich_hotel_with_contacts(hotel)
        enriched_hotels.append(enriched_hotel)

    return enriched_hotels


def main():
    final_hotels = []

    if USE_CACHED_HOTELS:
        print("Loading hotels from cache...")
        final_hotels = load_hotels_from_cache(HOTEL_CACHE_FILE)

    elif RUN_PHASE_1:
        print("Running Phase 1: Hotel scraping...")
        final_hotels = run_phase_1_hotels()
        final_hotels = dedupe_hotels(final_hotels)

        print("Saving hotels to cache...")
        save_hotels_to_cache(final_hotels, HOTEL_CACHE_FILE)

    else:
        print("Phase 1 is off and cache loading is off.")
        print("No hotels available to process.")

    if RUN_PHASE_2:
        print("Running Phase 2: Contact enrichment...")

        enriched_hotels = run_phase_2_contacts(final_hotels)

        print("\n---------------- Enriched Hotels ----------------")
        print(enriched_hotels)

    else:
        print("\n---------------- Final Hotels ----------------")
        print(final_hotels)


if __name__ == "__main__":
    main()


# Ideas:
# add check if exact hotel exists