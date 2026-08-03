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
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import bn_srt
import model_cache
from cancellation import Cancelled, as_token



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
    """
    Thin wrapper that keeps the loaded model warm between runs.

    Two levels of caching are involved:

      * **Disk** — weights are downloaded once into ``model_cache.cache_root()``
        with a real progress bar, then reused forever (and offline).
      * **Process** — a loaded ``WhisperModel`` is kept on the instance and
        shared through :func:`get_transcriber`, so a second Generate in the
        same session skips the multi-second load entirely.
    """

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

    @property
    def is_warm(self) -> bool:
        return self._model is not None

    def unload(self) -> None:
        self._model = None
        self._loaded_key = None

    # -- model ------------------------------------------------------------
    def load(
        self,
        progress: Optional[ProgressFn] = None,
        cancelled: Optional[object] = None,
    ):
        from faster_whisper import WhisperModel  # imported lazily

        token = as_token(cancelled)
        device, compute_type = pick_compute_settings(self.prefer_gpu)
        key = (self.model_size, device, compute_type)
        if self._model is not None and self._loaded_key == key:
            if progress:
                progress(f"Model {self.model_size} already loaded — reusing it.", 33)
            return self._model

        # Step 1: make sure the weights are on disk (downloads once, resumable).
        local_path = model_cache.ensure_model(
            self.model_size, progress=progress, cancelled=token
        )
        token.check("model load")

        # Step 2: load from the cache. `local_path` is "" when the direct
        # download was unavailable — then faster-whisper fetches into the same
        # cache root itself, so the result is still reused next run.
        if progress:
            progress(
                f"Loading Whisper {self.model_size} ({device}/{compute_type})…", 34
            )
        self._model = WhisperModel(
            local_path or self.model_size,
            device=device,
            compute_type=compute_type,
            cpu_threads=self.cpu_threads,
            num_workers=1,
            download_root=None if local_path else model_cache.cache_root(),
        )
        self._loaded_key = key
        return self._model

    # -- transcription ----------------------------------------------------
    def transcribe(
        self,
        wav_path: str,
        progress: Optional[ProgressFn] = None,
        cancelled: Optional[object] = None,
        beam_size: int = 5,
        time_offset: float = 0.0,
    ) -> List[Segment]:
        """
        Transcribe `wav_path`. `time_offset` (seconds) is added to every
        timestamp — used when leading silence was trimmed off the file so cues
        still line up with the Resolve timeline.
        """
        token = as_token(cancelled)
        token.check("transcription")
        model = self.load(progress, cancelled=token)
        token.check("transcription")

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
        # faster-whisper decodes lazily, so this loop is our cancellation point:
        # it fires between segments, i.e. at most a second or two after Cancel.
        for seg in segments_iter:
            if token.cancelled:
                del segments_iter  # release the decoder before unwinding
                raise Cancelled("Cancelled during transcription.")

            text = (seg.text or "").strip()
            if text:
                out.append(
                    Segment(
                        float(seg.start) + time_offset,
                        float(seg.end) + time_offset,
                        text,
                    )
                )
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
# Process-wide warm cache
# --------------------------------------------------------------------------
_WARM: Dict[Tuple[str, bool], Transcriber] = {}


def get_transcriber(
    model_size: str = DEFAULT_MODEL, prefer_gpu: bool = True
) -> Transcriber:
    """Reuse an already-loaded Transcriber for this (model, gpu) combination."""
    key = (model_size, bool(prefer_gpu))
    engine = _WARM.get(key)
    if engine is None:
        engine = Transcriber(model_size, prefer_gpu)
        _WARM[key] = engine
    return engine


def release_transcribers() -> None:
    for engine in _WARM.values():
        engine.unload()
    _WARM.clear()


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

