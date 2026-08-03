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

from cancellation import CancelToken, Cancelled, as_token

ProgressFn = Callable[[str, int], None]  # (message, percent 0-100)


# --------------------------------------------------------------------------
# Resolve module bootstrap
# --------------------------------------------------------------------------
def _candidate_module_paths() -> list[str]:
    """
    Standard install locations of DaVinciResolveScript.py per OS.

    Covers Resolve 17 through the current 19.x / 20.x builds, including the
    per-user Fusion path Blackmagic added for the newer installers and the
    portable "Studio"-suffixed folders.

    Resolve 21 keeps the same layout but ships more product-named folders
    (``DaVinci Resolve Studio``, ``DaVinci Resolve 21``), so every known
    variant is probed.
    """
    paths: list[str] = []
    env = os.environ.get("RESOLVE_SCRIPT_API")
    if env:
        paths.append(os.path.join(env, "Modules"))

    products = (
        "DaVinci Resolve",
        "DaVinci Resolve Studio",
        "DaVinci Resolve 21",
        "DaVinci Resolve 20",
    )

    if sys.platform.startswith("win"):
        pd = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        appdata = os.environ.get("APPDATA", "")
        pfs = [
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("ProgramW6432", r"C:\Program Files"),
        ]
        for product in products:
            paths.append(
                os.path.join(
                    pd, "Blackmagic Design", product,
                    "Support", "Developer", "Scripting", "Modules",
                )
            )
            if appdata:
                paths.append(
                    os.path.join(
                        appdata, "Blackmagic Design", product,
                        "Support", "Developer", "Scripting", "Modules",
                    )
                )
            for pf in pfs:
                paths.append(
                    os.path.join(
                        pf, "Blackmagic Design", product,
                        "Developer", "Scripting", "Modules",
                    )
                )
        if appdata:
            paths.append(
                os.path.join(appdata, "Blackmagic Design", "Fusion", "Modules")
            )
    elif sys.platform == "darwin":
        for product in products:
            paths.append(
                "/Library/Application Support/Blackmagic Design/"
                f"{product}/Developer/Scripting/Modules"
            )
            paths.append(
                os.path.expanduser(
                    "~/Library/Application Support/Blackmagic Design/"
                    f"{product}/Developer/Scripting/Modules"
                )
            )
            paths.append(
                f"/Applications/{product}/{product}.app/Contents/Libraries/Fusion"
            )
    else:  # Linux
        paths.append("/opt/resolve/Developer/Scripting/Modules")
        paths.append("/opt/resolve/libs/Fusion/Modules")
        paths.append("/home/resolve/Developer/Scripting/Modules")
        paths.append(os.path.expanduser("~/.local/share/DaVinciResolve/Developer/Scripting/Modules"))
    return paths


def _ensure_library_env() -> None:
    """
    Newer Resolve builds (19, 20 and 21) need RESOLVE_SCRIPT_API /
    RESOLVE_SCRIPT_LIB to be set before DaVinciResolveScript can locate
    fusionscript. Fill in sane defaults when the installer did not export them
    (common on Windows and macOS), trying every product folder in turn.
    """
    products = (
        "DaVinci Resolve",
        "DaVinci Resolve Studio",
        "DaVinci Resolve 21",
        "DaVinci Resolve 20",
    )
    api_candidates: list[str] = []
    lib_candidates: list[str] = []

    if sys.platform.startswith("win"):
        pd = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        appdata = os.environ.get("APPDATA", "")
        pfs = [
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("ProgramW6432", r"C:\Program Files"),
        ]
        for product in products:
            api_candidates.append(
                os.path.join(
                    pd, "Blackmagic Design", product,
                    "Support", "Developer", "Scripting",
                )
            )
            if appdata:
                api_candidates.append(
                    os.path.join(
                        appdata, "Blackmagic Design", product,
                        "Support", "Developer", "Scripting",
                    )
                )
            for pf in pfs:
                lib_candidates.append(
                    os.path.join(
                        pf, "Blackmagic Design", product, "fusionscript.dll"
                    )
                )
    elif sys.platform == "darwin":
        for product in products:
            api_candidates.append(
                "/Library/Application Support/Blackmagic Design/"
                f"{product}/Developer/Scripting"
            )
            lib_candidates.append(
                f"/Applications/{product}/{product}.app/Contents/"
                "Libraries/Fusion/fusionscript.so"
            )
    else:
        api_candidates.append("/opt/resolve/Developer/Scripting")
        lib_candidates.append("/opt/resolve/libs/Fusion/fusionscript.so")

    if not os.environ.get("RESOLVE_SCRIPT_API"):
        for api in api_candidates:
            if os.path.isdir(api):
                os.environ["RESOLVE_SCRIPT_API"] = api
                break
    if not os.environ.get("RESOLVE_SCRIPT_LIB"):
        for lib in lib_candidates:
            if os.path.isfile(lib):
                os.environ["RESOLVE_SCRIPT_LIB"] = lib
                break



