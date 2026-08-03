"""
pipeline.py
-----------
Orchestrates Step A (export) -> B (transcribe) -> C (import) -> D (cleanup).
Kept UI-free so it can run headless:  python -m pipeline
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from typing import Callable, Optional

import ai_engine
import resolve_api

ProgressFn = Callable[[str, int], None]


@dataclass
class PipelineResult:
    srt_path: str
    segment_count: int
    kept_srt: bool


def run_pipeline(
    model_size: str = ai_engine.DEFAULT_MODEL,
    prefer_gpu: bool = True,
    keep_srt_copy: bool = True,
    output_dir: Optional[str] = None,
    progress: Optional[ProgressFn] = None,
    cancelled: Optional[Callable[[], bool]] = None,
    transcriber: Optional[ai_engine.Transcriber] = None,
) -> PipelineResult:
    def say(msg: str, pct: int) -> None:
        if progress:
            progress(msg, pct)

    def check() -> None:
        if cancelled and cancelled():
            raise RuntimeError("Cancelled by user.")

    say("Connecting to DaVinci Resolve…", 1)
    ctx = resolve_api.connect()
    say(f"Connected — {ctx.project_name} / {ctx.timeline_name}", 3)

    wav_path = ""
    tmp_srt = ""
    try:
        check()
        wav_path = resolve_api.export_timeline_audio(ctx, progress=progress)

        check()
        engine = transcriber or ai_engine.Transcriber(model_size, prefer_gpu)
        segments = engine.transcribe(wav_path, progress=progress, cancelled=cancelled)
        if not segments:
            raise RuntimeError("No speech was detected in the timeline audio.")

        check()
        stamp = time.strftime("%Y%m%d_%H%M%S")
        base = f"{_safe(ctx.timeline_name)}_bn_{stamp}.srt"
        tmp_srt = os.path.join(tempfile.gettempdir(), "resolve_bangla_subs", base)
        os.makedirs(os.path.dirname(tmp_srt), exist_ok=True)
        ai_engine.write_srt(segments, tmp_srt)
        say("Importing subtitles into the Media Pool…", 90)

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

        if not resolve_api.import_srt(ctx, final_srt):
            raise RuntimeError(
                "Resolve could not import the SRT. The file is still available "
                f"at: {final_srt}"
            )

        say("Done — drag the SRT from the Media Pool onto a subtitle track.", 100)
        return PipelineResult(final_srt, len(segments), kept)

    finally:
        # Step D - cleanup temporaries.
        _quiet_remove(wav_path)
        if tmp_srt and (keep_srt_copy or not os.path.exists(tmp_srt)):
            _quiet_remove(tmp_srt)


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
    print(f"\nSRT: {result.srt_path}  ({result.segment_count} segments)")
