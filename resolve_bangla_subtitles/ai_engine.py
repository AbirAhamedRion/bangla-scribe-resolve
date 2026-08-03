"""
ai_engine.py
------------
Local Bengali transcription with faster-whisper (CTranslate2).

No cloud calls. Defaults are tuned so a mainstream laptop (e.g. a Lenovo
with 8-16 GB RAM and no discrete GPU) can run large-v3 without being killed:
int8 quantisation on CPU, VAD filtering to skip silence, and a bounded
worker/thread count.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional

import bn_srt


ProgressFn = Callable[[str, int], None]

DEFAULT_MODEL = "large-v3"
LANGUAGE = "bn"


@dataclass
class Segment:
    start: float
    end: float
    text: str


def pick_compute_settings(prefer_gpu: bool = True) -> tuple[str, str]:
    """
    Return (device, compute_type).

    CUDA -> float16 (fast, needs ~5 GB VRAM for large-v3)
    CPU  -> int8    (~2 GB RAM, the safe default on laptops)
    """
    if prefer_gpu:
        try:
            import ctranslate2  # type: ignore

            if ctranslate2.get_cuda_device_count() > 0:
                return "cuda", "float16"
        except Exception:
            pass
    return "cpu", "int8"


class Transcriber:
    """Thin wrapper that keeps the loaded model warm between runs."""

    def __init__(
        self,
        model_size: str = DEFAULT_MODEL,
        prefer_gpu: bool = True,
        cpu_threads: Optional[int] = None,
    ) -> None:
        self.model_size = model_size
        self.prefer_gpu = prefer_gpu
        self.cpu_threads = cpu_threads or max(2, min(8, (os.cpu_count() or 4)))
        self._model = None
        self._loaded_key: Optional[tuple] = None

    # -- model ------------------------------------------------------------
    def load(self, progress: Optional[ProgressFn] = None):
        from faster_whisper import WhisperModel  # imported lazily

        device, compute_type = pick_compute_settings(self.prefer_gpu)
        key = (self.model_size, device, compute_type)
        if self._model is not None and self._loaded_key == key:
            return self._model

        if progress:
            progress(
                f"Loading Whisper {self.model_size} ({device}/{compute_type})… "
                "first run downloads the model.",
                35,
            )
        self._model = WhisperModel(
            self.model_size,
            device=device,
            compute_type=compute_type,
            cpu_threads=self.cpu_threads,
            num_workers=1,
        )
        self._loaded_key = key
        return self._model

    # -- transcription ----------------------------------------------------
    def transcribe(
        self,
        wav_path: str,
        progress: Optional[ProgressFn] = None,
        cancelled: Optional[Callable[[], bool]] = None,
        beam_size: int = 5,
    ) -> List[Segment]:
        model = self.load(progress)

        if progress:
            progress("Transcribing Bengali audio…", 40)

        segments_iter, info = model.transcribe(
            wav_path,
            language=LANGUAGE,
            task="transcribe",
            beam_size=beam_size,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,  # avoids Bengali repetition loops
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            word_timestamps=False,
        )

        total = float(getattr(info, "duration", 0.0) or 0.0)
        out: List[Segment] = []
        for seg in segments_iter:
            if cancelled and cancelled():
                raise RuntimeError("Transcription cancelled.")
            text = (seg.text or "").strip()
            if text:
                out.append(Segment(float(seg.start), float(seg.end), text))
            if progress and total > 0:
                frac = min(1.0, float(seg.end) / total)
                progress(
                    f"Transcribing… {int(frac * 100)}%",
                    40 + int(frac * 45),
                )
        if progress:
            progress(f"Transcribed {len(out)} segments.", 86)
        return out


# --------------------------------------------------------------------------
# SRT writing (Bengali-aware formatting lives in bn_srt.py)
# --------------------------------------------------------------------------
def segments_to_srt(
    segments: Iterable[Segment],
    max_chars: int = bn_srt.DEFAULT_MAX_CHARS,
    max_lines: int = bn_srt.DEFAULT_MAX_LINES,
) -> str:
    """Normalise, re-split and wrap segments, then render them as SRT text."""
    cues = bn_srt.build_cues(segments, max_chars=max_chars, max_lines=max_lines)
    return bn_srt.cues_to_srt(cues)


def write_srt(
    segments: Iterable[Segment],
    srt_path: str,
    max_chars: int = bn_srt.DEFAULT_MAX_CHARS,
    max_lines: int = bn_srt.DEFAULT_MAX_LINES,
) -> str:
    with open(srt_path, "w", encoding="utf-8-sig", newline="\n") as fh:
        fh.write(segments_to_srt(segments, max_chars=max_chars, max_lines=max_lines))
    return srt_path

