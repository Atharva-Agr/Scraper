from __future__ import annotations

import json
import re
import sys
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app_state import (
    DATA_DIR,
    DEFAULT_ROLE_PROFILES,
    get_active_cache_path,
    get_active_purge_path,
    get_search_settings,
    load_app_settings,
    load_role_profiles,
    save_role_profile,
    save_search_settings,
    set_active_cache_path,
    set_active_purge_path,
    set_active_role_profile,
)

from pipeline import (
    add_hotel_to_cache,
    get_contact_rows,
    get_hotel_summary_rows,
    load_cache,
    move_contact_between_buckets,
    print_hotel_summary,
    run_contact_enrichment,
    run_full_pipeline,
    run_hotel_discovery,
    save_cache,
    update_contact_status,
    update_hotel_status,
)

from purge_utils import (
    add_blocked_contact_name,
    add_blocked_domain,
    add_blocked_pattern,
    add_blocked_url,
    add_blocked_url_contains,
    add_soft_blocked_domain,
    add_soft_blocked_pattern,
    add_soft_blocked_url,
    add_soft_blocked_url_contains,
    load_purge_list,
    save_purge_list,
)


SEARCH_LISTS_DIR = DATA_DIR / "search_lists"
EXPORTS_DIR = Path("exports")

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


