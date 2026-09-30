import json
import os
import shutil
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from codex_launcher_awarness.launch import LaunchError, LaunchManager, LaunchRequest
from codex_launcher_awarness.launch.manager import resolve_codex
from codex_launcher_awarness.launch.windows import spawn_interactive, is_elevated


def _fixture_at(tmp_path):
    project = tmp_path / "project O'Brien; [$task] 日本"
    project.mkdir()
    fake = project / "fake codex.ps1"
    fake.write_text("$args | ConvertTo-Json\n", encoding="utf-8")
    powershell = shutil.which("pwsh.exe") or str(tmp_path / "pwsh.exe")
    if not Path(powershell).exists():
        Path(powershell).touch()
    from codex_launcher_awarness.settings import Settings
    settings = Settings(trusted_executables={"codex": str(fake), "powershell": powershell}, approved_project_roots=[str(project)])
    manager = LaunchManager(settings, state_dir=tmp_path / "private")
    request = LaunchRequest(str(project), "Inspect safely", str(fake), powershell)
    return manager, request, project


@pytest.fixture
def prepared_fixture(tmp_path):
    return _fixture_at(tmp_path)


@pytest.fixture
def desktop_prepared_fixture():
    # Pytest's Windows temp root intentionally has an administrators/owner-only
    # ACL. Use CLA's per-user directory for real medium-token child tests.
    from platformdirs import user_data_path
    root = user_data_path("CLA", appauthor=False, roaming=False) / "acceptance-tests"
    root.mkdir(parents=True, exist_ok=True)
    directory = root / ("fake-launch-" + uuid.uuid4().hex)
    directory.mkdir()
    try:
        yield _fixture_at(directory)
    finally:
        assert directory.resolve().is_relative_to(root.resolve()) and directory != root
        shutil.rmtree(directory)


def test_prepare_immutable_context_and_safe_arguments(prepared_fixture):
    manager, request, project = prepared_fixture
    text = "Task: quotes ' and \"; $($evil); [brackets] 日本\nSecond line."
    prepared = manager.prepare(request, {"schema_version": 1, "capabilities": []}, text)
    manifest = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))
    assert manifest["codex_args"][-1] == prepared.prompt
    assert text in prepared.prompt
    assert manifest["project"] == str(project)
    assert "-Command" not in prepared.command and "-File" in prepared.command
    assert request.task not in " ".join(prepared.command)
    assert len(prepared.session_id) == 32
    assert json.loads(prepared.snapshot_path.read_text(encoding="utf-8"))["session_id"] == prepared.session_id
    assert "danger-full-access" not in manifest["codex_args"]
    assert "<approved briefing positional prompt>" in prepared.preview["argument_structure"]
    second = manager.prepare(request, {}, text)
    assert second.snapshot_path != prepared.snapshot_path
    assert prepared.snapshot_path.is_file()


def test_batch_wrapper_uses_same_installation_companion(tmp_path):
    wrapper = tmp_path / "codex.cmd"
    wrapper.touch()
    with pytest.raises(LaunchError, match="Batch-only"):
        resolve_codex(str(wrapper))
    script = wrapper.with_suffix(".ps1")
    script.touch()
    path, warning = resolve_codex(str(wrapper))
    assert path == script and "companion" in warning


def test_explicit_full_access_only(prepared_fixture):
    manager, request, _ = prepared_fixture
    from dataclasses import replace
    prepared = manager.prepare(replace(request, permission_mode="full-access-no-approval"), {}, "context")
    args = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))["codex_args"]
    assert args[-5:-1] == ["-s", "danger-full-access", "-a", "never"]
    assert any("disables" in warning for warning in prepared.warnings)


def test_reject_invalid_paths_and_long_prompt(prepared_fixture):
    manager, request, _ = prepared_fixture
    from dataclasses import replace
    with pytest.raises(LaunchError):
        manager.prepare(replace(request, codex_path="codex"), {}, "context")
    with pytest.raises(LaunchError):
        manager.prepare(replace(request, model="x; evil"), {}, "context")
    with pytest.raises(LaunchError, match="budget"):
        manager.prepare(request, {}, "x" * 6501)


def test_manager_requires_approved_paths(prepared_fixture):
    manager, request, _ = prepared_fixture
    manager.settings.approved_project_roots.clear()
    with pytest.raises(LaunchError, match="project root"):
        manager.prepare(request, {}, "context")
    manager.settings.approved_project_roots.append(request.project)
    manager.settings.trusted_executables.clear()
    with pytest.raises(LaunchError, match="exact selected codex"):
        manager.prepare(request, {}, "context")


def test_secret_canaries_redacted_before_private_storage(prepared_fixture):
    manager, request, _ = prepared_fixture
    canary = "cla-canary-" + uuid.uuid4().hex
    prepared = manager.prepare(request, {"api_key": canary}, "api_key=" + canary)
    for path in [prepared.manifest_path, prepared.snapshot_path, prepared.manifest_path.parent / "briefing.txt"]:
        assert canary not in path.read_text(encoding="utf-8")
    assert canary not in prepared.prompt


