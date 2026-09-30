"""CLA desktop: local evidence, exact launch previews, explicit consent."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import threading

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QSplitter, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

STYLE = """
QMainWindow, QWidget { background:#101824; color:#e4ebf5; font-size:13px; }
QLabel { background:transparent; }
QLabel#Brand { font-size:27px; font-weight:700; color:#f8fafc; }
QLabel#Subtitle, QLabel#Muted { color:#a3b5cc; font-size:12px; }
QLabel#Eyebrow { color:#60ddc1; font-size:11px; font-weight:700; }
QLabel#DemoBanner { color:#ffd895; background:#4b351d; border:1px solid #986b33;
 border-radius:7px; padding:10px; font-weight:700; }
QLabel#Freshness { color:#d4b679; background:#292c2f; padding:9px; border-radius:6px; }
QLabel#Metric { font-size:27px; font-weight:700; color:#69e0c4; }
QFrame#Card { background:#182333; border:1px solid #2b3b50; border-radius:9px; }
QGroupBox { border:1px solid #2d3e52; border-radius:8px; margin-top:20px; padding:16px 12px 12px; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 6px; color:#d4e2f1; font-weight:600; }
QTabWidget::pane { border:1px solid #2b3b50; border-radius:8px; padding:5px; }
QTabBar::tab { background:#172232; color:#9fb0c7; border:1px solid #2b3b50;
 padding:11px 21px; margin-right:3px; border-top-left-radius:6px; border-top-right-radius:6px; }
QTabBar::tab:selected { color:#86ead3; background:#203143; border-bottom:2px solid #60ddc1; }
QPushButton { background:#233449; border:1px solid #3c506b; border-radius:6px; padding:8px 13px; font-weight:600; }
QPushButton:hover { background:#304961; border-color:#70c7b5; }
QPushButton:disabled { color:#67778b; background:#192332; border-color:#26364a; }
QPushButton#Primary { background:#70dfc2; color:#10251f; border:1px solid #9aedd8; }
QPushButton#Primary:disabled { color:#728981; background:#294b43; border-color:#36594f; }
QLineEdit, QPlainTextEdit, QComboBox { background:#0c1420; border:1px solid #33465d;
 border-radius:5px; padding:7px; selection-background-color:#376d70; color:#e4ebf5; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border:1px solid #70dfc2; }
QComboBox::drop-down { border:0; width:24px; }
QComboBox QAbstractItemView { background:#182638; color:#e4ebf5; selection-background-color:#315369; }
QTableWidget { background:#101a28; alternate-background-color:#162334; border:1px solid #2b3b50;
 gridline-color:#253448; selection-background-color:#284953; selection-color:#f0fffb; }
QHeaderView::section { background:#203044; color:#a9c0d7; padding:9px 6px; border:0; font-weight:600; }
QTableCornerButton::section { background:#203044; border:0; }
QCheckBox { spacing:8px; }
QCheckBox::indicator { width:17px; height:17px; }
QProgressBar { background:#172536; border:0; border-radius:4px; max-height:7px; }
QProgressBar::chunk { background:#67d8bd; border-radius:4px; }
QScrollArea { border:0; }
QToolTip { background:#23364b; color:#fff; border:1px solid #47627c; }
"""


def field(value, key, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def display(value):
    if value is None:
        return "—"
    if hasattr(value, "value"):
        value = value.value
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def encoded(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: encoded(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encoded(item) for item in value]
    if isinstance(value, (datetime, Path)):
        return str(value)
    if hasattr(value, "__dict__"):
        return {key: encoded(item) for key, item in vars(value).items() if not key.startswith("_")}
    return value


def pretty(value):
    return json.dumps(encoded(value), indent=2, ensure_ascii=False, default=str)


def as_date(value):
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (ValueError, TypeError):
        return None


def label(text, name="Muted"):
    result = QLabel(text)
    result.setObjectName(name)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setWordWrap(True)
    return result


def button(text, callback, primary=False):
    result = QPushButton(text)
    result.clicked.connect(callback)
    if primary:
        result.setObjectName("Primary")
    return result


def readonly(placeholder, name=None):
    result = QPlainTextEdit()
    result.setReadOnly(True)
    result.setPlaceholderText(placeholder)
    if name:
        result.setAccessibleName(name)
    return result


class ScanWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, service, project, probes, cancel):
        super().__init__()
        self.service, self.project, self.probes, self.cancel = service, project, probes, cancel

    @Slot()
    def run(self):
        try:
            result = self.service.scan(project=self.project, allow_probes=self.probes, cancel=self.cancel, force=True)
            if not self.cancel.is_set():
                self.succeeded.emit(result)
        except Exception as exc:
            if not self.cancel.is_set():
                self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    """Injected services keep UI tests entirely local, with no executable probes."""

    def __init__(self, settings, discovery, launcher, briefing_builder, *, snapshot=None,
                 demo=False, save_settings=None, candidates=None, integration=None,
                 history_directory=None, request_factory=None, shortcut_factory=None):
        super().__init__()
        self.settings, self.discovery, self.launcher = settings, discovery, launcher
        self.briefing_builder = briefing_builder
        self.save_settings_callback = save_settings or (lambda _settings: None)
        self.candidates = candidates or (lambda _name: [])
        self.integration, self.history_directory = integration, history_directory
        self.request_factory, self.shortcut_factory = request_factory, shortcut_factory
        self.snapshot = None
        self.demo = bool(demo or field(snapshot, "demo", False))
        self.prepared, self.exact_prompt = None, ""
        self._scan_thread = self._scan_worker = self._scan_cancel = None
        self._snapshot_project = self._scan_project = None
        self._close_pending = self._launch_in_progress = False
        self._capabilities = []
        self._integration_plan = None
        self._active_status_path = None
        self._last_launch_status = None
        self.setWindowTitle("Codex Launcher Awarness · CLA 0.1.0 experimental")
        self.resize(1250, 890)
        self.setMinimumSize(920, 650)
        self.setStyleSheet(STYLE)
        self._build()
        self._restore()
        self._connect_invalidation()
        self._actions()
        self.freshness_timer = QTimer(self)
        self.freshness_timer.timeout.connect(self.update_freshness)
        self.freshness_timer.start(1000)
        self.history_timer = QTimer(self)
        self.history_timer.timeout.connect(lambda: self.refresh_history() if self.tabs.currentIndex() == 4 else None)
        self.history_timer.start(3000)
        self.launch_timer = QTimer(self)
        self.launch_timer.timeout.connect(self.poll_launch_status)
        self.launch_timer.start(1000)
        if snapshot is not None:
            self.set_snapshot(snapshot)
        self.refresh_history()

    def _build(self):
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(25, 19, 25, 18)
        outer.setSpacing(12)
        heading = QHBoxLayout()
        brand = QVBoxLayout()
        brand.addWidget(label("CLA  /  LOCAL CONTEXT, DELIBERATE LAUNCHES", "Eyebrow"))
        brand.addWidget(label("Codex Launcher Awarness", "Brand"))
        brand.addWidget(label("Inspect what is available. Review what will be shared. Start on your terms.", "Subtitle"))
        heading.addLayout(brand, 1)
        heading.addWidget(label("EXPERIMENTAL\n0.1.0", "Subtitle"))
        outer.addLayout(heading)
        self.demo_banner = label("DEMO DATA · SYNTHETIC INVENTORY · NO HOST PROBES · START DISABLED", "DemoBanner")
        self.demo_banner.setVisible(self.demo)
        outer.addWidget(self.demo_banner)
        self.freshness_label = label("No evidence collected. Choose a project, then inspect the local inventory.", "Freshness")
        outer.addWidget(self.freshness_label)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._dashboard(), "&Dashboard")
        self.tabs.addTab(self._engines(), "&Engines")
        self.tabs.addTab(self._launch(), "&Launch")
        self.tabs.addTab(self._integration(), "&Integration")
        self.tabs.addTab(self._history(), "&History")
        outer.addWidget(self.tabs, 1)
        footer = QHBoxLayout()
        self.status_label = label("Local preview only. No cloud request has been made.")
        footer.addWidget(self.status_label, 1)
        self.scan_button = button("Inspect &inventory", self.start_scan, True)
        self.cancel_button = button("Cancel scan", self.cancel_scan)
        self.cancel_button.setEnabled(False)
        footer.addWidget(self.scan_button)
        footer.addWidget(self.cancel_button)
        outer.addLayout(footer)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        outer.addWidget(self.progress)
        self.setCentralWidget(central)
        if self.demo:
            self.scan_button.setText("Synthetic demo")
            self.scan_button.setEnabled(False)

    @staticmethod
    def _scroll(widget):
        result = QScrollArea()
        result.setWidgetResizable(True)
        result.setWidget(widget)
        return result

    @staticmethod
    def _table(headers):
        result = QTableWidget(0, len(headers))
        result.setHorizontalHeaderLabels(headers)
        result.setAlternatingRowColors(True)
        result.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        result.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        result.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        result.verticalHeader().setVisible(False)
        result.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        result.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        result.setWordWrap(False)
        return result

    def _dashboard(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        cards = QHBoxLayout()
        self.hardware_labels, self.hardware_notes = {}, {}
        for key, title, note in (
            ("cpu", "CPU", "Model, logical processors, and sampled utilization"),
            ("memory", "RAM available / total", "Observed memory, not a reservation"),
            ("gpu", "GPU memory free / total", "Aggregate device VRAM; unknown until checked"),
            ("storage", "Selected volume", "Choose a project to inspect its storage"),
        ):
            card = QFrame()
            card.setObjectName("Card")
            content = QVBoxLayout(card)
            content.setContentsMargins(15, 11, 15, 11)
            content.addWidget(QLabel(title))
            number = label("—", "Metric")
            self.hardware_labels[key] = number
            content.addWidget(number)
            detail = label(note)
            self.hardware_notes[key] = detail
            content.addWidget(detail)
            cards.addWidget(card)
        layout.addLayout(cards)
        counts = QHBoxLayout()
        self.metric_labels = {}
        for key, title in (("total", "Capabilities"), ("verified", "Verified ready"),
                           ("attention", "Needs attention"), ("trust", "Approved executables")):
            counts.addWidget(label(title + ":"))
            self.metric_labels[key] = QLabel("—")
            counts.addWidget(self.metric_labels[key])
            counts.addSpacing(10)
        counts.addStretch()
        layout.addLayout(counts)
        layout.addWidget(label("Installation, configuration, reachability, and readiness are separate observations. "
                               "Unknown means not checked; it does not mean ready."))
        split = QSplitter(Qt.Orientation.Vertical)
        self.capability_table = self._table(["Capability", "Installed", "Configured", "Reachable", "Readiness", "Version", "Observed"])
        self.capability_table.itemSelectionChanged.connect(self.show_capability_details)
        self.evidence_details = readonly("Select a capability to inspect its evidence, values, units, limitations, and expiry.",
                                         "Selected capability evidence")
        split.addWidget(self.capability_table)
        split.addWidget(self.evidence_details)
        split.setSizes([300, 145])
        layout.addWidget(split, 1)
        return panel

    def _engines(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(label("PATH candidates are not executed automatically. Approve exact paths, then explicitly permit probes. "
                               "Missing Codex does not prevent inventory inspection."))
        group = QGroupBox("Executable candidates and explicit trust")
        form = QFormLayout(group)
        self.executable_fields = {}
        names = (("codex", "Codex CLI"), ("powershell", "PowerShell 7"), ("conda", "Conda (optional)"),
                 ("python", "Python (optional)"), ("blender", "Blender (optional)"),
                 ("maxima", "Maxima (optional)"), ("nvidia_smi", "NVIDIA SMI (optional)"))
        for key, title in names:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            choice = QComboBox()
            choice.setEditable(True)
            choice.setMinimumContentsLength(25)
            choice.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            choice.setAccessibleName(title + " executable path")
            choice.addItem("")
            if not self.demo:
                try:
                    for item in self.candidates(key):
                        if field(item, "path"):
                            choice.addItem(str(field(item, "path")))
                except Exception:
                    pass
            row_layout.addWidget(choice, 1)
            row_layout.addWidget(button("Browse…", lambda _checked=False, name=key: self.browse_executable(name)))
            self.executable_fields[key] = choice
            form.addRow(title, row)
        self.trust_button = button("Approve selected executable paths", self.approve_executables)
        self.trust_button.setEnabled(not self.demo)
        form.addRow("", self.trust_button)
        self.allow_probes = QCheckBox("Allow bounded probes of approved executables on inventory scans")
        self.allow_probes.setEnabled(not self.demo)
        self.allow_probes.toggled.connect(self.change_probe_approval)
        form.addRow("", self.allow_probes)
        layout.addWidget(group)
        extra = QGroupBox("Optional local engine configuration")
        extra_form = QFormLayout(extra)
        self.conda_env = QLineEdit()
        self.conda_env.setPlaceholderText("Conda environment name; activated only in the new launch terminal")
        extra_form.addRow("Conda environment", self.conda_env)
        self.python_environments = QPlainTextEdit()
        self.python_environments.setMaximumHeight(75)
        self.python_environments.setPlaceholderText("One existing absolute environment path per line")
        extra_form.addRow("Python environments", self.python_environments)
        self.local_endpoints = QPlainTextEdit()
        self.local_endpoints.setMaximumHeight(75)
        self.local_endpoints.setPlaceholderText("Loopback HTTP origins, one per line; e.g. http://127.0.0.1:8000")
        extra_form.addRow("Local endpoints", self.local_endpoints)
        save = button("Save local settings", self.save_engine_settings)
        save.setEnabled(not self.demo)
        extra_form.addRow("", save)
        layout.addWidget(extra)
        layout.addStretch()
        return self._scroll(panel)

    def _launch(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        group = QGroupBox("1 · Select and approve the project")
        content = QVBoxLayout(group)
        row = QHBoxLayout()
        self.project_path = QLineEdit()
        self.project_path.setPlaceholderText("First run: choose a local project folder…")
        self.project_path.setAccessibleName("Project folder")
        row.addWidget(self.project_path, 1)
        row.addWidget(button("Choose project…", self.browse_project))
        content.addLayout(row)
        self.project_trust = label("Choose and approve a project root before preparing a launch.")
        content.addWidget(self.project_trust)
        self.approve_project_button = button("Approve this project root", self.approve_project)
        self.approve_project_button.setEnabled(not self.demo)
        content.addWidget(self.approve_project_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(group)
        group = QGroupBox("2 · Describe the task and review the exact launch context")
        content = QVBoxLayout(group)
        self.task_input = QPlainTextEdit()
        self.task_input.setPlaceholderText("What should Codex work on in this project?")
        self.task_input.setAccessibleName("Task for Codex")
        self.task_input.setMinimumHeight(70)
        self.task_input.setMaximumHeight(105)
        content.addWidget(self.task_input)
        row = QHBoxLayout()
        self.relevance_filter = QComboBox()
        self.relevance_filter.addItems(["general", "coding", "symbolic-math", "blender", "gpu"])
        self.relevance_filter.setAccessibleName("Context relevance filter")
        row.addWidget(QLabel("Context"))
        row.addWidget(self.relevance_filter)
        self.permission_mode = QComboBox()
        self.permission_mode.addItem("Inherit existing Codex configuration", "inherit")
        self.permission_mode.addItem("Full access · disable sandbox and approvals", "full-access-no-approval")
        self.permission_mode.setAccessibleName("Codex permission mode")
        row.addWidget(self.permission_mode, 1)
        content.addLayout(row)
        row = QHBoxLayout()
        self.profile_input = QLineEdit()
        self.profile_input.setPlaceholderText("Codex profile (optional)")
        self.profile_input.setAccessibleName("Codex profile")
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("Codex model (optional)")
        self.model_input.setAccessibleName("Codex model")
        row.addWidget(self.profile_input)
        row.addWidget(self.model_input)
        content.addLayout(row)
        self.permission_note = label("Default: CLA adds no permission override; Codex uses its existing configuration.")
        content.addWidget(self.permission_note)
        self.allow_elevated = QCheckBox("Allow administrator rights for this terminal (explicit)")
        self.allow_elevated.setChecked(False)
        self.allow_elevated.setEnabled(not self.demo)
        self.allow_elevated.setToolTip("Separate from Codex sandbox permissions. Leave unchecked for a normal user terminal. "
                                      "If this desktop is elevated, launching is blocked unless you explicitly permit inheritance.")
        content.addWidget(self.allow_elevated)
        row = QHBoxLayout()
        self.preview_button = button("Prepare exact preview", self.prepare_preview)
        self.export_button = button("Export shown prompt…", self.export_preview)
        self.export_button.setEnabled(False)
        row.addWidget(self.preview_button)
        row.addWidget(self.export_button)
        row.addStretch()
        content.addLayout(row)
        self.prompt_preview = readonly("The exact task and context sent to Codex will appear here. Preparing a preview is local only.",
                                        "Exact prompt sent to Codex")
        self.prompt_preview.setMinimumHeight(160)
        content.addWidget(self.prompt_preview)
        self.command_preview = readonly("Validated terminal launch details", "Exact launch command")
        self.command_preview.setMinimumHeight(110)
        self.command_preview.setMaximumHeight(180)
        content.addWidget(self.command_preview)
        layout.addWidget(group)
        group = QGroupBox("3 · Decide what to share, then start")
        content = QVBoxLayout(group)
        self.privacy_ack = QCheckBox("I understand Start shares the shown task and context with my configured Codex service.")
        self.privacy_ack.toggled.connect(self.update_start_enabled)
        content.addWidget(self.privacy_ack)
        content.addWidget(label("The preview can contain local paths and machine metadata. Review it before starting. "
                                "Preview and export stay local. Closing CLA leaves Codex terminals running."))
        self.start_button = button("Start Codex in a new PowerShell 7 terminal", self.start_codex, True)
        self.start_button.setEnabled(False)
        content.addWidget(self.start_button)
        self.launch_status_label = label("No terminal has been started by CLA.")
        content.addWidget(self.launch_status_label)
        layout.addWidget(group)
        return self._scroll(panel)

    def _integration(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(label("Optional integration changes only the reviewed CLA-owned entry. "
                               "Choose its scope explicitly and review the proposed configuration before applying."))
        row = QHBoxLayout()
        self.integration_scope = QComboBox()
        self.integration_scope.addItem("Selected project only", "project")
        self.integration_scope.addItem("Current user Codex MCP configuration", "user")
        self.integration_scope.currentIndexChanged.connect(self.invalidate_integration)
        row.addWidget(self.integration_scope)
        self.integration_preview_button = button("Preview integration", self.preview_integration)
        self.integration_apply_button = button("Apply reviewed integration", self.apply_integration)
        self.integration_apply_button.setEnabled(False)
        self.integration_remove_button = button("Remove CLA-owned integration", self.remove_integration)
        self.integration_remove_button.setEnabled(not self.demo)
        for item in (self.integration_preview_button, self.integration_apply_button, self.integration_remove_button):
            row.addWidget(item)
        layout.addLayout(row)
        self.integration_preview = readonly("Choose a project in Launch, then preview the exact integration plan.", "Integration changes")
        layout.addWidget(self.integration_preview, 1)
        self.shortcut_button = button("Create CLA desktop shortcut", self.create_shortcut)
        self.shortcut_button.setEnabled(not self.demo)
        layout.addWidget(self.shortcut_button, 0, Qt.AlignmentFlag.AlignLeft)
        return panel

    def _history(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        row = QHBoxLayout()
        row.addWidget(label("Local launch metadata only. CLA does not load full Codex conversations."), 1)
        row.addWidget(button("Refresh history", self.refresh_history))
        layout.addLayout(row)
        self.history_table = self._table(["Session", "Created", "Status", "Project"])
        layout.addWidget(self.history_table, 1)
        self.history_note = label("No sessions recorded by CLA.")
        layout.addWidget(self.history_note)
        return panel

    def _actions(self):
        for shortcut, callback, title in (("Ctrl+R", self.start_scan, "Inspect inventory"),
                                          ("Ctrl+L", lambda: self.tabs.setCurrentIndex(2), "Open launch tab"),
                                          ("Escape", self.cancel_scan, "Cancel scan")):
            action = QAction(title, self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            self.addAction(action)

    def _restore(self):
        trusted = field(self.settings, "trusted_executables", {}) or {}
        for key, choice in self.executable_fields.items():
            choice.setCurrentText(str(trusted.get(key, "")))
        roots = field(self.settings, "approved_project_roots", []) or []
        if roots:
            self.project_path.setText(str(roots[0]))
        self.python_environments.setPlainText("\n".join(map(str, field(self.settings, "python_environments", []) or [])))
        self.local_endpoints.setPlainText("\n".join(map(str, field(self.settings, "local_endpoints", []) or [])))
        self.allow_probes.blockSignals(True)
        self.allow_probes.setChecked(bool(field(self.settings, "probe_enabled", False)) and not self.demo)
        self.allow_probes.blockSignals(False)
        self.update_project_trust()
        self.metric_labels["trust"].setText(str(len(trusted)))

    def _connect_invalidation(self):
        for widget in (self.project_path, self.profile_input, self.model_input, self.conda_env):
            widget.textChanged.connect(self.invalidate_preview)
        self.project_path.textChanged.connect(self.update_project_trust)
        self.project_path.textChanged.connect(self.invalidate_integration)
        self.project_path.textChanged.connect(self.update_freshness)
        self.task_input.textChanged.connect(self.invalidate_preview)
        self.relevance_filter.currentIndexChanged.connect(self.invalidate_preview)
        self.permission_mode.currentIndexChanged.connect(self.invalidate_preview)
        self.allow_elevated.toggled.connect(self.invalidate_preview)
        for choice in self.executable_fields.values():
            choice.currentTextChanged.connect(self.invalidate_preview)

    def invalidate_preview(self, *_args):
        self.prepared = None
        self.exact_prompt = ""
        self.prompt_preview.clear()
        self.command_preview.clear()
        self.privacy_ack.setChecked(False)
        self.export_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self._launch_in_progress = False
        self.start_button.setText("Start Codex in a new PowerShell 7 terminal")
        if self.permission_mode.currentData() == "full-access-no-approval":
            self.permission_note.setText("Full access explicitly disables Codex's sandbox and approval prompts. "
                                         "Codex can access files and run commands with your account's permissions.")
        else:
            self.permission_note.setText("Default: CLA adds no permission override; Codex uses its existing configuration.")

    def invalidate_integration(self, *_args):
        self._integration_plan = None
        if hasattr(self, "integration_apply_button"):
            self.integration_apply_button.setEnabled(False)
        if hasattr(self, "integration_preview"):
            self.integration_preview.clear()

    def _save_updates(self, **updates):
        if self.demo:
            raise ValueError("Demo mode cannot save host settings.")
        if hasattr(self.settings, "model_dump"):
            candidate = type(self.settings).model_validate({**self.settings.model_dump(), **updates})
        else:
            from copy import copy
            candidate = copy(self.settings)
            for key, value in updates.items():
                setattr(candidate, key, value)
        self.save_settings_callback(candidate)
        # Preserve the settings identity shared by the discovery and launch services.
        for key, value in updates.items():
            setattr(self.settings, key, value)

    def update_project_trust(self, *_args):
        raw = self.project_path.text().strip()
        if not raw:
            self.project_trust.setText("First run: choose a project folder and explicitly approve its root.")
            return
        try:
            project = Path(raw).resolve()
            approved = any(project.is_relative_to(Path(root).resolve())
                           for root in field(self.settings, "approved_project_roots", []) or [])
        except (OSError, ValueError):
            approved = False
        self.project_trust.setText("Project is inside an approved root." if approved else "This project has not been approved.")

    def browse_project(self):
        selected = QFileDialog.getExistingDirectory(self, "Choose the Codex project folder", self.project_path.text())
        if selected:
            self.project_path.setText(selected)
            self.tabs.setCurrentIndex(2)

    def browse_executable(self, key):
        selected, _ = QFileDialog.getOpenFileName(self, "Select an exact executable to approve", "",
                                                "Executables (*.exe *.cmd *.bat);;All files (*)")
        if selected:
            self.executable_fields[key].setCurrentText(selected)
            self.status_label.setText("Path selected. Click Approve selected executable paths before probing or launching.")

    def approve_executables(self):
        if self.demo:
            return
        try:
            trusted = dict(field(self.settings, "trusted_executables", {}) or {})
            for key, choice in self.executable_fields.items():
                trusted.pop(key, None)
                raw = choice.currentText().strip()
                if raw:
                    path = Path(raw)
                    if not path.is_absolute() or not path.is_file():
                        raise ValueError(f"{key}: choose an existing absolute executable path.")
                    trusted[key] = str(path.resolve())
            self._save_updates(trusted_executables=trusted)
            self.metric_labels["trust"].setText(str(len(trusted)))
            self.invalidate_preview()
            self.status_label.setText("Exact executable paths approved locally. Bounded probes require the separate checkbox.")
        except Exception as exc:
            self.show_error("Could not approve executables", exc)

    def change_probe_approval(self, checked):
        if self.demo:
            return
        try:
            self._save_updates(probe_enabled=bool(checked))
            self.invalidate_preview()
            self.status_label.setText("Bounded probes of approved executables " + ("enabled." if checked else "disabled."))
        except Exception as exc:
            self.allow_probes.blockSignals(True)
            self.allow_probes.setChecked(bool(field(self.settings, "probe_enabled", False)))
            self.allow_probes.blockSignals(False)
            self.show_error("Could not save probe approval", exc)

    def approve_project(self):
        if self.demo:
            return
        try:
            project = self.selected_project(required=True)
            roots = list(field(self.settings, "approved_project_roots", []) or [])
            if str(project) not in roots:
                roots.append(str(project))
            self._save_updates(approved_project_roots=roots)
            self.update_project_trust()
            self.status_label.setText("Project root approved in CLA's local settings.")
        except Exception as exc:
            self.show_error("Could not approve project", exc)

    def save_engine_settings(self):
        if self.demo:
            return
        try:
            self._save_updates(
                python_environments=[line.strip() for line in self.python_environments.toPlainText().splitlines() if line.strip()],
                local_endpoints=[line.strip() for line in self.local_endpoints.toPlainText().splitlines() if line.strip()])
            self.invalidate_preview()
            self.status_label.setText("Local engine settings saved. Inspect inventory to refresh evidence.")
        except Exception as exc:
            self.show_error("Could not save local settings", exc)

    def selected_project(self, required=False):
        raw = self.project_path.text().strip()
        if not raw:
            if required:
                raise ValueError("Choose a project folder in Launch first.")
            return None
        path = Path(raw)
        if not path.is_absolute() or not path.is_dir():
            raise ValueError("The project must be an existing absolute directory.")
        return path.resolve()

    def start_scan(self):
        if self.demo or self._scan_thread is not None:
            return
        try:
            project = self.selected_project()
        except Exception as exc:
            self.show_error("Cannot inspect project", exc)
            return
        self.invalidate_preview()
        self._scan_cancel = threading.Event()
        self._scan_project = str(project) if project is not None else None
        self._scan_thread = QThread(self)
        self._scan_worker = ScanWorker(self.discovery, project, self.allow_probes.isChecked(), self._scan_cancel)
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.succeeded.connect(self.set_snapshot)
        self._scan_worker.failed.connect(self.scan_failed)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.finished.connect(self._scan_worker.deleteLater)
        self._scan_thread.finished.connect(self.scan_finished)
        self.scan_button.setEnabled(False)
        self.preview_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.tabs.setTabEnabled(1, False)
        self.progress.setRange(0, 0)
        self.status_label.setText("Inspecting local evidence… Cancel keeps the last completed snapshot.")
        self._scan_thread.start()

    def cancel_scan(self):
        if self._scan_cancel is not None:
            self._scan_cancel.set()
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Cancelling scan… waiting for the current bounded probe to stop.")

    @Slot(str)
    def scan_failed(self, message):
        self.status_label.setText("Inventory scan failed: " + message)

    @Slot()
    def scan_finished(self):
        cancelled = self._scan_cancel is not None and self._scan_cancel.is_set()
        thread = self._scan_thread
        self._scan_thread = self._scan_worker = self._scan_cancel = None
        if thread is not None:
            thread.deleteLater()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.scan_button.setEnabled(not self.demo)
        self.preview_button.setEnabled(True)
        self.tabs.setTabEnabled(1, True)
        self.cancel_button.setEnabled(False)
        if cancelled:
            self.status_label.setText("Scan cancelled. Previous completed evidence is unchanged.")
        if self._close_pending:
            self.close()

    @Slot(object)
    def set_snapshot(self, snapshot):
        if bool(field(snapshot, "demo", False)) and not self.demo:
            self.demo = True
            self.demo_banner.show()
            self.scan_button.setEnabled(False)
            self.trust_button.setEnabled(False)
            self.approve_project_button.setEnabled(False)
            self.integration_remove_button.setEnabled(False)
            self.shortcut_button.setEnabled(False)
        self.snapshot = snapshot
        self._snapshot_project = self._scan_project if self._scan_thread is not None else self.project_key()
        self.invalidate_preview()
        self._capabilities = list(field(snapshot, "capabilities", []) or [])
        self.capability_table.setRowCount(len(self._capabilities))
        for row, capability in enumerate(self._capabilities):
            observed = as_date(field(capability, "observed_at"))
            values = (field(capability, "id"), field(capability, "installation"),
                      field(capability, "configuration"), field(capability, "reachability"),
                      field(capability, "readiness"), field(capability, "version"),
                      observed.strftime("%H:%M:%S UTC") if observed else "unknown")
            for column, value in enumerate(values):
                item = QTableWidgetItem(display(value))
                item.setToolTip(display(value))
                self.capability_table.setItem(row, column, item)
        self.metric_labels["total"].setText(str(len(self._capabilities)))
        self.metric_labels["trust"].setText(str(len(field(self.settings, "trusted_executables", {}) or {})))
        if self._capabilities:
            self.capability_table.selectRow(0)
        self.update_freshness()
        self.update_hardware_cards()
        self.status_label.setText("Synthetic demonstration loaded. Host discovery and launching are disabled." if self.demo else
                                 f"Local inventory updated: {len(self._capabilities)} capability records. No cloud request made.")

    def update_hardware_cards(self):
        def capability(tag):
            return next((item for item in self._capabilities if tag in (field(item, "tags", []) or [])), None)

        def numeric(value):
            return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

        def amount(value, divisor=1):
            return f"{value / divisor:.1f}" if numeric(value) else "—"

        def show(key, source, value, note):
            self.hardware_labels[key].setText(value)
            self.hardware_notes[key].setText(note)
            tip = (f"Evidence: {field(source, 'evidence_id', 'unknown')}\n"
                   f"Observed: {field(source, 'observed_at', 'unknown')}\n"
                   f"Expires: {field(source, 'expires_at', 'unknown')}\n"
                   f"Method: {field(source, 'probe_method', 'unknown')}")
            self.hardware_labels[key].setToolTip(tip)
            self.hardware_notes[key].setToolTip(tip)

        source = capability("cpu")
        values = field(source, "values", {}) or {}
        utilization = values.get("utilization_percent")
        cores = values.get("logical_count", values.get("logical_cores"))
        show("cpu", source, amount(utilization) + ("% busy" if numeric(utilization) else ""),
             f"{display(values.get('model'))} · {display(cores)} logical processors")
        source = capability("memory")
        values = field(source, "values", {}) or {}
        show("memory", source, amount(values.get("available_bytes"), 2**30) + " / " + amount(values.get("total_bytes"), 2**30) + " GiB",
             "Available RAM at the observation time")
        source = capability("gpu")
        values = field(source, "values", {}) or {}
        devices = values.get("devices") or []
        if devices:
            free_values = [item.get("memory_free_mib") for item in devices]
            total_values = [item.get("memory_total_mib") for item in devices]
            free = sum(free_values) if all(numeric(item) for item in free_values) else None
            total = sum(total_values) if all(numeric(item) for item in total_values) else None
            name = display(devices[0].get("name")) + (f" + {len(devices)-1} more" if len(devices) > 1 else "")
        else:
            free, total, name = values.get("vram_free_mib"), values.get("vram_total_mib"), display(values.get("name"))
        show("gpu", source, amount(free, 1024) + " / " + amount(total, 1024) + " GiB",
             name + " · aggregate free VRAM")
        source = capability("storage")
        values = field(source, "values", {}) or {}
        free = values.get("free_bytes")
        show("storage", source, amount(free, 2**30) + (" GiB free" if numeric(free) else ""),
             "of " + amount(values.get("total_bytes"), 2**30) + " GiB · " + display(field(source, "path")))

    def update_freshness(self):
        if self.snapshot is None:
            return
        now = datetime.now(timezone.utc)
        stale, ready = 0, 0
        for row, item in enumerate(self._capabilities):
            expiry = as_date(field(item, "expires_at"))
            expired = expiry is None or expiry <= now
            effective = "stale" if expired else field(item, "readiness", "unknown")
            stale += expired
            ready += effective == "verified"
            cell = self.capability_table.item(row, 4)
            if cell is not None:
                cell.setText(str(effective))
        self.metric_labels["verified"].setText(str(ready))
        self.metric_labels["attention"].setText(str(len(self._capabilities) - ready))
        if self.demo:
            self.freshness_label.setText("SYNTHETIC DEMO · Values illustrate the interface and are not observations of this computer.")
        elif self._snapshot_project != self.project_key():
            self.freshness_label.setText("PROJECT CHANGED · The displayed snapshot belongs to the previous project selection. "
                                         "Inspect inventory again before preparing a launch.")
        elif stale:
            self.freshness_label.setText(f"Evidence needs refresh: {stale} of {len(self._capabilities)} records are expired or lack freshness. "
                                         "Inspect inventory before relying on them.")
        else:
            self.freshness_label.setText("Evidence is within its freshness window. Readiness still depends on the individual checks shown below.")

    def project_key(self):
        raw = self.project_path.text().strip()
        if not raw:
            return None
        try:
            return str(Path(raw).resolve())
        except (OSError, ValueError):
            return raw

    def show_capability_details(self):
        row = self.capability_table.currentRow()
        if 0 <= row < len(self._capabilities):
            self.evidence_details.setPlainText(pretty(self._capabilities[row]))

    def _make_request(self):
        project = self.selected_project(required=True)
        if not any(project.is_relative_to(Path(root).resolve())
                   for root in field(self.settings, "approved_project_roots", []) or []):
            raise ValueError("Approve this project root before preparing a launch.")
        trusted = field(self.settings, "trusted_executables", {}) or {}
        required = ["codex", "powershell"]
        if self.conda_env.text().strip():
            required.append("conda")
        for key in required:
            selected = self.executable_fields[key].currentText().strip()
            if not selected or not trusted.get(key) or Path(selected).resolve() != Path(trusted[key]).resolve():
                raise ValueError(f"Approve the selected {key} executable path in Engines before preparing a launch.")
        values = {
            "project": project, "task": self.task_input.toPlainText().strip(),
            "codex_path": self.executable_fields["codex"].currentText().strip(),
            "powershell_path": self.executable_fields["powershell"].currentText().strip(),
            "conda_path": self.executable_fields["conda"].currentText().strip() or None,
            "conda_env": self.conda_env.text().strip() or None,
            "permission_mode": self.permission_mode.currentData(),
            "profile": self.profile_input.text().strip() or None,
            "model": self.model_input.text().strip() or None,
            "task_filter": self.relevance_filter.currentText(),
            "allow_elevated": self.allow_elevated.isChecked(),
        }
        if not values["task"]:
            raise ValueError("Describe the task before preparing a preview.")
        if self.request_factory is None:
            from codex_launcher_awarness.launch import LaunchRequest
            return LaunchRequest(**values)
        return self.request_factory(**values)

    def prepare_preview(self):
        self.invalidate_preview()
        try:
            if self.demo:
                # Synthetic previews never touch settings, sessions, or real launch services.
                self.exact_prompt = "SYNTHETIC DEMO — NOT SENT\n\nTask: " + (self.task_input.toPlainText().strip() or "Explain the demo inventory.") + "\n\n" + pretty(self.snapshot)
                self.prompt_preview.setPlainText(self.exact_prompt)
                self.command_preview.setPlainText("DEMO: no process will be started")
                self.prepared = {"prompt": self.exact_prompt, "demo": True}
                self.export_button.setEnabled(True)
                self.status_label.setText("Synthetic preview only. Demo cannot start Codex or change integration.")
                return
            if self.snapshot is None:
                raise ValueError("Inspect inventory first so the preview contains evidence.")
            if self._snapshot_project != self.project_key():
                raise ValueError("The project selection changed. Inspect inventory again before preparing a launch.")
            request = self._make_request()
            # The manager binds the briefing and immutable snapshot to one new session ID.
            self.prepared = self.launcher.prepare(request, self.snapshot)
            self.exact_prompt = str(field(self.prepared, "prompt", ""))
            if not self.exact_prompt:
                raise ValueError("Launch preparation supplied no exact prompt. Launch is blocked.")
            self.prompt_preview.setPlainText(self.exact_prompt)
            details = {"launch_route": field(self.prepared, "preview", {}),
                       "terminal_command": field(self.prepared, "command", []),
                       "warnings": field(self.prepared, "warnings", [])}
            self.command_preview.setPlainText(pretty(details))
            self.export_button.setEnabled(True)
            self.status_label.setText("Exact preview prepared locally. Review it, then acknowledge sharing to enable Start.")
            self.update_start_enabled()
        except Exception as exc:
            self.prepared = None
            self.show_error("Cannot prepare launch", exc)

    def update_start_enabled(self, *_args):
        self.start_button.setEnabled(bool(self.prepared is not None and self.privacy_ack.isChecked()
                                          and not self.demo and not self._launch_in_progress))

    def start_codex(self):
        if self.demo or self.prepared is None or not self.privacy_ack.isChecked() or self._launch_in_progress:
            return
        self._launch_in_progress = True
        self.start_button.setEnabled(False)
        self.start_button.setText("Starting one Codex terminal…")
        try:
            result = self.launcher.launch(self.prepared)
            lifecycle_path = field(result, "lifecycle_path")
            self._active_status_path = Path(lifecycle_path) if lifecycle_path else None
            self._last_launch_status = None
            self.start_button.setText("Terminal started · prepare a new preview to launch again")
            self.status_label.setText("Codex terminal started. Closing CLA leaves it running. " + display(field(result, "status", "started")))
            self.launch_status_label.setText("Terminal created; waiting for bootstrap lifecycle status. This does not confirm a model response.")
            self.refresh_history()
        except Exception as exc:
            self.prepared = None
            self.start_button.setText("Launch did not complete · prepare a new preview")
            self.launch_status_label.setText("Launch failed: " + str(exc))
            self.show_error("Could not start Codex", exc)

    def poll_launch_status(self):
        path = self._active_status_path
        if self.demo or path is None:
            return
        try:
            if path.name != "status.json" or (self.history_directory is not None and
                    not path.resolve().is_relative_to(Path(self.history_directory).resolve())):
                return
            if path.stat().st_size > 131072:
                return
            status = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(status, dict) or status == self._last_launch_status:
                return
            self._last_launch_status = status
            phase = status.get("status", "unknown")
            code = status.get("exit_code")
            failed = phase == "failed" or (code is not None and str(code) != "0")
            if failed:
                reason = status.get("error", status.get("reason", status.get("message", "See local session metadata.")))
                message = f"Codex session failed · exit code {display(code)} · {display(reason)}"
                self.status_label.setText(message)
            else:
                message = f"Codex session status: {phase}" + (f" · exit code {code}" if code is not None else "")
            self.launch_status_label.setText(message)
        except (OSError, ValueError, TypeError):
            # Atomic lifecycle updates may briefly race reads; the next tick retries.
            return

    def export_preview(self):
        if self.prepared is None or not self.exact_prompt:
            return
        selected, _ = QFileDialog.getSaveFileName(self, "Export the exact shown prompt locally", "cla-prompt.txt", "Text files (*.txt)")
        if selected:
            try:
                Path(selected).write_text(self.exact_prompt, encoding="utf-8")
                self.status_label.setText("The exact shown prompt was exported locally. No cloud request made.")
            except OSError as exc:
                self.show_error("Could not export preview", exc)

    def preview_integration(self):
        self.invalidate_integration()
        try:
            if self.demo:
                self.integration_preview.setPlainText("SYNTHETIC DEMO\nIntegration is disabled. Live mode previews CLA-owned changes before applying.")
                return
            if self.integration is None:
                raise ValueError("Integration is not available in this build.")
            scope = self.integration_scope.currentData()
            project = self.selected_project(required=True) if scope == "project" else None
            self._integration_plan = self.integration.preview(scope=scope, project=project)
            self.integration_preview.setPlainText(pretty(self._integration_plan))
            self.integration_apply_button.setEnabled(True)
            self.status_label.setText("Integration plan prepared. Review the target and exact changes before applying.")
        except Exception as exc:
            self.show_error("Cannot preview integration", exc)

    def apply_integration(self):
        if self.demo or self.integration is None or self._integration_plan is None:
            return
        try:
            result = self.integration.apply(self._integration_plan)
            self.invalidate_integration()
            self.integration_preview.setPlainText(pretty(result))
            self.status_label.setText("The reviewed CLA integration plan was applied.")
        except Exception as exc:
            self.show_error("Could not apply integration", exc)

    def remove_integration(self):
        if self.demo or self.integration is None:
            return
        try:
            scope = self.integration_scope.currentData()
            project = self.selected_project(required=True) if scope == "project" else None
            result = self.integration.remove(scope=scope, project=project)
            self.invalidate_integration()
            self.integration_preview.setPlainText(pretty(result))
            self.status_label.setText("CLA-owned integration removed where ownership was verified.")
        except Exception as exc:
            self.show_error("Could not remove integration", exc)

    def create_shortcut(self):
        if self.demo:
            return
        try:
            if self.shortcut_factory is None:
                raise ValueError("Desktop shortcut creation is not available in this build.")
            powershell = self.executable_fields["powershell"].currentText().strip()
            trusted = (field(self.settings, "trusted_executables", {}) or {}).get("powershell")
            if not powershell or not trusted or Path(powershell).resolve() != Path(trusted).resolve():
                raise ValueError("Approve the selected PowerShell 7 executable in Engines before creating a shortcut.")
            result = self.shortcut_factory(powershell_path=powershell)
            self.status_label.setText("CLA desktop shortcut created: " + str(result))
        except Exception as exc:
            self.show_error("Could not create desktop shortcut", exc)

    def refresh_history(self):
        self.history_table.setRowCount(0)
        if self.demo:
            self.history_note.setText("SYNTHETIC DEMO · Live session history is never loaded in Demo mode.")
            return
        if self.history_directory is None:
            return
        records = []
        try:
            paths = sorted(Path(self.history_directory).glob("*/status.json"), key=lambda item: item.stat().st_mtime, reverse=True)
            for path in paths[:100]:
                if path.stat().st_size > 131072:
                    continue
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(record, dict):
                    record.setdefault("session_id", path.parent.name)
                    records.append(record)
        except OSError as exc:
            self.history_note.setText("History is unavailable: " + str(exc))
            return
        self.history_table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = (record.get("session_id"), record.get("created_at", record.get("started_at", record.get("updated_at"))),
                      record.get("status"), record.get("project"))
            for column, value in enumerate(values):
                self.history_table.setItem(row, column, QTableWidgetItem(display(value)))
        self.history_note.setText(f"{len(records)} recent CLA metadata records. Full conversations are not loaded." if records else
                                 "No sessions recorded by CLA.")

    def show_error(self, title, error):
        # Inline errors preserve keyboard flow and keep smoke tests nonblocking.
        self.status_label.setText(f"{title}: {error}")

    def closeEvent(self, event: QCloseEvent):
        # CLA has no ownership of the user's launched Codex terminal lifetime.
        if self._scan_thread is not None and self._scan_thread.isRunning():
            self._close_pending = True
            self.cancel_scan()
            self.hide()
            event.ignore()
        else:
            event.accept()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Codex Launcher Awarness desktop interface")
    parser.add_argument("--demo", action="store_true", help="Synthetic data; host probes and launches disabled")
    parser.add_argument("--smoke-test", action="store_true", help="Open and close without probing or launching")
    parser.add_argument("--screenshot", type=Path, help="Save a synthetic screenshot; requires --demo")
    args = parser.parse_args(argv)
    if args.screenshot and not args.demo:
        parser.error("--screenshot requires --demo; live inventory screenshots are unavailable")
    from codex_launcher_awarness.settings import Settings, app_dir, load_settings, save_settings
    from codex_launcher_awarness.discovery import DiscoveryService
    from codex_launcher_awarness.discovery.service import resolve_candidates
    from codex_launcher_awarness.launch import LaunchManager, create_desktop_shortcut
    from codex_launcher_awarness.integration import IntegrationManager
    from codex_launcher_awarness.briefing import make_briefing

    app = QApplication.instance() or QApplication(["Codex Launcher Awarness"])
    app.setApplicationName("Codex Launcher Awarness")
    app.setOrganizationName("CLA")
    settings = Settings() if args.demo else load_settings()
    snapshot = None
    if args.demo:
        from codex_launcher_awarness.evidence.demo import demo_snapshot
        snapshot = demo_snapshot()
    discovery = None if args.demo else DiscoveryService(settings)
    launcher = None if args.demo else LaunchManager(settings)
    integration = None if args.demo else IntegrationManager(settings)
    window = MainWindow(settings, discovery, launcher, make_briefing,
                        snapshot=snapshot, demo=args.demo, save_settings=save_settings,
                        candidates=resolve_candidates, integration=integration,
                        history_directory=None if args.demo else app_dir() / "sessions",
                        shortcut_factory=create_desktop_shortcut)
    window.show()
    if not args.demo and not args.smoke_test and not settings.approved_project_roots:
        window.tabs.setCurrentIndex(2)
        window.project_path.setFocus()
    if args.screenshot:
        def capture():
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            if not window.grab().save(str(args.screenshot)):
                print("Could not save synthetic screenshot", file=sys.stderr)
                app.exit(1)
        QTimer.singleShot(400, capture)
    if args.smoke_test:
        QTimer.singleShot(900, window.close)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
