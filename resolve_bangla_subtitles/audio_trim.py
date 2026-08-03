"""
audio_trim.py
-------------
Leading/trailing silence removal for the exported timeline WAV.

Resolve renders the whole timeline, so the file usually opens with a few
seconds of room tone or countdown and ends with tail handles. Whisper's VAD
still finds the speech, but the first cue frequently starts early and the last
one lingers. Trimming the file before transcription makes the subtitles line up
with the actual voice, and it also shortens the decode.

Implementation notes
--------------------
* stdlib only (``wave`` + ``array``) — ``audioop`` was removed in Python 3.13.
* Only the head and tail are removed; interior silence is untouched, so cue
  timings inside the speech stay exactly as Whisper reports them.
* The amount removed from the head is returned as ``offset`` and added back to
  every timestamp, so subtitles remain aligned with the Resolve timeline.
"""

from __future__ import annotations

import array
import os
import wave
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

ProgressFn = Callable[[str, int], None]

WINDOW_SECONDS = 0.02        # 20 ms analysis window
DEFAULT_THRESHOLD_DB = -45.0  # below this counts as silence
DEFAULT_PAD_SECONDS = 0.25    # keep a little air around the speech
MIN_KEEP_SECONDS = 0.5        # never trim down to nothing


@dataclass
class TrimResult:
    path: str            # file to transcribe (trimmed copy, or the original)
    offset: float        # seconds removed from the head; add back to timestamps
    trimmed_head: float
    trimmed_tail: float
    duration: float
    created_file: bool   # True when a new temp file was written

    @property
    def changed(self) -> bool:
        return self.trimmed_head > 0.001 or self.trimmed_tail > 0.001


_SAMPLE_CODE = {1: "b", 2: "h", 4: "i"}


def _window_levels(
    frames: bytes, sampwidth: int, channels: int, framerate: int
) -> Tuple[list[float], int]:
    """Return (peak amplitude per window, frames per window), normalised 0..1."""
    code = _SAMPLE_CODE.get(sampwidth)
    if code is None:
        return [], 0
    samples = array.array(code)
    samples.frombytes(frames)
    if sampwidth == 1:
        full = 128.0  # 8-bit WAV is unsigned; centre it
        samples = array.array("h", (s - 128 for s in samples))
    else:
        full = float(2 ** (8 * sampwidth - 1))

    per_window = max(1, int(framerate * WINDOW_SECONDS)) * channels
    levels: list[float] = []
    for i in range(0, len(samples), per_window):
        chunk = samples[i : i + per_window]
        if not chunk:
            break
        peak = max(abs(int(s)) for s in chunk)
        levels.append(peak / full)
    return levels, per_window // max(1, channels)


def _db(level: float) -> float:
    if level <= 0:
        return -120.0
    from math import log10

    return 20.0 * log10(level)


def trim_silence(
    wav_path: str,
    threshold_db: float = DEFAULT_THRESHOLD_DB,
    pad_seconds: float = DEFAULT_PAD_SECONDS,
    progress: Optional[ProgressFn] = None,
    pct: int = 34,
) -> TrimResult:
    """
    Write a copy of `wav_path` without its leading/trailing silence.

    Falls back to the original file (offset 0) for anything unexpected —
    exotic sample widths, compressed WAVs, unreadable headers — so this step
    can never break the pipeline.
    """
    try:
        with wave.open(wav_path, "rb") as wf:
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            duration = nframes / float(framerate or 1)
            if sampwidth not in _SAMPLE_CODE or nframes <= 0:
                return TrimResult(wav_path, 0.0, 0.0, 0.0, duration, False)
            frames = wf.readframes(nframes)
    except Exception:
        return TrimResult(wav_path, 0.0, 0.0, 0.0, 0.0, False)

    levels, frames_per_window = _window_levels(frames, sampwidth, channels, framerate)
    if not levels or frames_per_window <= 0:
        return TrimResult(wav_path, 0.0, 0.0, 0.0, duration, False)

    loud = [i for i, lv in enumerate(levels) if _db(lv) > threshold_db]
    if not loud:
        # Nothing above the floor: leave the audio alone rather than delete it.
        if progress:
            progress("No speech-level audio found; skipping silence trim.", pct)
        return TrimResult(wav_path, 0.0, 0.0, 0.0, duration, False)

    pad_windows = max(0, int(pad_seconds / WINDOW_SECONDS))
    first = max(0, loud[0] - pad_windows)
    last = min(len(levels) - 1, loud[-1] + pad_windows)

    start_frame = first * frames_per_window
    end_frame = min(nframes, (last + 1) * frames_per_window)
    if (end_frame - start_frame) < MIN_KEEP_SECONDS * framerate:
        return TrimResult(wav_path, 0.0, 0.0, 0.0, duration, False)

    head = start_frame / float(framerate)
    tail = (nframes - end_frame) / float(framerate)
    if head < 0.05 and tail < 0.05:
        if progress:
            progress("Audio already starts and ends on speech.", pct)
        return TrimResult(wav_path, 0.0, 0.0, 0.0, duration, False)

    bytes_per_frame = sampwidth * channels
    out_path = f"{os.path.splitext(wav_path)[0]}_trimmed.wav"
    try:
        with wave.open(out_path, "wb") as out:
            out.setnchannels(channels)
            out.setsampwidth(sampwidth)
            out.setframerate(framerate)
            out.writeframes(
                frames[start_frame * bytes_per_frame : end_frame * bytes_per_frame]
            )
    except Exception:
        return TrimResult(wav_path, 0.0, 0.0, 0.0, duration, False)

    if progress:
        progress(
            f"Trimmed silence — {head:.1f}s from the head, {tail:.1f}s from the tail.",
            pct,
        )
    return TrimResult(out_path, head, head, tail, duration, True)