def test_tampered_preview_refused(prepared_fixture):
    manager, request, _ = prepared_fixture
    prepared = manager.prepare(request, {}, "context")
    prepared.manifest_path.write_text("{}")
    with pytest.raises(LaunchError, match="changed"):
        manager.launch(prepared)


@pytest.mark.skipif(os.name != "nt", reason="Windows launch engineering")
def test_duplicate_click_and_independent_manager_claim(prepared_fixture, monkeypatch):
    manager, request, _ = prepared_fixture
    prepared = manager.prepare(request, {}, "context")
    calls = []
    monkeypatch.setattr("codex_launcher_awarness.launch.windows.spawn_interactive", lambda *args, **kwargs: calls.append(args) or {"pid": 123, "unelevated": True})
    def launch():
        try:
            return manager.launch(prepared)["status"]
        except LaunchError:
            return "refused"
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: launch(), range(4)))
    assert results.count("terminal_started") == 1 and len(calls) == 1
    with pytest.raises(LaunchError, match="claimed"):
        LaunchManager(state_dir=manager.state_dir).launch(prepared)


@pytest.mark.skipif(os.name != "nt" or not shutil.which("pwsh.exe"), reason="Needs real Windows PowerShell 7; Codex remains mocked")
def test_real_bootstrap_fake_codex_hostile_payload_and_conda_child_only(desktop_prepared_fixture):
    manager, request, project = desktop_prepared_fixture
    fake = Path(request.codex_path)
    fake.write_text("""$output = @{ arguments = @($args); cwd = (Get-Location).Path; conda = $env:CONDA_DEFAULT_ENV;
    elevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) }
$output | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path (Get-Location).Path 'fake-result.json') -Encoding utf8
exit 0
""", encoding="utf-8")
    conda_root = manager.state_dir / "trusted conda"
    executable = conda_root / "Scripts" / "conda.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    hook = conda_root / "shell" / "condabin" / "conda-hook.ps1"
    hook.parent.mkdir(parents=True)
    hook.write_text("function global:conda { param([string]$Action,[string]$Environment) if ($Action -ne 'activate') { throw 'unexpected' }; $env:CONDA_DEFAULT_ENV = $Environment }\n")
    from dataclasses import replace
    original = os.environ.get("CONDA_DEFAULT_ENV")
    request = replace(request, conda_path=str(executable), conda_env="base", allow_elevated=is_elevated())
    manager.settings.trusted_executables["conda"] = str(executable)
    hostile = "quotes ' and \"; $([IO.File]::WriteAllText('INJECTED','x')); [hello] 日本\n" + ("Long context " * 300)
    prepared = manager.prepare(request, {}, hostile)
    command = [argument for argument in prepared.command if argument != "-NoExit"]
    result = spawn_interactive(command, str(project), new_console=False, allow_elevated=request.allow_elevated)
    assert result["unelevated"] is (not is_elevated())
    assert result.get("probe_exit_code", 0) in {0, 259}, result
    status_path = prepared.manifest_path.parent / "status.json"
    deadline = time.monotonic() + 20
    status = {}
    while time.monotonic() < deadline:
        try:
            status = json.loads(status_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            time.sleep(0.1)
            continue
        if status["status"] in {"codex_exited", "failed"}:
            break
        time.sleep(0.1)
    assert status["status"] == "codex_exited", status
    payload = json.loads((project / "fake-result.json").read_text(encoding="utf-8-sig"))
    assert payload["arguments"] == json.loads(prepared.manifest_path.read_text(encoding="utf-8"))["codex_args"]
    assert payload["cwd"] == str(project)
    assert payload["elevated"] is is_elevated()
    assert payload["conda"] == "base" and os.environ.get("CONDA_DEFAULT_ENV") == original
    assert not (project / "INJECTED").exists()
    assert status["exit_code"] == 0
    import psutil
    try:
        psutil.Process(result["pid"]).wait(timeout=5)
    except psutil.NoSuchProcess:
        pass


@pytest.mark.skipif(os.name != "nt", reason="Windows token behavior")
def test_elevation_requires_explicit_opt_in(prepared_fixture, monkeypatch):
    manager, request, project = prepared_fixture
    prepared = manager.prepare(request, {}, "context")
    assert prepared.preview["allow_elevated"] is False
    monkeypatch.setattr("codex_launcher_awarness.launch.windows.is_elevated", lambda: True)
    def refuse(*args, **kwargs):
        raise OSError("No unelevated desktop token")
    monkeypatch.setattr("codex_launcher_awarness.launch.windows._spawn_shell_token", refuse)
    with pytest.raises(LaunchError, match="unelevated"):
        manager.launch(prepared)
    assert not (prepared.manifest_path.parent / "launch.claim").exists()
