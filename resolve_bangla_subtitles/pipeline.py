"""
pipeline.py
-----------
Orchestrates Step A (export) -> B (transcribe) -> C (import) -> D (cleanup).
Kept UI-free so it can run headless:  python -m pipeline

Cancellation contract
---------------------
The caller passes a ``CancelToken`` (or any ``() -> bool`` predicate). Every
stage checks it at safe boundaries, the Resolve render is actively stopped,
and the SRT is written atomically (temp file + ``os.replace``) so a cancel can
never leave a truncated .srt on disk or a half-placed clip on the timeline.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from typing import Callable, Optional

import ai_engine
import audio_trim
import bn_srt
import resolve_api
import srt_repair
from cancellation import CancelToken, Cancelled, as_token


ProgressFn = Callable[[str, int], None]


@dataclass
class PipelineResult:
    srt_path: str
    segment_count: int
    kept_srt: bool
    placed_on_timeline: bool = False
    message: str = ""
    cancelled: bool = False
    repair_summary: str = ""
    trim_summary: str = ""


def run_pipeline(
    model_size: str = ai_engine.DEFAULT_MODEL,
    prefer_gpu: bool = True,
    keep_srt_copy: bool = True,
    output_dir: Optional[str] = None,
    max_chars: int = bn_srt.DEFAULT_MAX_CHARS,
    max_lines: int = bn_srt.DEFAULT_MAX_LINES,
    place_on_timeline: bool = True,
    trim_silence: bool = True,
    silence_threshold_db: float = audio_trim.DEFAULT_THRESHOLD_DB,
    progress: Optional[ProgressFn] = None,
    cancelled: Optional[object] = None,
    transcriber: Optional[ai_engine.Transcriber] = None,
) -> PipelineResult:
    def say(msg: str, pct: int) -> None:
        if progress:
            progress(msg, pct)

    token: CancelToken = as_token(cancelled)

    say("Connecting to DaVinci Resolve…", 1)
    token.check("startup")
    ctx = resolve_api.connect()
    version = ".".join(str(p) for p in resolve_api.resolve_version(ctx.resolve))
    say(f"Connected — {ctx.project_name} / {ctx.timeline_name} (Resolve {version})", 3)

    wav_path = ""
    trimmed_path = ""
    tmp_srt = ""
    final_srt = ""
    wrote_final = False
    trim_summary = ""
    repair_summary = ""
    try:
        token.check("audio export")
        wav_path = resolve_api.export_timeline_audio(
            ctx, progress=progress, cancelled=token
        )

        # Optional pre-pass: strip leading/trailing silence so the first and
        # last cues sit on the actual voice. The removed head is added back to
        # every timestamp, so timeline sync is preserved.
        offset = 0.0
        audio_for_whisper = wav_path
        if trim_silence:
            token.check("silence trim")
            say("Analysing audio for leading/trailing silence…", 33)
            trim = audio_trim.trim_silence(
                wav_path, threshold_db=silence_threshold_db, progress=progress
            )
            if trim.created_file:
                trimmed_path = trim.path
            audio_for_whisper = trim.path
            offset = trim.offset
            trim_summary = (
                f"Trimmed {trim.trimmed_head:.1f}s of head and "
                f"{trim.trimmed_tail:.1f}s of tail silence."
                if trim.changed
                else "No leading/trailing silence to trim."
            )

        token.check("transcription")
        engine = transcriber or ai_engine.get_transcriber(model_size, prefer_gpu)
        segments = engine.transcribe(
            audio_for_whisper, progress=progress, cancelled=token, time_offset=offset
        )
        if not segments:
            raise RuntimeError("No speech was detected in the timeline audio.")

        token.check("formatting")
        say("Formatting Bengali subtitles…", 88)
        cues = bn_srt.build_cues(segments, max_chars=max_chars, max_lines=max_lines)

        # Final safety pass: sort, de-overlap and sanitise every timestamp
        # before Resolve ever sees the file.
        say("Checking cue timings…", 90)
        cues, report = srt_repair.repair_cues(cues)
        repair_summary = report.summary()
        say(repair_summary, 91)
        if not cues:
            raise RuntimeError("Every cue was rejected by the timing check.")

        srt_text = bn_srt.cues_to_srt(cues)

        stamp = time.strftime("%Y%m%d_%H%M%S")
        base = f"{_safe(ctx.timeline_name)}_bn_{stamp}.srt"
        tmp_srt = os.path.join(tempfile.gettempdir(), "resolve_bangla_subs", base)
        os.makedirs(os.path.dirname(tmp_srt), exist_ok=True)
        _atomic_write(tmp_srt, srt_text)

        # Past this point the subtitle data is complete on disk. Cancelling now
        # would only discard finished work, so the last checkpoint is here.
        token.check("formatting")

        final_srt = tmp_srt
        kept = False
        if keep_srt_copy:
            # Resolve links to the file on disk, so the imported SRT must live
            # somewhere permanent. The temp copy is still cleaned up below.
            target_dir = output_dir or os.path.join(
                os.path.expanduser("~"), "Documents", "Resolve Bangla Subtitles"
            )
            os.makedirs(target_dir, exist_ok=True)
            final_srt = os.path.join(target_dir, base)
            shutil.copy2(tmp_srt, final_srt)
            kept = True
        wrote_final = True

        if place_on_timeline:
            placed, message = resolve_api.place_srt_on_timeline(
                ctx, final_srt, progress=progress
            )
        else:
            if resolve_api.import_srt(ctx, final_srt) is None:
                raise RuntimeError(
                    "Resolve could not import the SRT. The file is still "
                    f"available at: {final_srt}"
                )
            placed, message = False, "Imported into the Media Pool."

        say(message if placed else f"Finished — {message}", 100)
        return PipelineResult(
            final_srt,
            len(cues),
            kept,
            placed,
            message,
            repair_summary=repair_summary,
            trim_summary=trim_summary,
        )

    except Cancelled as stop:
        # Nothing partial survives a cancel: drop any half-produced SRT.
        if not wrote_final:
            _quiet_remove(final_srt)
        say(str(stop), 0)
        return PipelineResult("", 0, False, False, str(stop), cancelled=True)

    finally:
        # Step D - cleanup temporaries.
        _quiet_remove(wav_path)
        _quiet_remove(trimmed_path)
        if tmp_srt and (keep_srt_copy or not os.path.exists(tmp_srt)):
            _quiet_remove(tmp_srt)



def _atomic_write(path: str, text: str) -> None:
    """Write to a sibling .part file and rename, so readers never see a stub."""
    part = f"{path}.part"
    with open(part, "w", encoding="utf-8-sig", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(part, path)


def _safe(name: str) -> str:
    cleaned = "".join(c for c in name if c.isalnum() or c in ("-", "_", " ")).strip()
    return cleaned.replace(" ", "_") or "timeline"


def _quiet_remove(path: str) -> None:
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


if __name__ == "__main__":
    def _cli(msg: str, pct: int) -> None:
        print(f"[{pct:3d}%] {msg}")

    result = run_pipeline(progress=_cli)
    if result.cancelled:
        print("\nCancelled — nothing was written.")
    else:
        print(f"\nSRT: {result.srt_path}  ({result.segment_count} cues)")
        print(result.message)
