from scrapegraphai.graphs import SmartScraperGraph

from config import area, location, extra_info, graph_config
from schema import HotelInfo

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
