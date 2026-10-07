"""Build the standalone `lms-tool` for the current OS:

    pip install ".[bundle]"
    python packaging/build.py

Result: dist/lms-tool/ (a folder with the executable and its libraries).
A folder build starts faster than a single file and trips fewer antivirus
false positives.
"""

from pathlib import Path

import PyInstaller.__main__

BACKEND = Path(__file__).resolve().parent.parent

PyInstaller.__main__.run(
    [
        str(BACKEND / "packaging" / "entry.py"),
        "--name=lms-tool",
        "--onedir",
        "--noconfirm",
        "--clean",
        f"--paths={BACKEND}",
        f"--distpath={BACKEND / 'dist'}",
        f"--workpath={BACKEND / 'build'}",
        f"--specpath={BACKEND / 'build'}",
        # Loaded by name at runtime, so PyInstaller can't see them on its own.
        "--collect-submodules=uvicorn",
        "--hidden-import=aiosqlite",
        "--hidden-import=sqlalchemy.dialects.sqlite.aiosqlite",
        # The browser-automation extras are not part of the standalone build.
        "--exclude-module=selenium",
        "--exclude-module=undetected_chromedriver",
    ]
)
