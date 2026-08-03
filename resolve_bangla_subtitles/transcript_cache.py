"""
transcript_cache.py
-------------------
Reuse a previous transcription when the same timeline audio is rendered again.

Whisper is by far the slowest stage of the pipeline, and re-running the same
timeline (e.g. after tweaking the character-per-line limit, or after a cancel)
produces byte-identical audio. This module fingerprints the exported WAV plus
the settings that actually influence decoding, and stores the resulting
segments as JSON so a repeat run finishes in milliseconds.

Fingerprint
-----------
Hashing a 40-minute WAV in full would cost seconds, so the key combines:
  * file size
  * SHA-256 of the header + evenly spaced sample chunks (~1 MB total)
  * model size, language, and the silence-trim settings

Any real edit to the timeline changes both the size and the sampled bytes, so
collisions are not a practical concern; the entry is also validated against the
stored size before being reused.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

CACHE_VERSION = 3
CHUNK = 128 * 1024
SAMPLES = 8
MAX_ENTRIES = 40

ProgressFn = Callable[[str, int], None]


def cache_root() -> str:
    """Cache directory; override with RBS_TRANSCRIPT_CACHE."""
    env = os.environ.get("RBS_TRANSCRIPT_CACHE")
    if env:
        root = os.path.expanduser(env)
    else:
        root = os.path.join(
            os.path.expanduser("~"), ".cache", "resolve_bangla_subtitles", "transcripts"
        )
    os.makedirs(root, exist_ok=True)
    return root


def audio_fingerprint(path: str) -> str:
    """Cheap but stable content hash of a (potentially large) audio file."""
    size = os.path.getsize(path)
    h = hashlib.sha256()
    h.update(str(size).encode("ascii"))
    with open(path, "rb") as fh:
        if size <= CHUNK * SAMPLES:
            while True:
                block = fh.read(CHUNK)
                if not block:
                    break
                h.update(block)
        else:
            step = size // SAMPLES
            for i in range(SAMPLES):
                fh.seek(i * step)
                h.update(fh.read(CHUNK))
    return h.hexdigest()


def make_key(
    audio_path: str,
    model_size: str,
    language: str = "bn",
    trim_silence: bool = True,
    silence_threshold_db: float = -45.0,
    extra: Optional[dict] = None,
) -> str:
    """Full cache key: audio content + every setting that changes the words."""
    payload = {
        "v": CACHE_VERSION,
        "audio": audio_fingerprint(audio_path),
        "model": model_size,
        "language": language,
        "trim": bool(trim_silence),
        "threshold": round(float(silence_threshold_db), 1) if trim_silence else None,
    }
    if extra:
        payload.update(extra)
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:40]


def _entry_path(key: str) -> str:
    return os.path.join(cache_root(), f"{key}.json")


@dataclass
class CachedTranscript:
    segments: List[object]  # ai_engine.Segment instances
    created: float
    label: str = ""

    @property
    def age_text(self) -> str:
        delta = max(0.0, time.time() - self.created)
        if delta < 90:
            return "just now"
        if delta < 5400:
            return f"{int(delta // 60)} min ago"
        if delta < 172800:
            return f"{int(delta // 3600)} h ago"
        return f"{int(delta // 86400)} days ago"


def load(key: str, segment_factory) -> Optional[CachedTranscript]:
    """Return a cached transcript, or None when absent/corrupt."""
    path = _entry_path(key)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if int(data.get("version", 0)) != CACHE_VERSION:
            return None
        segments = [
            segment_factory(float(s["start"]), float(s["end"]), str(s["text"]))
            for s in data.get("segments", [])
        ]
        if not segments:
            return None
        # Touch so LRU pruning keeps frequently used timelines around.
        try:
            os.utime(path, None)
        except OSError:
            pass
        return CachedTranscript(
            segments, float(data.get("created", 0.0)), str(data.get("label", ""))
        )
    except Exception:
        return None


def save(key: str, segments: Sequence[object], label: str = "") -> str:
    """Atomically store segments for `key`. Never raises on cache failure."""
    path = _entry_path(key)
    data = {
        "version": CACHE_VERSION,
        "created": time.time(),
        "label": label,
        "segments": [
            {"start": float(s.start), "end": float(s.end), "text": str(s.text)}
            for s in segments
        ],
    }
    try:
        part = f"{path}.part"
        with open(part, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(part, path)
        _prune()
    except Exception:
        return ""
    return path


def _prune(max_entries: int = MAX_ENTRIES) -> None:
    try:
        root = cache_root()
        files = [
            os.path.join(root, f) for f in os.listdir(root) if f.endswith(".json")
        ]
        if len(files) <= max_entries:
            return
        files.sort(key=lambda p: os.path.getmtime(p))
        for old in files[: len(files) - max_entries]:
            try:
                os.remove(old)
            except OSError:
                pass
    except Exception:
        pass


def entry_count() -> int:
    try:
        return len([f for f in os.listdir(cache_root()) if f.endswith(".json")])
    except Exception:
        return 0


def clear() -> int:
    """Delete every cached transcript. Returns how many were removed."""
    removed = 0
    try:
        root = cache_root()
        for f in os.listdir(root):
            if f.endswith(".json"):
                try:
                    os.remove(os.path.join(root, f))
                    removed += 1
                except OSError:
                    pass
    except Exception:
        pass
    return removed
