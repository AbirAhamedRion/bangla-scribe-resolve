"""
settings_store.py
-----------------
Persist the GUI's last-used options so the app opens exactly as it was left.

Stored as plain JSON in the user config directory (override with RBS_CONFIG):
  Windows : %APPDATA%\\ResolveBanglaSubtitles\\settings.json
  macOS   : ~/Library/Application Support/ResolveBanglaSubtitles/settings.json
  Linux   : ~/.config/resolve_bangla_subtitles/settings.json

Every read is defensive: unknown keys are ignored, missing keys fall back to
DEFAULTS, and values are clamped to the same ranges the widgets allow, so a
hand-edited or stale config can never put the UI into an invalid state.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict

APP_DIR_NAME = "ResolveBanglaSubtitles"

DEFAULTS: Dict[str, Any] = {
    "model": "large-v3",
    "gpu": True,
    "trim": True,
    "threshold_db": -45,
    "max_chars": 42,
    "max_lines": 2,
    "place": True,
    "reuse_transcript": True,
    "timeline": "",
    "use_in_out": False,
    "output_dir": "",
    # ~8 x 6 inches at 96 dpi.
    "window": {"w": 800, "h": 600},
}


_MODELS = ("large-v3", "medium", "small")


def config_path() -> str:
    env = os.environ.get("RBS_CONFIG")
    if env:
        path = os.path.expanduser(env)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        folder = os.path.join(base, APP_DIR_NAME)
    elif sys.platform == "darwin":
        folder = os.path.expanduser(
            f"~/Library/Application Support/{APP_DIR_NAME}"
        )
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        folder = os.path.join(base, "resolve_bangla_subtitles")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "settings.json")


def _clamp(value: Any, lo: int, hi: int, fallback: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return fallback


def _sanitise(raw: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(DEFAULTS)
    if not isinstance(raw, dict):
        return out

    model = raw.get("model")
    out["model"] = model if model in _MODELS else DEFAULTS["model"]


    for flag in ("gpu", "trim", "place", "reuse_transcript", "use_in_out"):
        out[flag] = bool(raw.get(flag, DEFAULTS[flag]))

    out["threshold_db"] = _clamp(raw.get("threshold_db"), -70, -25, DEFAULTS["threshold_db"])
    out["max_chars"] = _clamp(raw.get("max_chars"), 20, 70, DEFAULTS["max_chars"])
    out["max_lines"] = _clamp(raw.get("max_lines"), 1, 3, DEFAULTS["max_lines"])

    timeline = raw.get("timeline") or ""
    out["timeline"] = timeline if isinstance(timeline, str) else ""

    out_dir = raw.get("output_dir") or ""
    out["output_dir"] = out_dir if isinstance(out_dir, str) else ""

    win = raw.get("window") if isinstance(raw.get("window"), dict) else {}
    out["window"] = {
        "w": _clamp(win.get("w"), 740, 2400, DEFAULTS["window"]["w"]),
        "h": _clamp(win.get("h"), 560, 2000, DEFAULTS["window"]["h"]),
    }

    return out


def load() -> Dict[str, Any]:
    """Return saved settings merged over the defaults. Never raises."""
    try:
        path = config_path()
        if not os.path.isfile(path):
            return dict(DEFAULTS)
        with open(path, "r", encoding="utf-8") as fh:
            return _sanitise(json.load(fh))
    except Exception:
        return dict(DEFAULTS)


def save(settings: Dict[str, Any]) -> str:
    """Atomically write settings. Returns the path, or "" if it could not save."""
    try:
        path = config_path()
        part = f"{path}.part"
        with open(part, "w", encoding="utf-8") as fh:
            json.dump(_sanitise(settings), fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(part, path)
        return path
    except Exception:
        return ""


def reset() -> None:
    try:
        path = config_path()
        if os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass
