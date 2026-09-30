import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from codex_launcher_awarness import process_runtime


def test_unfrozen_no_loader_changes(monkeypatch):
    monkeypatch.setattr(process_runtime.sys, "frozen", False, raising=False)
    monkeypatch.setattr(process_runtime, "_get_dll_directory", lambda: pytest.fail("Unfrozen loader queried"))
    with process_runtime.clean_child_dll_search():
        pass


def test_frozen_windows_resets_restores_and_preserves_environment(monkeypatch):
    monkeypatch.setattr(process_runtime.sys, "platform", "win32")
    monkeypatch.setattr(process_runtime.sys, "frozen", True, raising=False)
    calls = []
    monkeypatch.setattr(process_runtime, "_get_dll_directory", lambda: r"C:\portable\_internal")
    monkeypatch.setattr(process_runtime, "_set_dll_directory", calls.append)
    environment = dict(os.environ)
    with process_runtime.clean_child_dll_search():
        assert calls == [None]
        assert dict(os.environ) == environment
    assert calls == [None, r"C:\portable\_internal"]
    assert dict(os.environ) == environment


def test_restore_even_when_child_creation_fails(monkeypatch):
    monkeypatch.setattr(process_runtime.sys, "platform", "win32")
    monkeypatch.setattr(process_runtime.sys, "frozen", True, raising=False)
    calls = []
    monkeypatch.setattr(process_runtime, "_get_dll_directory", lambda: "original")
    monkeypatch.setattr(process_runtime, "_set_dll_directory", calls.append)
    with pytest.raises(OSError, match="child failed"):
        with process_runtime.clean_child_dll_search():
            raise OSError("child failed")
    assert calls == [None, "original"]


def test_child_creation_lock_serializes_loader_mutations(monkeypatch):
    monkeypatch.setattr(process_runtime.sys, "platform", "win32")
    monkeypatch.setattr(process_runtime.sys, "frozen", True, raising=False)
    calls = []
    monkeypatch.setattr(process_runtime, "_get_dll_directory", lambda: "original")
    monkeypatch.setattr(process_runtime, "_set_dll_directory", lambda value: calls.append((threading.get_ident(), value)))
    def worker(_):
        with process_runtime.clean_child_dll_search():
            time.sleep(0.01)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(worker, range(3)))
    assert [value for _, value in calls] == [None, "original"] * 3
    assert all(calls[index][0] == calls[index + 1][0] for index in range(0, 6, 2))
