from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import streamlit as st

from app_state import ensure_app_folders, DEFAULT_ROLE_PROFILES
from pipeline import (
    get_contact_rows,
    get_hotel_summary_rows,
    load_cache,
    run_contact_enrichment,
    run_full_pipeline,
    run_hotel_discovery,
    save_cache,
)


HOTEL_TYPE_OPTIONS = [
    "All hotels",
    "Business hotel",
    "Boutique hotel",
    "Independent hotel",
    "Chain hotel",
    "Budget hotel",
    "Luxury hotel",
    "Airport hotel",
    "Hotel with banquet facilities",
    "Hotel with conference facilities",
    "Custom",
]

DEFAULT_TARGET_ROLES = DEFAULT_ROLE_PROFILES["default"]["target_roles"]
DEFAULT_SECONDARY_ROLES = DEFAULT_ROLE_PROFILES["default"]["secondary_roles"]


def parse_lines(value: str) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def make_csv_download(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return b""

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def show_hotels(hotels: list[dict[str, Any]]) -> None:
    if not hotels:
        st.info("No hotels loaded yet.")
        return

    summary_rows = get_hotel_summary_rows(hotels)
    st.dataframe(summary_rows, use_container_width=True, hide_index=True)

    selected_index = st.selectbox(
        "Open hotel details",
        options=list(range(len(hotels))),
        format_func=lambda index: hotels[index].get("hotel_name") or f"Hotel {index + 1}",
    )

    hotel = hotels[selected_index]

    with st.expander("Hotel details", expanded=True):
        st.write({
            "hotel_name": hotel.get("hotel_name"),
            "location": hotel.get("location"),
            "area": hotel.get("area"),
            "website": hotel.get("website") or hotel.get("source_url"),
            "phone": hotel.get("phone"),
            "email": hotel.get("email"),
            "hotel_type": hotel.get("hotel_type"),
            "review_status": hotel.get("review_status"),
            "confirmed_contacts": len(hotel.get("manager_contacts") or []),
            "possible_contacts": len(hotel.get("contact_leads") or []),
        })

    with st.expander("Full hotel JSON"):
        st.json(hotel)

    st.download_button(
        "Download hotel CSV",
        data=make_csv_download(summary_rows),
        file_name="linengrass_hotels.csv",
        mime="text/csv",
    )


def show_contacts(hotels: list[dict[str, Any]]) -> None:
    confirmed_rows = get_contact_rows(hotels, "manager_contacts")
    lead_rows = get_contact_rows(hotels, "contact_leads")
    debug_rows = get_contact_rows(hotels, "contact_debug_candidates")

    st.subheader("Confirmed contacts")
    st.dataframe(confirmed_rows, use_container_width=True, hide_index=True)
    st.download_button(
        "Download confirmed contacts CSV",
        data=make_csv_download(confirmed_rows),
        file_name="linengrass_confirmed_contacts.csv",
        mime="text/csv",
    )

    st.subheader("Possible contacts")
    st.dataframe(lead_rows, use_container_width=True, hide_index=True)
    st.download_button(
        "Download possible contacts CSV",
        data=make_csv_download(lead_rows),
        file_name="linengrass_possible_contacts.csv",
        mime="text/csv",
    )

    with st.expander("Doubtful / debug candidates"):
        st.dataframe(debug_rows, use_container_width=True, hide_index=True)


st.set_page_config(
    page_title="LinenGrass Lead Manager",
    page_icon="🏨",
    layout="wide",
)

ensure_app_folders()

if "hotels" not in st.session_state:
    try:
        st.session_state.hotels = load_cache()
    except Exception:
        st.session_state.hotels = []

st.title("LinenGrass Lead Manager")
st.caption("Hosted web version for hotel discovery, contact enrichment, review, and CSV export.")

with st.sidebar:
    st.header("Search setup")

    search_name = st.text_input("Search list name", value="Hotel Search")
    location = st.text_input("Location / city", value="")
    area = st.text_input("Area / neighbourhood", value="")

    hotel_type_choice = st.selectbox("Hotel type", HOTEL_TYPE_OPTIONS, index=0)
    custom_hotel_type = ""

    if hotel_type_choice == "Custom":
        custom_hotel_type = st.text_input("Custom hotel type", value="")

    hotel_type = custom_hotel_type.strip() if hotel_type_choice == "Custom" else hotel_type_choice

    extra_info = st.text_area(
        "Extra requirements",
        value="",
        placeholder="Example: prefer hotels with banquet halls or conference facilities.",
    )

    complete_search = st.checkbox("Complete search", value=False)

    target_hotels = 100 if complete_search else st.number_input(
        "Hotels to find",
        min_value=1,
        max_value=100,
        value=5,
        step=1,
    )

    contact_depth = st.number_input(
        "Contact search depth",
        min_value=1,
        max_value=20,
        value=4,
        step=1,
    )

    with st.expander("Advanced terms"):
        nearby_terms = st.text_area(
            "Nearby area terms, one per line",
            value="",
        )
        excluded_terms = st.text_area(
            "Excluded location terms, one per line",
            value="",
        )
        max_search_results = st.number_input("Search results per query", 1, 50, 10)
        max_pages_to_try = st.number_input("Max hotel pages to scrape", 1, 200, int(target_hotels))
        max_contact_pages = st.number_input("Max contact pages per hotel", 1, 20, 2)

    with st.expander("Contact roles"):
        target_roles_text = st.text_area(
            "Target roles",
            value="\n".join(DEFAULT_TARGET_ROLES),
            height=180,
        )
        secondary_roles_text = st.text_area(
            "Secondary roles",
            value="\n".join(DEFAULT_SECONDARY_ROLES),
            height=140,
        )

    settings = {
        "search_name": search_name,
        "location": location,
        "area": area,
        "hotel_type": hotel_type,
        "extra_info": extra_info,
        "nearby_area_terms": parse_lines(nearby_terms),
        "excluded_location_terms": parse_lines(excluded_terms),
        "complete_search": complete_search,
        "target_hotels": int(target_hotels),
        "max_search_results": int(max_search_results),
        "max_pages_to_try": int(max_pages_to_try),
        "max_contact_search_results": int(contact_depth),
        "max_contact_pages_per_hotel": int(max_contact_pages),
    }

    target_roles = parse_lines(target_roles_text) + parse_lines(secondary_roles_text)

    st.divider()

    run_discovery = st.button("Run hotel discovery", use_container_width=True)
    run_contacts = st.button("Run contacts on loaded hotels", use_container_width=True)
    run_full = st.button("Run full pipeline", use_container_width=True)
    load_saved = st.button("Reload saved cache", use_container_width=True)

if load_saved:
    st.session_state.hotels = load_cache()
    st.success("Saved cache loaded.")

if run_discovery or run_contacts or run_full:
    if not location.strip() or not area.strip():
        st.error("Enter both Location and Area before running.")
    else:
        try:
            with st.status("Running LinenGrass backend...", expanded=True):
                if run_discovery:
                    st.write("Discovering hotels...")
                    hotels = run_hotel_discovery(
                        settings=settings,
                        target_roles=target_roles,
                        save_results=True,
                    )

                elif run_contacts:
                    st.write("Enriching loaded hotels with contacts...")
                    hotels = run_contact_enrichment(
                        hotels=st.session_state.hotels,
                        settings=settings,
                        target_roles=target_roles,
                        save_after_each_hotel=True,
                    )

                else:
                    st.write("Running full discovery + contact enrichment...")
                    hotels = run_full_pipeline(
                        settings=settings,
                        target_roles=target_roles,
                    )

                save_cache(hotels)
                st.session_state.hotels = hotels
                st.write("Done.")

            st.success(f"Loaded {len(st.session_state.hotels)} hotel records.")

        except Exception as error:
            st.error(f"Run failed: {type(error).__name__}: {error}")
            st.exception(error)

tab_results, tab_contacts, tab_raw = st.tabs(["Results", "Contacts", "Raw cache"])

with tab_results:
    show_hotels(st.session_state.hotels)

with tab_contacts:
    show_contacts(st.session_state.hotels)

with tab_raw:
    st.json(st.session_state.hotels)