class PipelineWorker(QObject):
    finished = Signal(list)
    failed = Signal(str)
    log = Signal(str)

    def __init__(
        self,
        task_name: str,
        settings: dict,
        roles: list[str],
        cache_path: Path,
        purge_path: Path,
    ):
        super().__init__()

        self.task_name = task_name
        self.settings = settings
        self.roles = roles
        self.cache_path = cache_path
        self.purge_path = purge_path

    def run(self):
        try:
            self.log.emit(f"Starting task: {self.task_name}")

            if self.task_name == "full":
                hotels = run_full_pipeline(
                    settings=self.settings,
                    target_roles=self.roles,
                    cache_path=self.cache_path,
                    purge_path=self.purge_path,
                )

            elif self.task_name == "discovery":
                hotels = run_hotel_discovery(
                    settings=self.settings,
                    target_roles=self.roles,
                    cache_path=self.cache_path,
                    purge_path=self.purge_path,
                    save_results=True,
                )

            elif self.task_name == "contacts":
                hotels = load_cache(self.cache_path)
                hotels = run_contact_enrichment(
                    hotels=hotels,
                    settings=self.settings,
                    target_roles=self.roles,
                    cache_path=self.cache_path,
                    save_after_each_hotel=True,
                )

            else:
                raise ValueError(f"Unknown task: {self.task_name}")

            self.log.emit("Task completed.")
            self.finished.emit(hotels)

        except Exception:
            self.failed.emit(traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("LinenGrass Scraper")
        self.resize(1450, 850)

        SEARCH_LISTS_DIR.mkdir(parents=True, exist_ok=True)
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

        self.settings = load_app_settings()
        self.role_profiles = load_role_profiles()
        self.cache_path = get_active_cache_path(self.settings)
        self.purge_path = get_active_purge_path(self.settings)
        self.hotels = load_cache(self.cache_path)

        self.worker_thread = None
        self.worker = None
        self.advanced_result_view = False

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.build_search_tab()
        self.build_results_tab()
        self.build_contacts_tab()
        self.build_lists_tab()
        self.build_advanced_tab()
        self.build_export_tab()

        self.refresh_all()

    # -----------------------------
    # Helpers
    # -----------------------------

    def show_info(self, message: str):
        QMessageBox.information(self, "LinenGrass", message)

    def show_error(self, message: str):
        QMessageBox.critical(self, "LinenGrass Error", message)

    def append_log(self, message: str):
        self.log_box.append(str(message))

    def get_csv_list(self, box: QLineEdit) -> list[str]:
        values = []

        for item in box.text().split(","):
            value = item.strip()

            if value:
                values.append(value)

        return values

    def selected_table_row(self, table: QTableWidget) -> int:
        selected = table.selectedItems()

        if not selected:
            return -1

        return selected[0].row()

    def slugify(self, value: str) -> str:
        value = str(value or "search").lower()
        value = re.sub(r"[^a-z0-9]+", "-", value)
        value = value.strip("-")
        return value or "search"

    def make_named_search_path(self) -> Path:
        search_name = self.search_name_input.text().strip()

        if not search_name:
            search_name = f"{self.area_input.text()} {self.location_input.text()} hotels"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.slugify(search_name)}_{timestamp}.json"
        return SEARCH_LISTS_DIR / filename

    def get_hotel_type_from_ui(self) -> str:
        selected = self.hotel_type_dropdown.currentText()

        if selected == "Custom":
            return self.custom_hotel_type_input.text().strip() or "hotel"

        return selected

    def get_current_settings_from_ui(self) -> dict:
        complete_search = self.complete_search_checkbox.isChecked()

        settings = {
            "search_name": self.search_name_input.text().strip(),
            "complete_search": complete_search,
            "location": self.location_input.text().strip(),
            "area": self.area_input.text().strip(),
            "hotel_type": self.get_hotel_type_from_ui(),
            "extra_info": self.extra_info_input.text().strip(),
            "nearby_area_terms": self.get_csv_list(self.nearby_terms_input),
            "excluded_location_terms": self.get_csv_list(self.excluded_terms_input),
            "max_search_results": self.max_search_results_input.value(),
            "max_pages_to_try": self.max_pages_input.value(),
            "target_hotels": self.target_hotels_input.value(),
            "max_contact_search_results": self.contact_results_input.value(),
            "max_contact_pages_per_hotel": self.contact_pages_input.value(),
        }

        if complete_search:
            # Basic UI hides hotel-count controls. The backend still needs safe values.
            # These are intentionally broad so complete search is not capped too early.
            settings["target_hotels"] = 100
            settings["max_pages_to_try"] = 100
            settings["max_search_results"] = max(settings["max_search_results"], 20)

        return settings

    def get_roles_from_ui(self) -> list[str]:
        roles = []

        for index in range(self.target_roles_list.count()):
            text = self.target_roles_list.item(index).text().strip()

            if text:
                roles.append(text)

        return roles

    def save_current_setup(self, show_popup: bool = True):
        search_settings = self.get_current_settings_from_ui()
        save_search_settings(search_settings)

        profile_name = self.role_profile_name_input.text().strip() or "default"

        target_roles = [
            self.target_roles_list.item(index).text()
            for index in range(self.target_roles_list.count())
        ]

        secondary_roles = [
            self.secondary_roles_list.item(index).text()
            for index in range(self.secondary_roles_list.count())
        ]

        ignored_roles = [
            self.ignored_roles_list.item(index).text()
            for index in range(self.ignored_roles_list.count())
        ]

        save_role_profile(profile_name, target_roles, secondary_roles, ignored_roles)
        set_active_role_profile(profile_name)

        self.settings = load_app_settings()
        self.role_profiles = load_role_profiles()

        if show_popup:
            self.show_info("Settings and role profile saved.")

    def open_url(self, url: str):
        url = str(url or "").strip()

        if not url:
            self.show_error("No URL available.")
            return

        webbrowser.open(url)

    def get_selected_hotel_index_from_results(self) -> int:
        row = self.selected_table_row(self.results_table)

        if row < 0:
            return -1

        item = self.results_table.item(row, 0)

        if not item:
            return -1

        return int(item.text())

    def get_selected_hotel(self) -> tuple[int, dict | None]:
        index = self.get_selected_hotel_index_from_results()

        if index < 0 or index >= len(self.hotels):
            return -1, None

        return index, self.hotels[index]

    def set_advanced_result_view(self, checked: bool):
        self.advanced_result_view = checked
        self.refresh_results_table()
        self.refresh_selected_hotel_details()
        self.refresh_contacts_tab()

    # -----------------------------
    # Search tab
    # -----------------------------

    def build_search_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)

        left = QVBoxLayout()
        right = QVBoxLayout()

        search_box = QGroupBox("Search")
        form = QFormLayout(search_box)

        search_settings = get_search_settings(self.settings)

        self.search_name_input = QLineEdit()
        self.search_name_input.setPlaceholderText("Example: Downtown business hotels")

        self.location_input = QLineEdit(search_settings["location"])
        self.area_input = QLineEdit(search_settings["area"])

        self.hotel_type_dropdown = QComboBox()
        self.hotel_type_dropdown.addItems(HOTEL_TYPE_OPTIONS)
        default_hotel_type = str(search_settings.get("hotel_type") or "Business hotel")
        matched_index = self.hotel_type_dropdown.findText(default_hotel_type, Qt.MatchFixedString)

        if matched_index >= 0:
            self.hotel_type_dropdown.setCurrentIndex(matched_index)
        else:
            self.hotel_type_dropdown.setCurrentText("Custom")

        self.custom_hotel_type_input = QLineEdit(default_hotel_type)
        self.custom_hotel_type_input.setPlaceholderText("Enter custom hotel type")
        self.custom_hotel_type_input.setVisible(self.hotel_type_dropdown.currentText() == "Custom")
        self.hotel_type_dropdown.currentTextChanged.connect(
            lambda text: self.custom_hotel_type_input.setVisible(text == "Custom")
        )

        self.extra_info_input = QLineEdit(search_settings["extra_info"])

        self.complete_search_checkbox = QCheckBox("Complete search")
        self.complete_search_checkbox.setToolTip(
            "Complete search hides hotel-count controls and tries to find as many hotels in the area as possible."
        )
        self.complete_search_checkbox.stateChanged.connect(self.update_complete_search_visibility)

        self.contact_results_input = QSpinBox()
        self.contact_results_input.setRange(1, 50)
        self.contact_results_input.setValue(search_settings["max_contact_search_results"])

        self.partial_search_box = QGroupBox("Partial search size")
        partial_form = QFormLayout(self.partial_search_box)

        self.target_hotels_input = QSpinBox()
        self.target_hotels_input.setRange(1, 100)
        self.target_hotels_input.setValue(search_settings["target_hotels"])

        partial_form.addRow("Hotels to find", self.target_hotels_input)

        form.addRow("Search list name", self.search_name_input)
        form.addRow("Location / City", self.location_input)
        form.addRow("Area / Neighbourhood", self.area_input)
        form.addRow("Hotel type", self.hotel_type_dropdown)
        form.addRow("Custom hotel type", self.custom_hotel_type_input)
        form.addRow("Extra requirements", self.extra_info_input)
        form.addRow("Search mode", self.complete_search_checkbox)
        form.addRow("Contacts to search per hotel", self.contact_results_input)

        left.addWidget(search_box)
        left.addWidget(self.partial_search_box)

        run_box = QGroupBox("Run")
        run_layout = QVBoxLayout(run_box)

        full_run_btn = QPushButton("Run Search + Contacts")
        discovery_btn = QPushButton("Run Hotel Search Only")
        contacts_btn = QPushButton("Run Contacts On Current List")

        full_run_btn.clicked.connect(lambda: self.start_pipeline_task("full"))
        discovery_btn.clicked.connect(lambda: self.start_pipeline_task("discovery"))
        contacts_btn.clicked.connect(lambda: self.start_pipeline_task("contacts"))

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)

        run_layout.addWidget(full_run_btn)
        run_layout.addWidget(discovery_btn)
        run_layout.addWidget(contacts_btn)
        run_layout.addWidget(QLabel("Progress / Logs"))
        run_layout.addWidget(self.log_box)

        right.addWidget(run_box)

        layout.addLayout(left, 1)
        layout.addLayout(right, 2)

        self.tabs.addTab(tab, "Search")

    def update_complete_search_visibility(self):
        self.partial_search_box.setVisible(not self.complete_search_checkbox.isChecked())

    # -----------------------------
    # Results tab
    # -----------------------------

    def build_results_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top_row = QHBoxLayout()
        self.active_list_label = QLabel(str(self.cache_path))
        self.results_advanced_checkbox = QCheckBox("Advanced result view")
        self.results_advanced_checkbox.stateChanged.connect(
            lambda state: self.set_advanced_result_view(state == Qt.Checked)
        )

        top_row.addWidget(QLabel("Active list:"))
        top_row.addWidget(self.active_list_label, 1)
        top_row.addWidget(self.results_advanced_checkbox)

        splitter = QSplitter(Qt.Horizontal)

        self.results_table = QTableWidget()
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.itemSelectionChanged.connect(self.refresh_selected_hotel_details)

        self.hotel_details_box = QTextEdit()
        self.hotel_details_box.setReadOnly(True)

        splitter.addWidget(self.results_table)
        splitter.addWidget(self.hotel_details_box)
        splitter.setSizes([650, 800])

        button_row = QHBoxLayout()

        approve_btn = QPushButton("Approve")
        reject_btn = QPushButton("Reject")
        delete_btn = QPushButton("Remove From List")
        open_btn = QPushButton("Open Website / Source")
        contacts_btn = QPushButton("Run Contacts For This List")

        approve_btn.clicked.connect(lambda: self.set_selected_result_status("approved"))
        reject_btn.clicked.connect(lambda: self.set_selected_result_status("rejected"))
        delete_btn.clicked.connect(self.remove_selected_hotel_from_list)
        open_btn.clicked.connect(self.open_selected_hotel_url)
        contacts_btn.clicked.connect(lambda: self.start_pipeline_task("contacts"))

        button_row.addWidget(approve_btn)
        button_row.addWidget(reject_btn)
        button_row.addWidget(delete_btn)
        button_row.addWidget(open_btn)
        button_row.addWidget(contacts_btn)

        layout.addLayout(top_row)
        layout.addWidget(splitter)
        layout.addLayout(button_row)

        self.tabs.addTab(tab, "Results")

    def get_basic_hotel_rows(self) -> list[dict]:
        rows = []

        for index, hotel in enumerate(self.hotels):
            rows.append(
                {
                    "index": index,
                    "hotel_name": hotel.get("hotel_name"),
                    "location": hotel.get("location") or hotel.get("area"),
                    "phone": hotel.get("phone"),
                    "email": hotel.get("email"),
                    "website": hotel.get("website") or hotel.get("source_url"),
                    "status": hotel.get("review_status"),
                    "confirmed": len(hotel.get("manager_contacts") or []),
                    "possible": len(hotel.get("contact_leads") or []),
                }
            )

        return rows

    def refresh_results_table(self):
        if self.advanced_result_view:
            rows = get_hotel_summary_rows(self.hotels)
        else:
            rows = self.get_basic_hotel_rows()

        self.fill_table(self.results_table, rows)

    def refresh_selected_hotel_details(self):
        _, hotel = self.get_selected_hotel()

        if not hotel:
            self.hotel_details_box.setPlainText("Select a hotel to view details.")
            return

        if self.advanced_result_view:
            self.hotel_details_box.setPlainText(json.dumps(hotel, indent=4, ensure_ascii=False))
            return

        lines = [
            f"Hotel: {hotel.get('hotel_name') or ''}",
            f"Location: {hotel.get('location') or ''}",
            f"Area: {hotel.get('area') or ''}",
            f"Website: {hotel.get('website') or hotel.get('source_url') or ''}",
            f"General number: {hotel.get('phone') or ''}",
            f"Email: {hotel.get('email') or ''}",
            f"Hotel type: {hotel.get('hotel_type') or ''}",
            f"Chain/Independent: {hotel.get('chain_or_independent') or ''}",
            f"Rating: {hotel.get('rating') or ''}",
            f"Status: {hotel.get('review_status') or ''}",
            f"Notes: {hotel.get('notes') or ''}",
            "",
            "Review summary:",
            str(hotel.get("review_summary") or ""),
            "",
            "Facilities:",
            self.format_list(hotel.get("facilities") or []),
            "",
            "Room types:",
            self.format_list(hotel.get("room_types") or []),
            "",
            "Room pricing:",
            self.format_list(hotel.get("room_pricing") or []),
            "",
            f"Confirmed contacts: {len(hotel.get('manager_contacts') or [])}",
            f"Possible contacts: {len(hotel.get('contact_leads') or [])}",
        ]

        self.hotel_details_box.setPlainText("\n".join(lines))

    def format_list(self, values: Any) -> str:
        if not values:
            return ""

        if isinstance(values, list):
            formatted = []

            for value in values:
                if isinstance(value, dict):
                    formatted.append(json.dumps(value, ensure_ascii=False))
                else:
                    formatted.append(str(value))

            return "\n".join(f"- {item}" for item in formatted)

        return str(values)

    def set_selected_result_status(self, status: str):
        index, _ = self.get_selected_hotel()

        if index < 0:
            self.show_error("Select a hotel first.")
            return

        self.hotels = update_hotel_status(index, status, self.cache_path)
        self.refresh_all()

    def remove_selected_hotel_from_list(self):
        index, hotel = self.get_selected_hotel()

        if index < 0 or hotel is None:
            self.show_error("Select a hotel first.")
            return

        del self.hotels[index]
        save_cache(self.hotels, self.cache_path)
        self.refresh_all()

    def open_selected_hotel_url(self):
        _, hotel = self.get_selected_hotel()

        if not hotel:
            self.show_error("Select a hotel first.")
            return

        self.open_url(hotel.get("website") or hotel.get("source_url"))

    # -----------------------------
    # Contacts tab
    # -----------------------------

    def build_contacts_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top_row = QHBoxLayout()

        self.contact_hotel_dropdown = QComboBox()
        self.contact_hotel_dropdown.currentIndexChanged.connect(self.refresh_contact_dropdown)

        self.contact_selector_dropdown = QComboBox()
        self.contact_selector_dropdown.currentIndexChanged.connect(self.refresh_selected_contact_details)

        self.contacts_advanced_checkbox = QCheckBox("Advanced contact view")
        self.contacts_advanced_checkbox.stateChanged.connect(
            lambda state: self.set_advanced_result_view(state == Qt.Checked)
        )

        top_row.addWidget(QLabel("Hotel"))
        top_row.addWidget(self.contact_hotel_dropdown, 1)
        top_row.addWidget(QLabel("Contact"))
        top_row.addWidget(self.contact_selector_dropdown, 1)
        top_row.addWidget(self.contacts_advanced_checkbox)

        self.contact_details_box = QTextEdit()
        self.contact_details_box.setReadOnly(True)

        button_row = QHBoxLayout()

        confirm_btn = QPushButton("Confirm")
        possible_btn = QPushButton("Move To Possible")
        doubtful_btn = QPushButton("Move To Doubtful")
        outdated_btn = QPushButton("Mark Outdated")
        wrong_hotel_btn = QPushButton("Wrong Hotel")
        reject_btn = QPushButton("Reject")
        open_btn = QPushButton("Open Source")

        confirm_btn.clicked.connect(lambda: self.move_selected_contact("manager_contacts"))
        possible_btn.clicked.connect(lambda: self.move_selected_contact("contact_leads"))
        doubtful_btn.clicked.connect(lambda: self.move_selected_contact("contact_debug_candidates"))
        outdated_btn.clicked.connect(lambda: self.set_selected_contact_status("outdated"))
        wrong_hotel_btn.clicked.connect(lambda: self.set_selected_contact_status("wrong_hotel"))
        reject_btn.clicked.connect(lambda: self.set_selected_contact_status("rejected"))
        open_btn.clicked.connect(self.open_selected_contact_source)

        button_row.addWidget(confirm_btn)
        button_row.addWidget(possible_btn)
        button_row.addWidget(doubtful_btn)
        button_row.addWidget(outdated_btn)
        button_row.addWidget(wrong_hotel_btn)
        button_row.addWidget(reject_btn)
        button_row.addWidget(open_btn)

        layout.addLayout(top_row)
        layout.addWidget(self.contact_details_box)
        layout.addLayout(button_row)

        self.tabs.addTab(tab, "Contacts")

    def get_all_contacts_for_hotel(self, hotel: dict) -> list[dict]:
        contacts = []

        for bucket, label in [
            ("manager_contacts", "Confirmed"),
            ("contact_leads", "Possible"),
            ("contact_debug_candidates", "Doubtful"),
        ]:
            for index, contact in enumerate(hotel.get(bucket) or []):
                item = dict(contact)
                item["_bucket"] = bucket
                item["_bucket_label"] = label
                item["_contact_index"] = index
                contacts.append(item)

        return contacts

    def refresh_contacts_tab(self):
        current_index = self.contact_hotel_dropdown.currentIndex() if hasattr(self, "contact_hotel_dropdown") else -1

        self.contact_hotel_dropdown.blockSignals(True)
        self.contact_hotel_dropdown.clear()

        for index, hotel in enumerate(self.hotels):
            self.contact_hotel_dropdown.addItem(hotel.get("hotel_name") or f"Hotel {index + 1}", index)

        if 0 <= current_index < self.contact_hotel_dropdown.count():
            self.contact_hotel_dropdown.setCurrentIndex(current_index)

        self.contact_hotel_dropdown.blockSignals(False)
        self.refresh_contact_dropdown()

    def refresh_contact_dropdown(self):
        hotel_index = self.contact_hotel_dropdown.currentData()

        self.contact_selector_dropdown.blockSignals(True)
        self.contact_selector_dropdown.clear()

        if hotel_index is None or not (0 <= int(hotel_index) < len(self.hotels)):
            self.contact_selector_dropdown.blockSignals(False)
            self.contact_details_box.setPlainText("No hotel selected.")
            return

        contacts = self.get_all_contacts_for_hotel(self.hotels[int(hotel_index)])

        for contact in contacts:
            name = contact.get("name") or contact.get("title") or "Unknown contact"
            role = contact.get("role") or contact.get("matched_role") or "Unknown role"
            label = contact.get("_bucket_label") or "Contact"
            self.contact_selector_dropdown.addItem(f"{label}: {name} — {role}", contact)

        self.contact_selector_dropdown.blockSignals(False)
        self.refresh_selected_contact_details()

    def refresh_selected_contact_details(self):
        contact = self.contact_selector_dropdown.currentData()

        if not contact:
            self.contact_details_box.setPlainText("No contacts found for this hotel yet.")
            return

        if self.advanced_result_view:
            self.contact_details_box.setPlainText(json.dumps(contact, indent=4, ensure_ascii=False))
            return

        lines = [
            f"Name: {contact.get('name') or ''}",
            f"Role: {contact.get('role') or contact.get('matched_role') or ''}",
            f"Group: {contact.get('_bucket_label') or ''}",
            f"Confidence: {contact.get('confidence') or ''}",
            f"Source type: {contact.get('evidence_type') or ''}",
            f"Source: {contact.get('source_url') or contact.get('url') or contact.get('profile_url') or ''}",
            f"LinkedIn: {contact.get('linkedin_url') or ''}",
            f"Email: {contact.get('email') or ''}",
            f"Status: {contact.get('review_status') or ''}",
            f"Notes: {contact.get('notes') or ''}",
            "",
            "Reasons:",
            self.format_list(contact.get("evidence_reasons") or contact.get("reasons") or []),
        ]

        self.contact_details_box.setPlainText("\n".join(lines))

    def selected_contact_identity(self):
        hotel_index = self.contact_hotel_dropdown.currentData()
        contact = self.contact_selector_dropdown.currentData()

        if hotel_index is None or not contact:
            return None

        return int(hotel_index), contact.get("_bucket"), int(contact.get("_contact_index"))

    def move_selected_contact(self, target_bucket: str):
        identity = self.selected_contact_identity()

        if not identity:
            self.show_error("Select a contact first.")
            return

        hotel_index, source_bucket, contact_index = identity

        self.hotels = move_contact_between_buckets(
            hotel_index,
            source_bucket,
            contact_index,
            target_bucket,
            self.cache_path,
        )

        self.refresh_all()

    def set_selected_contact_status(self, status: str):
        identity = self.selected_contact_identity()

        if not identity:
            self.show_error("Select a contact first.")
            return

        hotel_index, bucket, contact_index = identity

        self.hotels = update_contact_status(
            hotel_index,
            bucket,
            contact_index,
            status,
            self.cache_path,
        )

        self.refresh_all()

    def open_selected_contact_source(self):
        contact = self.contact_selector_dropdown.currentData()

        if not contact:
            self.show_error("Select a contact first.")
            return

        self.open_url(contact.get("source_url") or contact.get("url") or contact.get("profile_url") or contact.get("linkedin_url"))

    # -----------------------------
    # Lists tab
    # -----------------------------

    def build_lists_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        info = QLabel("Each search is saved as its own list. Select lists here to open or merge them.")

        self.lists_widget = QListWidget()
        self.lists_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)

        button_row = QHBoxLayout()

        open_btn = QPushButton("Open Selected List")
        merge_btn = QPushButton("Merge Selected Lists")
        refresh_btn = QPushButton("Refresh Lists")
        save_as_btn = QPushButton("Save Current List As")

        open_btn.clicked.connect(self.open_selected_search_list)
        merge_btn.clicked.connect(self.merge_selected_search_lists)
        refresh_btn.clicked.connect(self.refresh_lists_tab)
        save_as_btn.clicked.connect(self.save_current_list_as)

        button_row.addWidget(open_btn)
        button_row.addWidget(merge_btn)
        button_row.addWidget(refresh_btn)
        button_row.addWidget(save_as_btn)

        layout.addWidget(info)
        layout.addWidget(self.lists_widget)
        layout.addLayout(button_row)

        self.tabs.addTab(tab, "Lists")

    def refresh_lists_tab(self):
        self.lists_widget.clear()

        for path in sorted(SEARCH_LISTS_DIR.glob("*.json")):
            self.lists_widget.addItem(str(path))

        root_cache = Path("hotel_cache.json")
        if root_cache.exists():
            self.lists_widget.addItem(str(root_cache.resolve()))

    def get_selected_list_paths(self) -> list[Path]:
        return [Path(item.text()) for item in self.lists_widget.selectedItems()]

    def open_selected_search_list(self):
        paths = self.get_selected_list_paths()

        if not paths:
            self.show_error("Select a list first.")
            return

        self.cache_path = paths[0]
        set_active_cache_path(self.cache_path)
        self.hotels = load_cache(self.cache_path)
        self.active_list_label.setText(str(self.cache_path))
        self.refresh_all()

    def merge_selected_search_lists(self):
        paths = self.get_selected_list_paths()

        if len(paths) < 2:
            self.show_error("Select at least two lists to merge.")
            return

        merged_hotels = []

        for path in paths:
            merged_hotels.extend(load_cache(path))

        merged_name = f"merged_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        merged_path = SEARCH_LISTS_DIR / merged_name

        save_cache(merged_hotels, merged_path)
        self.cache_path = merged_path
        set_active_cache_path(self.cache_path)
        self.hotels = load_cache(self.cache_path)
        self.active_list_label.setText(str(self.cache_path))
        self.refresh_all()
        self.show_info(f"Merged lists saved to:\n{merged_path}")

    def save_current_list_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save current list as",
            str(SEARCH_LISTS_DIR / "new_search_list.json"),
            "JSON Files (*.json)",
        )

        if not path:
            return

        self.cache_path = Path(path)
        set_active_cache_path(self.cache_path)
        save_cache(self.hotels, self.cache_path)
        self.active_list_label.setText(str(self.cache_path))
        self.refresh_all()

    # -----------------------------
    # Advanced tab
    # -----------------------------

    def build_advanced_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)

        left = QVBoxLayout()
        right = QVBoxLayout()

        search_settings = get_search_settings(self.settings)

        advanced_search_box = QGroupBox("Advanced Search Controls")
        advanced_form = QFormLayout(advanced_search_box)

        self.nearby_terms_input = QLineEdit(", ".join(search_settings["nearby_area_terms"]))
        self.excluded_terms_input = QLineEdit(", ".join(search_settings["excluded_location_terms"]))

        self.max_search_results_input = QSpinBox()
        self.max_search_results_input.setRange(1, 50)
        self.max_search_results_input.setValue(search_settings["max_search_results"])

        self.max_pages_input = QSpinBox()
        self.max_pages_input.setRange(1, 500)
        self.max_pages_input.setValue(search_settings["max_pages_to_try"])

        self.contact_pages_input = QSpinBox()
        self.contact_pages_input.setRange(1, 50)
        self.contact_pages_input.setValue(search_settings["max_contact_pages_per_hotel"])

        advanced_form.addRow("Nearby area terms", self.nearby_terms_input)
        advanced_form.addRow("Excluded area terms", self.excluded_terms_input)
        advanced_form.addRow("Search results per query", self.max_search_results_input)
        advanced_form.addRow("Max hotel pages to scrape", self.max_pages_input)
        advanced_form.addRow("Contact pages per hotel", self.contact_pages_input)

        role_box = QGroupBox("Contact Role Profiles")
        role_layout = QVBoxLayout(role_box)

        self.role_profile_name_input = QLineEdit(self.settings.get("active_role_profile", "default"))

        active_profile_name = self.settings.get("active_role_profile", "default")
        active_profile = self.role_profiles.get(active_profile_name) or DEFAULT_ROLE_PROFILES["default"]

        self.target_roles_list = QListWidget()
        self.secondary_roles_list = QListWidget()
        self.ignored_roles_list = QListWidget()

        for role in active_profile.get("target_roles", []):
            self.target_roles_list.addItem(role)

        for role in active_profile.get("secondary_roles", []):
            self.secondary_roles_list.addItem(role)

        for role in active_profile.get("ignored_roles", []):
            self.ignored_roles_list.addItem(role)

        self.new_role_input = QLineEdit()
        self.new_role_input.setPlaceholderText("Role to add")

        role_buttons = QHBoxLayout()

        add_target_btn = QPushButton("Add Target")
        add_secondary_btn = QPushButton("Add Secondary")
        add_ignored_btn = QPushButton("Add Ignored")
        remove_role_btn = QPushButton("Remove Selected")
        save_setup_btn = QPushButton("Save Settings")

        add_target_btn.clicked.connect(lambda: self.add_role_to_list(self.target_roles_list))
        add_secondary_btn.clicked.connect(lambda: self.add_role_to_list(self.secondary_roles_list))
        add_ignored_btn.clicked.connect(lambda: self.add_role_to_list(self.ignored_roles_list))
        remove_role_btn.clicked.connect(self.remove_selected_role)
        save_setup_btn.clicked.connect(self.save_current_setup)

        role_buttons.addWidget(add_target_btn)
        role_buttons.addWidget(add_secondary_btn)
        role_buttons.addWidget(add_ignored_btn)
        role_buttons.addWidget(remove_role_btn)

        role_layout.addWidget(QLabel("Profile name"))
        role_layout.addWidget(self.role_profile_name_input)
        role_layout.addWidget(QLabel("Target roles"))
        role_layout.addWidget(self.target_roles_list)
        role_layout.addWidget(QLabel("Secondary roles"))
        role_layout.addWidget(self.secondary_roles_list)
        role_layout.addWidget(QLabel("Ignored roles"))
        role_layout.addWidget(self.ignored_roles_list)
        role_layout.addWidget(self.new_role_input)
        role_layout.addLayout(role_buttons)
        role_layout.addWidget(save_setup_btn)

        left.addWidget(advanced_search_box)
        left.addWidget(role_box)

        cache_box = QGroupBox("Cache / List Controls")
        cache_layout = QVBoxLayout(cache_box)

        self.cache_path_label = QLabel(str(self.cache_path))

        open_cache_btn = QPushButton("Open Cache/List")
        save_cache_btn = QPushButton("Save Current List")
        manual_add_btn = QPushButton("Add Hotel Manually")

        open_cache_btn.clicked.connect(self.open_cache_file)
        save_cache_btn.clicked.connect(self.save_current_cache)
        manual_add_btn.clicked.connect(self.add_manual_hotel_dialog)

        cache_layout.addWidget(QLabel("Active cache/list"))
        cache_layout.addWidget(self.cache_path_label)
        cache_layout.addWidget(open_cache_btn)
        cache_layout.addWidget(save_cache_btn)
        cache_layout.addWidget(manual_add_btn)

        purge_box = QGroupBox("Purge Rules")
        purge_layout = QVBoxLayout(purge_box)
        purge_form = QFormLayout()

        self.purge_path_label = QLabel(str(self.purge_path))
        self.purge_type_box = QComboBox()
        self.purge_type_box.addItems([
            "Hard URL",
            "Hard Domain",
            "Hard URL Contains",
            "Hard Contact Name",
            "Hard Text Pattern",
            "Soft URL",
            "Soft Domain",
            "Soft URL Contains",
            "Soft Text Pattern",
        ])

        self.purge_value_input = QLineEdit()
        self.purge_reason_input = QLineEdit()

        add_purge_btn = QPushButton("Add Purge Rule")
        open_purge_btn = QPushButton("Open Purge File")

        add_purge_btn.clicked.connect(self.add_purge_rule)
        open_purge_btn.clicked.connect(self.open_purge_file)

        purge_form.addRow("Purge file", self.purge_path_label)
        purge_form.addRow("Rule type", self.purge_type_box)
        purge_form.addRow("Value", self.purge_value_input)
        purge_form.addRow("Reason", self.purge_reason_input)

        self.purge_view = QTextEdit()
        self.purge_view.setReadOnly(True)

        purge_layout.addLayout(purge_form)
        purge_layout.addWidget(add_purge_btn)
        purge_layout.addWidget(open_purge_btn)
        purge_layout.addWidget(QLabel("Current purge list"))
        purge_layout.addWidget(self.purge_view)

        right.addWidget(cache_box)
        right.addWidget(purge_box)

        layout.addLayout(left, 1)
        layout.addLayout(right, 1)

        self.tabs.addTab(tab, "Advanced")

    def add_role_to_list(self, list_widget: QListWidget):
        role = self.new_role_input.text().strip()

        if not role:
            return

        existing = {
            list_widget.item(index).text().lower()
            for index in range(list_widget.count())
        }

        if role.lower() not in existing:
            list_widget.addItem(role)

        self.new_role_input.clear()

    def remove_selected_role(self):
        for list_widget in [
            self.target_roles_list,
            self.secondary_roles_list,
            self.ignored_roles_list,
        ]:
            for item in list_widget.selectedItems():
                row = list_widget.row(item)
                list_widget.takeItem(row)

    def open_cache_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open cache/list file",
            str(self.cache_path.parent),
            "JSON Files (*.json)",
        )

        if not path:
            return

        self.cache_path = Path(path)
        set_active_cache_path(self.cache_path)
        self.hotels = load_cache(self.cache_path)
        self.active_list_label.setText(str(self.cache_path))
        self.cache_path_label.setText(str(self.cache_path))
        self.refresh_all()

    def save_current_cache(self):
        save_cache(self.hotels, self.cache_path)
        self.show_info("Current list saved.")

    def add_manual_hotel_dialog(self):
        hotel_name, ok = self.simple_input_dialog("Hotel name")

        if not ok or not hotel_name.strip():
            return

        website, _ = self.simple_input_dialog("Website/source URL")
        phone, _ = self.simple_input_dialog("General phone/contact number")
        email, _ = self.simple_input_dialog("Email")

        hotel = {
            "hotel_name": hotel_name.strip(),
            "location": self.location_input.text().strip(),
            "area": self.area_input.text().strip(),
            "website": website.strip(),
            "source_url": website.strip(),
            "phone": phone.strip(),
            "email": email.strip(),
            "review_status": "approved",
            "manager_contacts": [],
            "contact_leads": [],
            "contact_debug_candidates": [],
        }

        self.hotels = add_hotel_to_cache(hotel, self.cache_path)
        self.refresh_all()

    def simple_input_dialog(self, label: str) -> tuple[str, bool]:
        from PySide6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getText(self, "LinenGrass", label)
        return text, ok

    def open_purge_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open purge file",
            str(self.purge_path.parent),
            "JSON Files (*.json)",
        )

        if not path:
            return

        self.purge_path = Path(path)
        set_active_purge_path(self.purge_path)
        self.purge_path_label.setText(str(self.purge_path))
        self.refresh_purge_view()

    def add_purge_rule(self):
        purge_list = load_purge_list(self.purge_path)

        rule_type = self.purge_type_box.currentText()
        value = self.purge_value_input.text().strip()
        reason = self.purge_reason_input.text().strip()

        if not value:
            self.show_error("Enter a value.")
            return

        if rule_type == "Hard URL":
            purge_list = add_blocked_url(purge_list, value, reason)
        elif rule_type == "Hard Domain":
            purge_list = add_blocked_domain(purge_list, value, reason)
        elif rule_type == "Hard URL Contains":
            purge_list = add_blocked_url_contains(purge_list, value, reason)
        elif rule_type == "Hard Contact Name":
            purge_list = add_blocked_contact_name(purge_list, value, reason)
        elif rule_type == "Hard Text Pattern":
            purge_list = add_blocked_pattern(purge_list, value, reason)
        elif rule_type == "Soft URL":
            purge_list = add_soft_blocked_url(purge_list, value, reason)
        elif rule_type == "Soft Domain":
            purge_list = add_soft_blocked_domain(purge_list, value, reason)
        elif rule_type == "Soft URL Contains":
            purge_list = add_soft_blocked_url_contains(purge_list, value, reason)
        elif rule_type == "Soft Text Pattern":
            purge_list = add_soft_blocked_pattern(purge_list, value, reason)

        save_purge_list(purge_list, self.purge_path)

        self.purge_value_input.clear()
        self.purge_reason_input.clear()
        self.refresh_purge_view()

    # -----------------------------
    # Export tab
    # -----------------------------

    def build_export_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        export_hotels_btn = QPushButton("Export Full Hotels CSV")
        export_contacts_btn = QPushButton("Export Confirmed Contacts CSV")
        export_possible_btn = QPushButton("Export Possible Contacts CSV")
        export_combined_btn = QPushButton("Export Combined Lead List CSV")
        open_exports_btn = QPushButton("Open Exports Folder")

        export_hotels_btn.clicked.connect(self.export_full_hotels)
        export_contacts_btn.clicked.connect(lambda: self.export_contacts_bucket("manager_contacts", "confirmed_contacts.csv"))
        export_possible_btn.clicked.connect(lambda: self.export_contacts_bucket("contact_leads", "possible_contacts.csv"))
        export_combined_btn.clicked.connect(self.export_combined_leads)
        open_exports_btn.clicked.connect(lambda: webbrowser.open(str(EXPORTS_DIR.resolve())))

        layout.addWidget(QLabel("Exports use the currently opened search list."))
        layout.addWidget(export_hotels_btn)
        layout.addWidget(export_contacts_btn)
        layout.addWidget(export_possible_btn)
        layout.addWidget(export_combined_btn)
        layout.addWidget(open_exports_btn)
        layout.addStretch()

        self.tabs.addTab(tab, "Export")

    def write_csv(self, path: Path, rows: list[dict]):
        import csv

        path.parent.mkdir(parents=True, exist_ok=True)

        if not rows:
            path.write_text("", encoding="utf-8")
            return

        fieldnames = list(rows[0].keys())

        with open(path, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def export_full_hotels(self):
        rows = []

        for hotel in self.hotels:
            rows.append(
                {
                    "hotel_name": hotel.get("hotel_name"),
                    "location": hotel.get("location"),
                    "area": hotel.get("area"),
                    "website": hotel.get("website") or hotel.get("source_url"),
                    "phone": hotel.get("phone"),
                    "email": hotel.get("email"),
                    "hotel_type": hotel.get("hotel_type"),
                    "chain_or_independent": hotel.get("chain_or_independent"),
                    "rating": hotel.get("rating"),
                    "review_summary": hotel.get("review_summary"),
                    "room_types": json.dumps(hotel.get("room_types") or [], ensure_ascii=False),
                    "room_pricing": json.dumps(hotel.get("room_pricing") or [], ensure_ascii=False),
                    "facilities": json.dumps(hotel.get("facilities") or [], ensure_ascii=False),
                    "source_url": hotel.get("source_url"),
                    "status": hotel.get("review_status"),
                    "confirmed_contacts": len(hotel.get("manager_contacts") or []),
                    "possible_contacts": len(hotel.get("contact_leads") or []),
                }
            )

        path = EXPORTS_DIR / "full_hotels.csv"
        self.write_csv(path, rows)
        self.show_info(f"Exported to:\n{path}")

    def export_contacts_bucket(self, bucket: str, filename: str):
        rows = get_contact_rows(self.hotels, bucket)
        path = EXPORTS_DIR / filename
        self.write_csv(path, rows)
        self.show_info(f"Exported to:\n{path}")

    def export_combined_leads(self):
        rows = []

        for hotel in self.hotels:
            contacts = hotel.get("manager_contacts") or hotel.get("contact_leads") or []
            best_contact = contacts[0] if contacts else {}

            rows.append(
                {
                    "hotel_name": hotel.get("hotel_name"),
                    "location": hotel.get("location") or hotel.get("area"),
                    "website": hotel.get("website") or hotel.get("source_url"),
                    "hotel_phone": hotel.get("phone"),
                    "hotel_email": hotel.get("email"),
                    "contact_name": best_contact.get("name"),
                    "contact_role": best_contact.get("role") or best_contact.get("matched_role"),
                    "contact_email": best_contact.get("email"),
                    "linkedin_url": best_contact.get("linkedin_url"),
                    "source_url": best_contact.get("source_url") or best_contact.get("url"),
                    "confidence": best_contact.get("confidence"),
                    "review_status": best_contact.get("review_status"),
                }
            )

        path = EXPORTS_DIR / "combined_leads.csv"
        self.write_csv(path, rows)
        self.show_info(f"Exported to:\n{path}")

    # -----------------------------
    # Refresh helpers
    # -----------------------------

    def refresh_all(self):
        self.refresh_results_table()
        self.refresh_selected_hotel_details()
        self.refresh_contacts_tab()
        self.refresh_lists_tab()
        self.refresh_purge_view()

        if hasattr(self, "active_list_label"):
            self.active_list_label.setText(str(self.cache_path))

        if hasattr(self, "cache_path_label"):
            self.cache_path_label.setText(str(self.cache_path))

    def fill_table(self, table: QTableWidget, rows: list[dict]):
        table.clear()

        if not rows:
            table.setRowCount(0)
            table.setColumnCount(0)
            return

        headers = list(rows[0].keys())

        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            for column_index, header in enumerate(headers):
                value = row.get(header)
                item = QTableWidgetItem("" if value is None else str(value))
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                table.setItem(row_index, column_index, item)

        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

    def refresh_purge_view(self):
        if not hasattr(self, "purge_view"):
            return

        purge_list = load_purge_list(self.purge_path)
        self.purge_view.setPlainText(json.dumps(purge_list, indent=4, ensure_ascii=False))

    # -----------------------------
    # Pipeline execution
    # -----------------------------

    def start_pipeline_task(self, task_name: str):
        self.save_current_setup(show_popup=False)

        settings = self.get_current_settings_from_ui()
        roles = self.get_roles_from_ui()

        if not roles:
            self.show_error("Add at least one target role in Advanced > Contact Role Profiles.")
            return

        if task_name in {"full", "discovery"}:
            self.cache_path = self.make_named_search_path()
            set_active_cache_path(self.cache_path)
            self.active_list_label.setText(str(self.cache_path))

        self.worker_thread = QThread()
        self.worker = PipelineWorker(
            task_name=task_name,
            settings=settings,
            roles=roles,
            cache_path=self.cache_path,
            purge_path=self.purge_path,
        )

        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.pipeline_finished)
        self.worker.failed.connect(self.pipeline_failed)
        self.worker.log.connect(self.append_log)

        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)

        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)

        self.append_log(f"Launching {task_name}...")
        self.worker_thread.start()

    def pipeline_finished(self, hotels: list[dict]):
        self.hotels = hotels
        save_cache(self.hotels, self.cache_path)
        self.refresh_all()

        self.append_log("Pipeline finished and search list saved.")
        print_hotel_summary(self.hotels)

    def pipeline_failed(self, error_text: str):
        self.append_log(error_text)
        self.show_error(error_text)


def main():
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