def get_resolve():
    """Return the Resolve app object, raising a helpful error if unavailable."""
    # Inside Resolve's own console the global already exists.
    try:
        return resolve  # type: ignore[name-defined]  # noqa: F821
    except NameError:
        pass

    _ensure_library_env()
    last_err: Optional[Exception] = None
    for p in _candidate_module_paths():
        if p and os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)

    dvr = None
    try:
        import DaVinciResolveScript as dvr  # type: ignore
    except Exception as exc:  # pragma: no cover
        last_err = exc
        # Resolve 19/20 also ship a bare `fusionscript` module that exposes the
        # same scriptapp() entry point; try it before giving up.
        try:
            import fusionscript as dvr  # type: ignore
            last_err = None
        except Exception as exc2:
            last_err = exc2

    if dvr is None:
        raise RuntimeError(
            "Could not import DaVinciResolveScript.\n"
            "Make sure DaVinci Resolve (18 through 21) is installed and that "
            "external scripting is enabled: Preferences > System > General > "
            "'External scripting using' = Local.\n"
            f"Underlying error: {last_err}"
        )

    app = dvr.scriptapp("Resolve")
    if app is None:
        raise RuntimeError(
            "DaVinci Resolve is not running, or external scripting is disabled. "
            "Open Resolve, load a project, then try again."
        )
    return app


def resolve_version(app) -> tuple[int, ...]:
    """Best-effort (major, minor, patch) of the running Resolve build."""
    try:
        parts = app.GetVersion()  # [major, minor, patch, build, suffix]
        return tuple(int(p) for p in parts[:3])
    except Exception:
        pass
    try:
        return tuple(int(p) for p in str(app.GetVersionString()).split(".")[:3])
    except Exception:
        return (0,)



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
    cancelled: Optional[object] = None,
) -> str:
    """
    Clear the render queue, configure an 'audio only' WAV render of the whole
    current timeline and render it into the OS temp directory.

    Cancellation-safe: if the token is tripped while Resolve is rendering, the
    job is stopped, removed from the queue and any partial file is deleted.

    Returns the absolute path of the rendered .wav file.
    """

    def say(msg: str, pct: int) -> None:
        if progress:
            progress(msg, pct)

    token = as_token(cancelled)
    project = ctx.project
    token.check("audio export")
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

    token.check("audio export")
    job_id = project.AddRenderJob()
    if not job_id:
        raise RuntimeError(
            "Resolve refused to queue the render job. Check that the timeline "
            "has audio and that the Deliver page settings are valid."
        )

    def _abort_render() -> None:
        try:
            project.StopRendering()
        except Exception:
            pass

    token.add_hook(_abort_render)

    say("Rendering timeline audio…", 10)
    try:
        project.StartRendering([job_id], isInteractiveMode=False)

        while project.IsRenderingInProgress():
            if token.cancelled:
                _abort_render()
                break
            status = {}
            try:
                status = project.GetRenderJobStatus(job_id) or {}
            except Exception:
                pass
            pct = int(status.get("CompletionPercentage", 0) or 0)
            say(f"Rendering timeline audio… {pct}%", 10 + int(pct * 0.20))
            # Interruptible wait so Cancel reacts within ~100 ms.
            if token.wait(min(poll_seconds, 0.25)):
                continue
    finally:
        token.remove_hook(_abort_render)

    if token.cancelled:
        # Wait briefly for Resolve to release the file, then bin the partial WAV.
        for _ in range(20):
            try:
                if not project.IsRenderingInProgress():
                    break
            except Exception:
                break
            time.sleep(0.1)
        try:
            project.DeleteAllRenderJobs()
        except Exception:
            pass
        partial = _find_rendered_file(out_dir, base_name)
        if partial:
            try:
                os.remove(partial)
            except OSError:
                pass
        raise Cancelled("Cancelled during audio export — render stopped cleanly.")

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
# Step C - import the SRT and place it on a subtitle track
# --------------------------------------------------------------------------
def import_srt(ctx: ResolveContext, srt_path: str):
    """Import the generated .srt into the current Media Pool folder."""
    media_pool = ctx.project.GetMediaPool()
    try:
        ctx.resolve.OpenPage("edit")
    except Exception:
        pass
    items = media_pool.ImportMedia([srt_path])
    if not items:
        return None
    return items[0]


