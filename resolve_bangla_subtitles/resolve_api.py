"""
resolve_api.py
--------------
All DaVinci Resolve automation lives here:
  * connecting to a running Resolve instance
  * rendering the active timeline to a temporary WAV (audio only)
  * importing a finished .srt back into the Media Pool

Nothing in this module imports PySide6 or faster-whisper, so it can be
unit-tested / driven from a plain console script too.
"""

from __future__ import annotations

import os
import sys
import time
import tempfile
from dataclasses import dataclass
from typing import Callable, Optional

ProgressFn = Callable[[str, int], None]  # (message, percent 0-100)


# --------------------------------------------------------------------------
# Resolve module bootstrap
# --------------------------------------------------------------------------
def _candidate_module_paths() -> list[str]:
    """Standard install locations of DaVinciResolveScript.py per OS."""
    paths: list[str] = []
    env = os.environ.get("RESOLVE_SCRIPT_API")
    if env:
        paths.append(os.path.join(env, "Modules"))

    if sys.platform.startswith("win"):
        pd = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        paths.append(
            os.path.join(
                pd,
                "Blackmagic Design",
                "DaVinci Resolve",
                "Support",
                "Developer",
                "Scripting",
                "Modules",
            )
        )
    elif sys.platform == "darwin":
        paths.append(
            "/Library/Application Support/Blackmagic Design/DaVinci Resolve/"
            "Developer/Scripting/Modules"
        )
    else:  # Linux
        paths.append("/opt/resolve/Developer/Scripting/Modules")
        paths.append("/home/resolve/Developer/Scripting/Modules")
    return paths


def get_resolve():
    """Return the Resolve app object, raising a helpful error if unavailable."""
    # Inside Resolve's own console the global already exists.
    try:
        return resolve  # type: ignore[name-defined]  # noqa: F821
    except NameError:
        pass

    last_err: Optional[Exception] = None
    for p in _candidate_module_paths():
        if p and os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)
    try:
        import DaVinciResolveScript as dvr  # type: ignore
    except Exception as exc:  # pragma: no cover
        last_err = exc
        raise RuntimeError(
            "Could not import DaVinciResolveScript.\n"
            "Make sure DaVinci Resolve Studio is installed and that external "
            "scripting is enabled (Preferences > System > General > "
            "'External scripting using' = Local).\n"
            f"Underlying error: {last_err}"
        )

    app = dvr.scriptapp("Resolve")
    if app is None:
        raise RuntimeError(
            "DaVinci Resolve is not running, or external scripting is disabled. "
            "Open Resolve, load a project, then try again."
        )
    return app


@dataclass
class ResolveContext:
    resolve: object
    project_manager: object
    project: object
    timeline: object

    @property
    def timeline_name(self) -> str:
        return self.timeline.GetName()

    @property
    def project_name(self) -> str:
        return self.project.GetName()


def connect() -> ResolveContext:
    app = get_resolve()
    pm = app.GetProjectManager()
    project = pm.GetCurrentProject()
    if project is None:
        raise RuntimeError("No project is open in DaVinci Resolve.")
    timeline = project.GetCurrentTimeline()
    if timeline is None:
        raise RuntimeError("No timeline is open in the current project.")
    return ResolveContext(app, pm, project, timeline)


