import config

from pipeline import (
    load_cache,
    print_hotel_summary,
    run_contact_enrichment,
    run_hotel_discovery,
)


def main():
    settings = config.configure_from_cli()

    final_hotels = []

    if config.USE_CACHED_HOTELS:
        print("Loading hotels from cache...")
        final_hotels = load_cache(config.HOTEL_CACHE_FILE)

    elif config.RUN_PHASE_1:
        print("Running Phase 1: Hotel scraping...")

        final_hotels = run_hotel_discovery(
            settings=settings,
            target_roles=config.contact_roles,
            cache_path=config.HOTEL_CACHE_FILE,
            purge_path=config.PURGE_LIST_FILE,
            save_results=True,
        )

    else:
        print("Phase 1 is off and cache loading is off.")
        print("No hotels available to process.")

    if not final_hotels:
        print("\nNo hotels to process.")
        return

    if config.RUN_PHASE_2:
        print("Running Phase 2: Contact enrichment...")

        final_hotels = run_contact_enrichment(
            hotels=final_hotels,
            settings=settings,
            target_roles=config.contact_roles,
            cache_path=config.HOTEL_CACHE_FILE,
            save_after_each_hotel=True,
        )

    print_hotel_summary(final_hotels)


if __name__ == "__main__":
    main()