def ensure_subtitle_track(ctx: ResolveContext) -> int:
    """Return the index of a subtitle track, adding one if the timeline has none."""
    timeline = ctx.timeline
    try:
        count = int(timeline.GetTrackCount("subtitle") or 0)
    except Exception:
        count = 0
    if count == 0:
        try:
            timeline.AddTrack("subtitle")
        except Exception as exc:
            raise RuntimeError(f"Could not add a subtitle track: {exc}")
        try:
            count = int(timeline.GetTrackCount("subtitle") or 1)
        except Exception:
            count = 1
    return max(1, count)


def place_srt_on_timeline(
    ctx: ResolveContext,
    srt_path: str,
    progress: Optional[ProgressFn] = None,
) -> tuple[bool, str]:
    """
    Import the SRT and drop it onto a subtitle track of the active timeline.

    Returns (placed, message). `placed` is False when Resolve imported the file
    but refused the automatic edit — the caller should then tell the user to
    drag it from the Media Pool.
    """

    def say(msg: str, pct: int) -> None:
        if progress:
            progress(msg, pct)

    say("Importing subtitles into the Media Pool…", 90)
    item = import_srt(ctx, srt_path)
    if item is None:
        raise RuntimeError(
            f"Resolve could not import the SRT. It is still on disk at: {srt_path}"
        )

    say("Placing subtitles on the timeline…", 94)
    track_index = ensure_subtitle_track(ctx)
    media_pool = ctx.project.GetMediaPool()

    # Preferred path: an explicit subtitle-track append (Resolve 18.5+).
    clip_info = {
        "mediaPoolItem": item,
        "startFrame": 0,
        "trackIndex": track_index,
        "mediaType": 3,  # 1 = video, 2 = audio, 3 = subtitle
    }
    for info in (clip_info, {k: v for k, v in clip_info.items() if k != "mediaType"}):
        try:
            appended = media_pool.AppendToTimeline([info])
        except Exception:
            appended = None
        if appended:
            return True, f"Subtitles placed on subtitle track {track_index}."

    # Fallback: let Resolve import the file straight into the timeline.
    for options in (
        {"importSubtitle": True, "autoImportSourceClipsIntoMediaPool": False},
        None,
    ):
        try:
            ok = (
                ctx.timeline.ImportIntoTimeline(srt_path, options)
                if options is not None
                else ctx.timeline.ImportIntoTimeline(srt_path)
            )
        except Exception:
            ok = False
        if ok:
            return True, "Subtitles imported into the timeline."

    return (
        False,
        "The SRT is in the Media Pool, but this Resolve build refused the "
        "automatic edit — drag it onto a subtitle track to finish.",
    )

