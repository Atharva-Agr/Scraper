from __future__ import annotations

import sys
import traceback
import webbrowser
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
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
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app_state import (
    DEFAULT_ROLE_PROFILES,
    get_active_cache_path,
    get_active_purge_path,
    get_search_settings,
    load_app_settings,
    load_role_profiles,
    save_app_settings,
    save_role_profile,
    save_search_settings,
    set_active_cache_path,
    set_active_purge_path,
    set_active_role_profile,
)

from pipeline import (
    export_contacts_csv,
    export_hotels_csv,
    export_leads_csv,
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


class PipelineWorker(QObject):
    finished = Signal(list)
    failed = Signal(str)
    log = Signal(str)

    def __init__(self, task_name: str, settings: dict, roles: list[str], cache_path: Path, purge_path: Path):
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

        self.setWindowTitle("LinenGrass Lead Manager")
        self.resize(1450, 850)

        self.settings = load_app_settings()
        self.role_profiles = load_role_profiles()
        self.cache_path = get_active_cache_path(self.settings)
        self.purge_path = get_active_purge_path(self.settings)
        self.hotels = load_cache(self.cache_path)

        self.worker_thread = None
        self.worker = None

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.build_setup_tab()
        self.build_cache_tab()
        self.build_hotel_review_tab()
        self.build_contact_review_tab()
        self.build_purge_tab()
        self.build_export_tab()

        self.refresh_all_tables()

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

    def selected_hotel_index(self) -> int:
        row = self.selected_table_row(self.hotel_table)

        if row < 0:
            return -1

        item = self.hotel_table.item(row, 0)

        if not item:
            return -1

        return int(item.text())

    def get_current_settings_from_ui(self) -> dict:
        return {
            "location": self.location_input.text().strip(),
            "area": self.area_input.text().strip(),
            "hotel_type": self.hotel_type_input.text().strip(),
            "extra_info": self.extra_info_input.text().strip(),
            "nearby_area_terms": self.get_csv_list(self.nearby_terms_input),
            "excluded_location_terms": self.get_csv_list(self.excluded_terms_input),
            "max_search_results": self.max_search_results_input.value(),
            "max_pages_to_try": self.max_pages_input.value(),
            "target_hotels": self.target_hotels_input.value(),
            "max_contact_search_results": self.contact_results_input.value(),
            "max_contact_pages_per_hotel": self.contact_pages_input.value(),
        }

    def get_roles_from_ui(self) -> list[str]:
        roles = []

        for index in range(self.target_roles_list.count()):
            text = self.target_roles_list.item(index).text().strip()

            if text:
                roles.append(text)

        return roles

    def save_current_setup(self):
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

        self.show_info("Settings and role profile saved.")

    def open_url_from_table(self, table: QTableWidget, column_name: str):
        headers = [
            table.horizontalHeaderItem(index).text()
            for index in range(table.columnCount())
        ]

        if column_name not in headers:
            self.show_error(f"Column not found: {column_name}")
            return

        row = self.selected_table_row(table)

        if row < 0:
            self.show_error("Select a row first.")
            return

        column = headers.index(column_name)
        item = table.item(row, column)

        if not item or not item.text().strip():
            self.show_error("No URL in selected row.")
            return

        webbrowser.open(item.text().strip())

    # -----------------------------
    # Setup tab
    # -----------------------------

    def build_setup_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)

        left = QVBoxLayout()
        right = QVBoxLayout()

        search_box = QGroupBox("Search Setup")
        form = QFormLayout(search_box)

        search_settings = get_search_settings(self.settings)

        self.location_input = QLineEdit(search_settings["location"])
        self.area_input = QLineEdit(search_settings["area"])
        self.hotel_type_input = QLineEdit(search_settings["hotel_type"])
        self.extra_info_input = QLineEdit(search_settings["extra_info"])
        self.nearby_terms_input = QLineEdit(", ".join(search_settings["nearby_area_terms"]))
        self.excluded_terms_input = QLineEdit(", ".join(search_settings["excluded_location_terms"]))

        self.max_search_results_input = QSpinBox()
        self.max_search_results_input.setRange(1, 50)
        self.max_search_results_input.setValue(search_settings["max_search_results"])

        self.max_pages_input = QSpinBox()
        self.max_pages_input.setRange(1, 100)
        self.max_pages_input.setValue(search_settings["max_pages_to_try"])

        self.target_hotels_input = QSpinBox()
        self.target_hotels_input.setRange(1, 100)
        self.target_hotels_input.setValue(search_settings["target_hotels"])

        self.contact_results_input = QSpinBox()
        self.contact_results_input.setRange(1, 50)
        self.contact_results_input.setValue(search_settings["max_contact_search_results"])

        self.contact_pages_input = QSpinBox()
        self.contact_pages_input.setRange(1, 20)
        self.contact_pages_input.setValue(search_settings["max_contact_pages_per_hotel"])

        form.addRow("Location / City", self.location_input)
        form.addRow("Area / Neighborhood", self.area_input)
        form.addRow("Hotel Type", self.hotel_type_input)
        form.addRow("Extra Info", self.extra_info_input)
        form.addRow("Nearby Area Terms", self.nearby_terms_input)
        form.addRow("Excluded Location Terms", self.excluded_terms_input)
        form.addRow("Search Results", self.max_search_results_input)
        form.addRow("Max Hotel Pages", self.max_pages_input)
        form.addRow("Target Hotels", self.target_hotels_input)
        form.addRow("Contact Results", self.contact_results_input)
        form.addRow("Contact Pages", self.contact_pages_input)

        left.addWidget(search_box)

        role_box = QGroupBox("Editable Contact Roles")
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
        self.new_role_input.setPlaceholderText("Role to add...")

        role_buttons = QHBoxLayout()

        add_target_btn = QPushButton("Add Target")
        add_secondary_btn = QPushButton("Add Secondary")
        add_ignored_btn = QPushButton("Add Ignored")
        remove_role_btn = QPushButton("Remove Selected")
        save_setup_btn = QPushButton("Save Setup")

        add_target_btn.clicked.connect(lambda: self.add_role_to_list(self.target_roles_list))
        add_secondary_btn.clicked.connect(lambda: self.add_role_to_list(self.secondary_roles_list))
        add_ignored_btn.clicked.connect(lambda: self.add_role_to_list(self.ignored_roles_list))
        remove_role_btn.clicked.connect(self.remove_selected_role)
        save_setup_btn.clicked.connect(self.save_current_setup)

        role_buttons.addWidget(add_target_btn)
        role_buttons.addWidget(add_secondary_btn)
        role_buttons.addWidget(add_ignored_btn)
        role_buttons.addWidget(remove_role_btn)

        role_layout.addWidget(QLabel("Role profile name"))
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

        right.addWidget(role_box)

        run_box = QGroupBox("Run Pipeline")
        run_layout = QVBoxLayout(run_box)

        full_run_btn = QPushButton("Run Full Pipeline")
        discovery_btn = QPushButton("Run Hotel Discovery Only")
        contacts_btn = QPushButton("Run Contacts Only From Cache")

        full_run_btn.clicked.connect(lambda: self.start_pipeline_task("full"))
        discovery_btn.clicked.connect(lambda: self.start_pipeline_task("discovery"))
        contacts_btn.clicked.connect(lambda: self.start_pipeline_task("contacts"))

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)

        run_layout.addWidget(full_run_btn)
        run_layout.addWidget(discovery_btn)
        run_layout.addWidget(contacts_btn)
        run_layout.addWidget(QLabel("Logs"))
        run_layout.addWidget(self.log_box)

        right.addWidget(run_box)

        layout.addLayout(left, 2)
        layout.addLayout(right, 2)

        self.tabs.addTab(tab, "Search Setup")

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

    # -----------------------------
    # Cache tab
    # -----------------------------

    def build_cache_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        path_row = QHBoxLayout()

        self.cache_path_label = QLabel(str(self.cache_path))

        open_cache_btn = QPushButton("Open Cache")
        save_cache_btn = QPushButton("Save Cache")
        save_as_btn = QPushButton("Save Cache As")
        reload_btn = QPushButton("Reload Cache")

        open_cache_btn.clicked.connect(self.open_cache_file)
        save_cache_btn.clicked.connect(self.save_current_cache)
        save_as_btn.clicked.connect(self.save_cache_as)
        reload_btn.clicked.connect(self.reload_cache)

        path_row.addWidget(QLabel("Active cache:"))
        path_row.addWidget(self.cache_path_label, 1)
        path_row.addWidget(open_cache_btn)
        path_row.addWidget(save_cache_btn)
        path_row.addWidget(save_as_btn)
        path_row.addWidget(reload_btn)

        self.cache_table = QTableWidget()
        self.cache_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.cache_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        action_row = QHBoxLayout()

        approve_btn = QPushButton("Approve Hotel")
        reject_btn = QPushButton("Reject Hotel")
        duplicate_btn = QPushButton("Mark Duplicate")
        open_source_btn = QPushButton("Open Source URL")

        approve_btn.clicked.connect(lambda: self.set_selected_hotel_status("approved"))
        reject_btn.clicked.connect(lambda: self.set_selected_hotel_status("rejected"))
        duplicate_btn.clicked.connect(lambda: self.set_selected_hotel_status("duplicate"))
        open_source_btn.clicked.connect(lambda: self.open_url_from_table(self.cache_table, "source_url"))

        action_row.addWidget(approve_btn)
        action_row.addWidget(reject_btn)
        action_row.addWidget(duplicate_btn)
        action_row.addWidget(open_source_btn)

        layout.addLayout(path_row)
        layout.addWidget(self.cache_table)
        layout.addLayout(action_row)

        self.tabs.addTab(tab, "Cache Manager")

    def open_cache_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open cache file",
            str(self.cache_path.parent),
            "JSON Files (*.json)",
        )

        if not path:
            return

        self.cache_path = Path(path)
        set_active_cache_path(self.cache_path)
        self.cache_path_label.setText(str(self.cache_path))
        self.hotels = load_cache(self.cache_path)
        self.refresh_all_tables()

    def save_current_cache(self):
        save_cache(self.hotels, self.cache_path)
        self.show_info("Cache saved.")

    def save_cache_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save cache as",
            str(self.cache_path),
            "JSON Files (*.json)",
        )

        if not path:
            return

        self.cache_path = Path(path)
        set_active_cache_path(self.cache_path)
        self.cache_path_label.setText(str(self.cache_path))
        save_cache(self.hotels, self.cache_path)
        self.show_info("Cache saved.")

    def reload_cache(self):
        self.hotels = load_cache(self.cache_path)
        self.refresh_all_tables()

    def set_selected_hotel_status(self, status: str):
        row = self.selected_table_row(self.cache_table)

        if row < 0:
            self.show_error("Select a hotel first.")
            return

        hotel_index = int(self.cache_table.item(row, 0).text())
        self.hotels = update_hotel_status(hotel_index, status, self.cache_path)
        self.refresh_all_tables()

    # -----------------------------
    # Hotel review tab
    # -----------------------------

    def build_hotel_review_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.hotel_table = QTableWidget()
        self.hotel_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hotel_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        self.hotel_table.itemSelectionChanged.connect(self.refresh_contact_tables)

        buttons = QHBoxLayout()

        approve_btn = QPushButton("Approve")
        reject_btn = QPushButton("Reject")
        duplicate_btn = QPushButton("Duplicate")
        enrich_selected_btn = QPushButton("Run Contacts For Cache")

        approve_btn.clicked.connect(lambda: self.set_selected_hotel_status_from_hotel_table("approved"))
        reject_btn.clicked.connect(lambda: self.set_selected_hotel_status_from_hotel_table("rejected"))
        duplicate_btn.clicked.connect(lambda: self.set_selected_hotel_status_from_hotel_table("duplicate"))
        enrich_selected_btn.clicked.connect(lambda: self.start_pipeline_task("contacts"))

        buttons.addWidget(approve_btn)
        buttons.addWidget(reject_btn)
        buttons.addWidget(duplicate_btn)
        buttons.addWidget(enrich_selected_btn)

        layout.addWidget(self.hotel_table)
        layout.addLayout(buttons)

        self.tabs.addTab(tab, "Hotel Review")

    def set_selected_hotel_status_from_hotel_table(self, status: str):
        hotel_index = self.selected_hotel_index()

        if hotel_index < 0:
            self.show_error("Select a hotel first.")
            return

        self.hotels = update_hotel_status(hotel_index, status, self.cache_path)
        self.refresh_all_tables()

    # -----------------------------
    # Contact review tab
    # -----------------------------

    def build_contact_review_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.contact_bucket_box = QComboBox()
        self.contact_bucket_box.addItem("Confirmed contacts", "manager_contacts")
        self.contact_bucket_box.addItem("Contact leads", "contact_leads")
        self.contact_bucket_box.addItem("Debug candidates", "contact_debug_candidates")
        self.contact_bucket_box.currentIndexChanged.connect(self.refresh_contact_tables)

        self.contact_table = QTableWidget()
        self.contact_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.contact_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        buttons = QHBoxLayout()

        confirm_btn = QPushButton("Move To Confirmed")
        lead_btn = QPushButton("Move To Leads")
        debug_btn = QPushButton("Move To Debug")
        reject_btn = QPushButton("Reject")
        open_btn = QPushButton("Open Source")

        confirm_btn.clicked.connect(lambda: self.move_selected_contact("manager_contacts"))
        lead_btn.clicked.connect(lambda: self.move_selected_contact("contact_leads"))
        debug_btn.clicked.connect(lambda: self.move_selected_contact("contact_debug_candidates"))
        reject_btn.clicked.connect(lambda: self.set_selected_contact_status("rejected"))
        open_btn.clicked.connect(lambda: self.open_url_from_table(self.contact_table, "source_url"))

        buttons.addWidget(confirm_btn)
        buttons.addWidget(lead_btn)
        buttons.addWidget(debug_btn)
        buttons.addWidget(reject_btn)
        buttons.addWidget(open_btn)

        layout.addWidget(self.contact_bucket_box)
        layout.addWidget(self.contact_table)
        layout.addLayout(buttons)

        self.tabs.addTab(tab, "Contact Review")

    def selected_contact_identity(self):
        row = self.selected_table_row(self.contact_table)

        if row < 0:
            return None

        hotel_index = int(self.contact_table.item(row, 0).text())
        contact_index = int(self.contact_table.item(row, 1).text())
        bucket = self.contact_table.item(row, 2).text()

        return hotel_index, bucket, contact_index

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

        self.refresh_all_tables()

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

        self.refresh_all_tables()

    # -----------------------------
    # Purge tab
    # -----------------------------

    def build_purge_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        path_row = QHBoxLayout()

        self.purge_path_label = QLabel(str(self.purge_path))

        open_purge_btn = QPushButton("Open Purge File")
        save_purge_btn = QPushButton("Save Purge File")

        open_purge_btn.clicked.connect(self.open_purge_file)
        save_purge_btn.clicked.connect(self.save_current_purge)

        path_row.addWidget(QLabel("Active purge list:"))
        path_row.addWidget(self.purge_path_label, 1)
        path_row.addWidget(open_purge_btn)
        path_row.addWidget(save_purge_btn)

        form_box = QGroupBox("Add Purge Rule")
        form = QFormLayout(form_box)

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

        add_purge_btn = QPushButton("Add Rule")
        add_purge_btn.clicked.connect(self.add_purge_rule)

        form.addRow("Rule Type", self.purge_type_box)
        form.addRow("Value", self.purge_value_input)
        form.addRow("Reason", self.purge_reason_input)
        form.addRow(add_purge_btn)

        self.purge_view = QTextEdit()
        self.purge_view.setReadOnly(True)

        layout.addLayout(path_row)
        layout.addWidget(form_box)
        layout.addWidget(QLabel("Current purge list"))
        layout.addWidget(self.purge_view)

        self.tabs.addTab(tab, "Purge List")

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

    def save_current_purge(self):
        purge_list = load_purge_list(self.purge_path)
        save_purge_list(purge_list, self.purge_path)
        self.show_info("Purge list saved.")

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

        export_hotels_btn = QPushButton("Export Hotels CSV")
        export_contacts_btn = QPushButton("Export Confirmed Contacts CSV")
        export_leads_btn = QPushButton("Export Contact Leads CSV")
        open_exports_btn = QPushButton("Open Exports Folder")

        export_hotels_btn.clicked.connect(self.export_hotels)
        export_contacts_btn.clicked.connect(self.export_contacts)
        export_leads_btn.clicked.connect(self.export_leads)
        open_exports_btn.clicked.connect(lambda: webbrowser.open(str(Path("exports").resolve())))

        layout.addWidget(export_hotels_btn)
        layout.addWidget(export_contacts_btn)
        layout.addWidget(export_leads_btn)
        layout.addWidget(open_exports_btn)
        layout.addStretch()

        self.tabs.addTab(tab, "Export")

    def export_hotels(self):
        path = export_hotels_csv(self.hotels)
        self.show_info(f"Exported hotels to:\n{path}")

    def export_contacts(self):
        path = export_contacts_csv(self.hotels)
        self.show_info(f"Exported contacts to:\n{path}")

    def export_leads(self):
        path = export_leads_csv(self.hotels)
        self.show_info(f"Exported leads to:\n{path}")

    # -----------------------------
    # Refresh tables
    # -----------------------------

    def refresh_all_tables(self):
        self.refresh_cache_table()
        self.refresh_hotel_table()
        self.refresh_contact_tables()
        self.refresh_purge_view()

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

    def refresh_cache_table(self):
        rows = get_hotel_summary_rows(self.hotels)
        self.fill_table(self.cache_table, rows)

    def refresh_hotel_table(self):
        rows = get_hotel_summary_rows(self.hotels)
        self.fill_table(self.hotel_table, rows)

    def refresh_contact_tables(self):
        bucket = self.contact_bucket_box.currentData() if hasattr(self, "contact_bucket_box") else "manager_contacts"
        rows = get_contact_rows(self.hotels, bucket)
        self.fill_table(self.contact_table, rows)

    def refresh_purge_view(self):
        purge_list = load_purge_list(self.purge_path)

        import json
        self.purge_view.setPlainText(json.dumps(purge_list, indent=4, ensure_ascii=False))

    # -----------------------------
    # Pipeline execution
    # -----------------------------

    def start_pipeline_task(self, task_name: str):
        self.save_current_setup()

        settings = self.get_current_settings_from_ui()
        roles = self.get_roles_from_ui()

        if not roles:
            self.show_error("Add at least one target role.")
            return

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
        self.refresh_all_tables()

        self.append_log("Pipeline finished and cache saved.")
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