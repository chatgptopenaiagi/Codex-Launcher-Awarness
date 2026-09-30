"""Offscreen GUI tests use fake backends; they never start Codex or probe a host."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from codex_launcher_awarness.evidence.demo import demo_snapshot
from codex_launcher_awarness.evidence.models import Capability, Snapshot
from codex_launcher_awarness.gui.app import MainWindow, main
from codex_launcher_awarness.settings import Settings


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(["cla-test"])
    app.setQuitOnLastWindowClosed(False)
    return app


def wait_until(app, condition, timeout=3):
    deadline = time.monotonic() + timeout
    while not condition():
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("Qt operation did not finish before the test deadline")
        time.sleep(0.005)
    app.processEvents()


class FakeDiscovery:
    def __init__(self, snapshot=None, block=False):
        self.snapshot = snapshot or Snapshot(capabilities=[Capability(id="tool.codex", readiness="unknown")])
        self.calls = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.block = block

    def scan(self, **kwargs):
        self.calls.append(kwargs)
        self.started.set()
        if self.block:
            while not self.release.wait(0.01) and not kwargs["cancel"].is_set():
                pass
        return self.snapshot


class FakeLauncher:
    def __init__(self):
        self.preparations, self.launches = [], []
        self.error = None

    def prepare(self, request, snapshot, briefing_text=None):
        if self.error:
            raise ValueError(self.error)
        self.preparations.append((request, snapshot, briefing_text))
        return SimpleNamespace(prompt="Exact task:\n" + request.task + "\n\n" + (briefing_text or "LOCAL EVIDENCE / " + request.task_filter),
                               command=["synthetic-pwsh", "-File", "fixed-bootstrap.ps1"],
                               warnings=[], session_id="fake-session",
                               preview={"codex_executable": request.codex_path,
                                        "powershell": request.powershell_path,
                                        "permission_mode": request.permission_mode,
                                        "allow_elevated": request.allow_elevated,
                                        "conda": {"executable": request.conda_path, "environment": request.conda_env},
                                        "argument_structure": ["-C", str(request.project), "<approved briefing positional prompt>"]})

    def launch(self, prepared):
        self.launches.append(prepared)
        return {"status": "started", "session_id": "fake-session", "pid": 123}


class FakeIntegration:
    def __init__(self):
        self.previews, self.applied, self.removed = [], [], []

    def preview(self, **kwargs):
        self.previews.append(kwargs)
        return {"target": "synthetic-project-config", "before_sha256": "fake-digest",
                "toml": "[mcp_servers.cla]\ncommand = 'cla'", "scope": kwargs["scope"]}

    def apply(self, plan):
        self.applied.append(plan)
        return {"status": "applied"}

    def remove(self, **kwargs):
        self.removed.append(kwargs)
        return {"status": "removed"}


@pytest.fixture
def window(qapp, tmp_path):
    codex, powershell = tmp_path / "codex.exe", tmp_path / "pwsh.exe"
    codex.write_bytes(b"SYNTHETIC; NEVER EXECUTED")
    powershell.write_bytes(b"SYNTHETIC; NEVER EXECUTED")
    settings = Settings(approved_project_roots=[str(tmp_path)],
                        trusted_executables={"codex": str(codex), "powershell": str(powershell)})
    discovery = FakeDiscovery()
    launcher = FakeLauncher()
    integrations = FakeIntegration()
    saved = []
    ui = MainWindow(settings, discovery, launcher,
                    lambda snapshot, project, task, **kwargs: "LOCAL EVIDENCE / " + kwargs["filter"],
                    snapshot=discovery.snapshot, save_settings=lambda item: saved.append(item.model_copy(deep=True)),
                    request_factory=SimpleNamespace, integration=integrations,
                    history_directory=tmp_path / "sessions")
    ui._test_saved = saved
    ui.show()
    qapp.processEvents()
    yield ui
    ui.cancel_scan()
    wait_until(qapp, lambda: ui._scan_thread is None)
    ui.close()
    ui.deleteLater()
    qapp.processEvents()


def test_missing_codex_does_not_block_local_inventory(window, qapp):
    assert window.tabs.count() == 5
    window.executable_fields["codex"].setCurrentText("")
    assert not window.executable_fields["codex"].currentText()
    window.start_scan()
    wait_until(qapp, lambda: window._scan_thread is None)
    assert window.capability_table.rowCount() == 1
    assert window.discovery.calls[0]["allow_probes"] is False
    assert not window.launcher.preparations
    assert not window.launcher.launches


def test_scan_is_responsive_cancellable_and_retains_snapshot(window, qapp):
    original = window.snapshot
    discovery = FakeDiscovery(block=True)
    window.discovery = discovery
    ticks = []
    QTimer.singleShot(20, lambda: ticks.append(True))
    window.start_scan()
    wait_until(qapp, lambda: discovery.started.is_set() and bool(ticks))
    assert not window.scan_button.isEnabled()
    assert window.cancel_button.isEnabled()
    window.cancel_scan()
    wait_until(qapp, lambda: window._scan_thread is None)
    assert discovery.calls[0]["cancel"].is_set()
    assert window.snapshot is original
    assert window.scan_button.isEnabled()
    assert "cancelled" in window.status_label.text().lower()


def test_exact_preview_privacy_gate_duplicate_start_and_close(window, qapp):
    task = "Keep this exact text:\nquotes ' \" & $() ; Unicode Ω."
    window.task_input.setPlainText(task)
    window.prepare_preview()
    assert window.prepared is not None
    assert window.prompt_preview.toPlainText() == window.prepared.prompt
    assert window.exact_prompt == window.prepared.prompt
    assert window.launcher.preparations[-1][0].permission_mode == "inherit"
    assert window.launcher.preparations[-1][0].allow_elevated is False
    details = json.loads(window.command_preview.toPlainText())
    route = details["launch_route"]
    assert route == window.prepared.preview
    assert route["codex_executable"] == window.executable_fields["codex"].currentText()
    assert route["powershell"] == window.executable_fields["powershell"].currentText()
    assert route["permission_mode"] == "inherit" and route["allow_elevated"] is False
    assert details["terminal_command"] == window.prepared.command
    assert not window.start_button.isEnabled()
    window.start_codex()
    assert not window.launcher.launches
    window.privacy_ack.setChecked(True)
    assert window.start_button.isEnabled()
    prepared = window.prepared
    window.start_codex()
    window.start_codex()
    assert window.launcher.launches == [prepared]
    assert not window.start_button.isEnabled()
    window.close()
    qapp.processEvents()
    assert window.launcher.launches == [prepared]


@pytest.mark.parametrize("edit", ["task", "filter", "permission", "model", "project", "elevation"])
def test_launch_edits_invalidate_exact_preview_and_consent(window, edit, tmp_path):
    window.task_input.setPlainText("Inspect this project")
    window.prepare_preview()
    window.privacy_ack.setChecked(True)
    assert window.start_button.isEnabled()
    if edit == "task":
        window.task_input.setPlainText("A different task")
    elif edit == "filter":
        window.relevance_filter.setCurrentText("gpu")
    elif edit == "permission":
        window.permission_mode.setCurrentIndex(1)
        assert "disables" in window.permission_note.text()
    elif edit == "model":
        window.model_input.setText("explicit-model")
    elif edit == "elevation":
        window.allow_elevated.setChecked(True)
    else:
        other = tmp_path / "other"
        other.mkdir()
        window.project_path.setText(str(other))
    assert window.prepared is None
    assert not window.privacy_ack.isChecked()
    assert not window.start_button.isEnabled()
    assert not window.prompt_preview.toPlainText()


def test_prepare_error_is_visible_and_does_not_start_process(window):
    window.launcher.error = "Approved Codex executable is missing"
    window.task_input.setPlainText("Inspect")
    window.prepare_preview()
    assert window.prepared is None
    assert "Approved Codex executable is missing" in window.status_label.text()
    assert not window.start_button.isEnabled()
    assert not window.launcher.launches


def test_unapproved_executable_cannot_reach_prepare(window, tmp_path):
    unexpected = tmp_path / "unapproved.exe"
    unexpected.write_bytes(b"NEVER EXECUTED")
    window.executable_fields["codex"].setCurrentText(str(unexpected))
    window.task_input.setPlainText("Inspect")
    window.prepare_preview()
    assert "Approve the selected codex" in window.status_label.text()
    assert not window.launcher.preparations
    assert not window.start_button.isEnabled()


def test_project_change_requires_new_snapshot_before_preparing(window, qapp, tmp_path):
    other = tmp_path / "different-project"
    other.mkdir()
    window.project_path.setText(str(other))
    window.task_input.setPlainText("Inspect the selected project")
    assert "PROJECT CHANGED" in window.freshness_label.text()
    window.prepare_preview()
    assert "Inspect inventory again" in window.status_label.text()
    assert not window.launcher.preparations
    window.start_scan()
    wait_until(qapp, lambda: window._scan_thread is None)
    assert window.discovery.calls[-1]["project"] == other.resolve()
    window.prepare_preview()
    assert len(window.launcher.preparations) == 1


def test_keyboard_navigation_and_minimum_resize(window, qapp):
    window.resize(920, 650)
    QTest.keyClick(window, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
    qapp.processEvents()
    assert window.tabs.currentIndex() == 2
    assert window.width() >= 920 and window.height() >= 650
    window.task_input.setFocus()
    QTest.keyClicks(window.task_input, "Task entered by keyboard")
    assert window.task_input.toPlainText() == "Task entered by keyboard"


def test_executable_selection_requires_approval_and_probe_consent(window, tmp_path):
    executable = tmp_path / "synthetic.exe"
    executable.write_bytes(b"NOT AN EXECUTABLE")
    window.executable_fields["codex"].setCurrentText(str(executable))
    assert window.settings.trusted_executables["codex"] != str(executable)
    assert not window._test_saved
    window.approve_executables()
    assert window.settings.trusted_executables["codex"] == str(executable.resolve())
    assert window.settings.probe_enabled is False
    assert not window.discovery.calls
    window.allow_probes.setChecked(True)
    assert window.settings.probe_enabled is True
    assert not window.discovery.calls


def test_invalid_endpoint_settings_are_not_committed(window):
    window.local_endpoints.setPlainText("https://remote.example.invalid")
    window.save_engine_settings()
    assert window.settings.local_endpoints == []
    assert not window._test_saved
    assert "Could not save" in window.status_label.text()


def test_demo_is_unmistakable_and_never_calls_host_services(qapp, tmp_path):
    candidates = []
    saved, shortcuts = [], []
    discovery, launcher, integration = FakeDiscovery(), FakeLauncher(), FakeIntegration()
    ui = MainWindow(Settings(), discovery, launcher, lambda *_args, **_kwargs: "unused",
                    snapshot=demo_snapshot(), demo=True,
                    candidates=lambda name: candidates.append(name) or [],
                    save_settings=lambda item: saved.append(item), integration=integration,
                    shortcut_factory=lambda: shortcuts.append(True), history_directory=tmp_path,
                    request_factory=SimpleNamespace)
    ui.show()
    qapp.processEvents()
    assert ui.demo_banner.isVisible()
    assert "SYNTHETIC" in ui.demo_banner.text()
    ui.start_scan()
    ui.prepare_preview()
    ui.privacy_ack.setChecked(True)
    ui.start_codex()
    ui.approve_executables()
    ui.approve_project()
    ui.apply_integration()
    ui.remove_integration()
    ui.create_shortcut()
    assert not candidates and not saved and not shortcuts
    assert not discovery.calls and not launcher.launches and not launcher.preparations
    assert not integration.applied and not integration.removed
    assert not ui.start_button.isEnabled()
    assert "SYNTHETIC DEMO" in ui.prompt_preview.toPlainText()
    screenshot = tmp_path / "synthetic-demo.png"
    assert ui.grab().save(str(screenshot))
    assert screenshot.stat().st_size > 1000
    ui.close()
    ui.deleteLater()
    qapp.processEvents()


def test_stale_evidence_is_not_counted_as_ready(window):
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    window.set_snapshot(Snapshot(capabilities=[
        Capability(id="stale-tool", readiness="verified", expires_at=past),
        Capability(id="unchecked-tool", readiness="unknown"),
    ]))
    assert window.metric_labels["verified"].text() == "0"
    assert window.metric_labels["attention"].text() == "2"
    assert window.capability_table.item(0, 4).text() == "stale"
    assert "refresh" in window.freshness_label.text().lower()


def test_hardware_cards_show_values_units_and_unknowns(window):
    window.set_snapshot(Snapshot(capabilities=[
        Capability(id="hardware.cpu", tags=["cpu"], values={"model": "Synthetic CPU", "logical_count": 12, "utilization_percent": 8.5}),
        Capability(id="hardware.memory", tags=["memory"], values={"available_bytes": 16*2**30, "total_bytes": 32*2**30}),
        Capability(id="hardware.gpu", tags=["gpu"], values={"devices": [
            {"name": "Synthetic GPU 1", "memory_free_mib": 4096, "memory_total_mib": 8192},
            {"name": "Synthetic GPU 2", "memory_free_mib": 2048, "memory_total_mib": 4096},
        ]}),
        Capability(id="hardware.storage.0", tags=["storage"], path="synthetic volume", values={"free_bytes": 120*2**30, "total_bytes": 512*2**30}),
    ]))
    assert window.hardware_labels["cpu"].text() == "8.5% busy"
    assert "12 logical" in window.hardware_notes["cpu"].text()
    assert window.hardware_labels["memory"].text() == "16.0 / 32.0 GiB"
    assert window.hardware_labels["gpu"].text() == "6.0 / 12.0 GiB"
    assert window.hardware_labels["storage"].text() == "120.0 GiB free"
    assert "Evidence:" in window.hardware_labels["gpu"].toolTip()
    window.set_snapshot(Snapshot(capabilities=[Capability(id="hardware.gpu", tags=["gpu"], values={"devices": [
        {"name": "Unknown metrics", "memory_free_mib": None, "memory_total_mib": 8192}]} )]))
    assert window.hardware_labels["gpu"].text() == "— / 8.0 GiB"
    assert window.hardware_labels["cpu"].text() == "—"


def test_integration_applies_only_the_reviewed_plan(window):
    window.preview_integration()
    plan = window._integration_plan
    assert plan is not None
    assert not window.integration.applied
    assert window.integration.previews[0]["scope"] == "project"
    window.apply_integration()
    window.apply_integration()
    assert window.integration.applied == [plan]
    window.preview_integration()
    window.integration_scope.setCurrentIndex(1)
    assert window._integration_plan is None
    assert not window.integration_apply_button.isEnabled()


def test_history_reads_metadata_only(window, tmp_path):
    directory = tmp_path / "sessions" / "safe-session"
    directory.mkdir(parents=True)
    (directory / "status.json").write_text(json.dumps({"status": "exited", "project": "synthetic project",
                                                       "session_id": "safe-session"}), encoding="utf-8")
    (directory / "launch.json").write_text('{"prompt":"PRIVATE PROMPT MUST NEVER APPEAR"}', encoding="utf-8")
    (directory / "conversation.json").write_text('{"content":"PRIVATE CONVERSATION"}', encoding="utf-8")
    window.refresh_history()
    assert window.history_table.rowCount() == 1
    assert window.history_table.item(0, 2).text() == "exited"
    assert "PRIVATE" not in window.history_note.text()
    assert all("PRIVATE" not in window.history_table.item(0, col).text() for col in range(4))


def test_launch_lifecycle_failure_is_visible_and_transient_reads_retry(window, tmp_path):
    directory = tmp_path / "sessions" / "lifecycle-test"
    directory.mkdir(parents=True)
    path = directory / "status.json"
    window._active_status_path = path
    window.poll_launch_status()  # A status file may not exist immediately after terminal creation.
    path.write_text('{"incomplete"', encoding="utf-8")
    window.poll_launch_status()  # Retry incomplete/temporarily unavailable metadata.
    path.write_text(json.dumps({"status": "failed", "exit_code": 7, "reason": "codex_nonzero_exit"}), encoding="utf-8")
    window.poll_launch_status()
    assert "failed" in window.launch_status_label.text()
    assert "7" in window.launch_status_label.text()
    assert "codex_nonzero_exit" in window.status_label.text()
    assert not window.launcher.launches


def test_close_during_scan_cancels_and_closes_after_worker_returns(window, qapp):
    window.discovery = FakeDiscovery(block=True)
    window.start_scan()
    wait_until(qapp, lambda: window.discovery.started.is_set())
    window.close()
    assert window._close_pending
    wait_until(qapp, lambda: window._scan_thread is None)
    assert not window.isVisible()
    assert not window.launcher.launches


def test_screenshot_requires_synthetic_demo(qapp, tmp_path):
    with pytest.raises(SystemExit) as error:
        main(["--screenshot", str(tmp_path / "forbidden.png")])
    assert error.value.code == 2
    assert not (tmp_path / "forbidden.png").exists()
