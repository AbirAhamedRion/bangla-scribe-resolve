"""
build_desktop.py
----------------
Turn Bangla Subtitle Studio into a real desktop application (a single
double-clickable executable) with PyInstaller.

    pip install pyinstaller
    python build_desktop.py

Output:
    dist/BanglaSubtitleStudio.exe      (Windows)
    dist/BanglaSubtitleStudio.app      (macOS, --windowed bundle)
    dist/BanglaSubtitleStudio          (Linux)

Notes
-----
* The Whisper weights are NOT bundled — they download once at first run into
  the model cache, exactly as they do when running from source.
* faster-whisper pulls in ctranslate2 binaries; PyInstaller picks them up via
  --collect-all, which is why the build is a few hundred MB.
* Build on the OS you want to ship for: PyInstaller does not cross-compile.
"""

from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "BanglaSubtitleStudio"


def main() -> int:
    sep = ";" if sys.platform.startswith("win") else ":"
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",                       # no console window
        "--name", NAME,
        "--paths", HERE,
        "--add-data", f"{os.path.join(HERE, 'style.qss')}{sep}.",
        "--collect-all", "faster_whisper",
        "--collect-all", "ctranslate2",
        "--collect-all", "tokenizers",
        "--hidden-import", "resolve_api",
        "--hidden-import", "ai_engine",
        "--hidden-import", "pipeline",
    ]
    icon = os.path.join(HERE, "icon.ico")
    if os.path.isfile(icon):
        args += ["--icon", icon]
    args.append(os.path.join(HERE, "app.py"))

    print("Running:", " ".join(args))
    return subprocess.call(args)


if __name__ == "__main__":
    raise SystemExit(main())