# --------------------------------------------------------------------------
# Step A - export timeline audio to a temp WAV
# --------------------------------------------------------------------------
def export_timeline_audio(
    ctx: ResolveContext,
    progress: Optional[ProgressFn] = None,
    poll_seconds: float = 1.0,
) -> str:
    """
    Clear the render queue, configure an 'audio only' WAV render of the whole
    current timeline and render it into the OS temp directory.

    Returns the absolute path of the rendered .wav file.
    """

    def say(msg: str, pct: int) -> None:
        if progress:
            progress(msg, pct)

    project = ctx.project
    say("Preparing render queue…", 2)

    # Resolve must be on the Deliver page for render settings to apply cleanly.
    try:
        ctx.resolve.OpenPage("deliver")
    except Exception:
        pass

    project.DeleteAllRenderJobs()

    out_dir = os.path.join(tempfile.gettempdir(), "resolve_bangla_subs")
    os.makedirs(out_dir, exist_ok=True)

    safe_name = "".join(
        c for c in ctx.timeline_name if c.isalnum() or c in ("-", "_", " ")
    ).strip().replace(" ", "_") or "timeline"
    base_name = f"{safe_name}_{int(time.time())}"

    # Start from Resolve's built-in audio-only preset when present.
    for preset in ("Audio Only", "audio only"):
        try:
            if project.LoadRenderPreset(preset):
                break
        except Exception:
            pass

    say("Configuring WAV (audio only) render…", 6)
    settings = {
        "SelectAllFrames": True,
        "TargetDir": out_dir,
        "CustomName": base_name,
        "ExportVideo": False,
        "ExportAudio": True,
        "AudioCodec": "lpcm",          # uncompressed PCM
        "AudioBitDepth": 16,
        "AudioSampleRate": 48000,
        "FormatWidth": 1920,           # ignored for audio-only, kept for safety
        "FormatHeight": 1080,
    }
    if not project.SetRenderSettings(settings):
        # Some builds reject unknown keys; retry with a minimal set.
        project.SetRenderSettings(
            {
                "SelectAllFrames": True,
                "TargetDir": out_dir,
                "CustomName": base_name,
                "ExportVideo": False,
                "ExportAudio": True,
            }
        )

    try:
        project.SetCurrentRenderFormatAndCodec("wav", "lpcm")
    except Exception:
        pass

    job_id = project.AddRenderJob()
    if not job_id:
        raise RuntimeError(
            "Resolve refused to queue the render job. Check that the timeline "
            "has audio and that the Deliver page settings are valid."
        )

    say("Rendering timeline audio…", 10)
    project.StartRendering([job_id], isInteractiveMode=False)

    while project.IsRenderingInProgress():
        status = {}
        try:
            status = project.GetRenderJobStatus(job_id) or {}
        except Exception:
            pass
        pct = int(status.get("CompletionPercentage", 0) or 0)
        say(f"Rendering timeline audio… {pct}%", 10 + int(pct * 0.20))
        time.sleep(poll_seconds)

    status = project.GetRenderJobStatus(job_id) or {}
    if status.get("JobStatus") not in (None, "Complete"):
        raise RuntimeError(
            f"Audio render failed: {status.get('JobStatus')} "
            f"{status.get('Error', '')}".strip()
        )

    project.DeleteAllRenderJobs()

    wav_path = _find_rendered_file(out_dir, base_name)
    if not wav_path:
        raise RuntimeError(
            f"Render finished but no audio file was found in {out_dir}."
        )
    say("Audio export complete.", 30)
    return wav_path


def _find_rendered_file(out_dir: str, base_name: str) -> Optional[str]:
    """Resolve may append the timeline name/extension, so match by prefix."""
    best: Optional[str] = None
    for fn in os.listdir(out_dir):
        if not fn.startswith(base_name):
            continue
        if os.path.splitext(fn)[1].lower() not in (".wav", ".aif", ".aiff"):
            continue
        path = os.path.join(out_dir, fn)
        if best is None or os.path.getmtime(path) > os.path.getmtime(best):
            best = path
    return best


# --------------------------------------------------------------------------
# Step C - import the SRT into the Media Pool
# --------------------------------------------------------------------------
def import_srt(ctx: ResolveContext, srt_path: str) -> bool:
    """Import the generated .srt into the current Media Pool folder."""
    media_pool = ctx.project.GetMediaPool()
    try:
        ctx.resolve.OpenPage("edit")
    except Exception:
        pass
    items = media_pool.ImportMedia([srt_path])
    return bool(items)
