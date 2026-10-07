"""Start the server automatically at login, the native way on each OS:
a systemd user unit on Linux, a LaunchAgent on macOS, a hidden script in
the Startup folder on Windows.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

LABEL = "lms-tool"
MAC_LABEL = "local.lms-tool"


def server_command() -> list[str]:
    """Command line that starts the server from outside any shell."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "run"]
    found = shutil.which("lms-tool")
    if found:
        return [found, "run"]
    return [sys.executable, "-m", "src.cli", "run"]


def target_path(platform: str = sys.platform) -> Path:
    if platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return (
            base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
            / f"{LABEL}.vbs"
        )
    if platform == "darwin":
        return Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "systemd" / "user" / f"{LABEL}.service"


def render(command: list[str], platform: str = sys.platform) -> str:
    if platform == "win32":
        # A .vbs with window style 0 starts the server without a console window.
        quoted = " ".join(f'""{part}""' for part in command)
        return f'CreateObject("WScript.Shell").Run "{quoted}", 0, False\r\n'
    if platform == "darwin":
        args = "\n".join(f"        <string>{part}</string>" for part in command)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{MAC_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{args}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
"""
    exec_start = " ".join(f'"{part}"' for part in command)
    return f"""[Unit]
Description=lms-tool server (СЭО helper)

[Service]
ExecStart={exec_start}
Restart=on-failure

[Install]
WantedBy=default.target
"""


def _run(*cmd: str) -> bool:
    try:
        return subprocess.run(cmd, check=False, capture_output=True).returncode == 0  # noqa: S603
    except FileNotFoundError:
        return False


def enable(platform: str = sys.platform) -> Path:
    path = target_path(platform)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(server_command(), platform), encoding="utf-8")
    if platform == "darwin":
        _run("launchctl", "unload", str(path))
        _run("launchctl", "load", "-w", str(path))
    elif platform != "win32":
        _run("systemctl", "--user", "daemon-reload")
        _run("systemctl", "--user", "enable", "--now", f"{LABEL}.service")
    return path


def disable(platform: str = sys.platform) -> bool:
    """Remove autostart. Returns False if it wasn't set up."""
    path = target_path(platform)
    if not path.exists():
        return False
    if platform == "darwin":
        _run("launchctl", "unload", "-w", str(path))
    elif platform != "win32":
        _run("systemctl", "--user", "disable", "--now", f"{LABEL}.service")
    path.unlink()
    if platform not in ("win32", "darwin"):
        _run("systemctl", "--user", "daemon-reload")
    return True


def is_enabled(platform: str = sys.platform) -> bool:
    return target_path(platform).exists()
