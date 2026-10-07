from __future__ import annotations

from pathlib import Path

import pytest

from src import autostart, cli

CMD = ["/opt/lms tool/lms-tool", "run"]


def test_linux_unit_quotes_the_command_and_restarts():
    unit = autostart.render(CMD, "linux")
    assert 'ExecStart="/opt/lms tool/lms-tool" "run"' in unit
    assert "WantedBy=default.target" in unit


def test_macos_plist_lists_arguments_and_runs_at_load():
    plist = autostart.render(CMD, "darwin")
    assert "<string>/opt/lms tool/lms-tool</string>" in plist
    assert "<key>RunAtLoad</key>" in plist


def test_windows_script_runs_hidden():
    script = autostart.render([r"C:\Tools\lms-tool.exe", "run"], "win32")
    assert script.startswith('CreateObject("WScript.Shell").Run')
    assert r'""C:\Tools\lms-tool.exe"" ""run""' in script
    assert script.rstrip().endswith(", 0, False")


def test_target_paths_follow_each_os(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert autostart.target_path("linux") == tmp_path / "systemd/user/lms-tool.service"
    assert autostart.target_path("win32").name == "lms-tool.vbs"
    assert "Startup" in autostart.target_path("win32").parts
    assert autostart.target_path("darwin").parent.name == "LaunchAgents"


@pytest.fixture
def no_system_calls(monkeypatch, tmp_path) -> list[tuple[str, ...]]:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(autostart, "_run", lambda *cmd: calls.append(cmd) or True)
    return calls


def test_enable_then_disable_on_linux(no_system_calls, tmp_path: Path):
    path = autostart.enable("linux")
    assert path.exists()
    assert autostart.is_enabled("linux")
    assert ("systemctl", "--user", "enable", "--now", "lms-tool.service") in no_system_calls

    assert autostart.disable("linux") is True
    assert not path.exists()
    assert autostart.disable("linux") is False


def test_init_creates_settings_once(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "user_config_dir", lambda: tmp_path / "cfg")

    assert cli.main(["init"]) == 0
    env_file = tmp_path / "cfg" / ".env"
    assert "GEMINI_API_KEY=" in env_file.read_text(encoding="utf-8")

    env_file.write_text("GEMINI_API_KEY=mine\n", encoding="utf-8")
    assert cli.main(["init"]) == 0
    assert env_file.read_text(encoding="utf-8") == "GEMINI_API_KEY=mine\n"
    assert "уже есть" in capsys.readouterr().out
