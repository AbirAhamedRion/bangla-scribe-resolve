"""
model_cache.py
--------------
Persistent, cancellable caching for faster-whisper (CTranslate2) weights.

Why this exists
---------------
``WhisperModel("large-v3")`` downloads ~3 GB from the Hugging Face hub the
first time it is constructed, with no progress reporting reaching our UI. This
module:

  * pins a stable cache directory that survives virtualenv rebuilds
    (``RBS_MODEL_CACHE`` env var, else ``~/.cache/resolve_bangla_subtitles``)
  * reports byte-level download progress through the normal ``progress(msg, pct)``
    callback, so the GUI can show a real bar instead of freezing
  * makes the download cancellable — the CancelToken is checked on every
    chunk update, and a partial download simply resumes next time
  * detects an already-cached model and skips straight to loading, which is
    what makes the second and every later run start almost instantly
"""

from __future__ import annotations

import os
import shutil
from typing import Callable, Optional

from cancellation import Cancelled, as_token

ProgressFn = Callable[[str, int], None]

# Official CTranslate2 conversions used by faster-whisper.
MODEL_REPOS = {
    "large-v3": "Systran/faster-whisper-large-v3",
    "large-v2": "Systran/faster-whisper-large-v2",
    "medium": "Systran/faster-whisper-medium",
    "small": "Systran/faster-whisper-small",
    "base": "Systran/faster-whisper-base",
    "tiny": "Systran/faster-whisper-tiny",
}

# Rough download sizes, only used for a friendlier first-run message.
APPROX_SIZE_GB = {
    "large-v3": 3.1,
    "large-v2": 3.1,
    "medium": 1.5,
    "small": 0.5,
    "base": 0.15,
    "tiny": 0.08,
}


def cache_root() -> str:
    """Where converted model weights live between runs."""
    env = os.environ.get("RBS_MODEL_CACHE")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache"
    )
    return os.path.join(base, "resolve_bangla_subtitles", "models")


def model_dir(model_size: str) -> str:
    return os.path.join(cache_root(), model_size.replace("/", "_"))


def is_cached(model_size: str) -> bool:
    """True when the weights are already on disk and look complete."""
    d = model_dir(model_size)
    if not os.path.isdir(d):
        return False
    weights = os.path.join(d, "model.bin")
    if not os.path.isfile(weights) or os.path.getsize(weights) < 1_000_000:
        return False
    # tokenizer.json is optional on a few conversions; config.json is not.
    return os.path.isfile(os.path.join(d, "config.json"))


def cached_size_bytes(model_size: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(model_dir(model_size)):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def clear_cache(model_size: Optional[str] = None) -> None:
    """Delete one cached model, or the whole cache when model_size is None."""
    target = model_dir(model_size) if model_size else cache_root()
    shutil.rmtree(target, ignore_errors=True)


# --------------------------------------------------------------------------
# Download with progress
# --------------------------------------------------------------------------
def _progress_tqdm_class(report: Callable[[int, int], None], token):
    """Build a tqdm subclass huggingface_hub can use to stream progress."""
    from tqdm.auto import tqdm as _tqdm  # hub already depends on tqdm

    class _HookedTqdm(_tqdm):  # pragma: no cover - exercised only with network
        def update(self, n=1):
            token.check("model download")
            result = super().update(n)
            try:
                report(int(self.n or 0), int(self.total or 0))
            except Cancelled:
                raise
            except Exception:
                pass
            return result

    return _HookedTqdm


def ensure_model(
    model_size: str,
    progress: Optional[ProgressFn] = None,
    cancelled: Optional[object] = None,
    pct_start: int = 6,
    pct_end: int = 32,
) -> str:
    """
    Make sure `model_size` is present in the local cache and return its path.

    Returns the directory to hand to ``WhisperModel(...)``. When the model is
    already cached this is a couple of ``stat`` calls, so warm runs skip the
    network entirely (and work fully offline).
    """
    token = as_token(cancelled)
    token.check("model download")
    target = model_dir(model_size)

    if is_cached(model_size):
        if progress:
            gb = cached_size_bytes(model_size) / 1_073_741_824
            progress(f"Model {model_size} found in cache ({gb:.1f} GB).", pct_start)
        return target

    repo = MODEL_REPOS.get(model_size)
    if not repo:
        # Unknown/custom name (or a local path) — let faster-whisper resolve it,
        # but still keep everything under our cache root.
        if os.path.isdir(model_size):
            return model_size
        return model_size

    approx = APPROX_SIZE_GB.get(model_size, 1.0)
    if progress:
        progress(
            f"Downloading Whisper {model_size} (~{approx:.1f} GB) — one time only…",
            pct_start,
        )

    span = max(1, pct_end - pct_start)

    def report(done: int, total: int) -> None:
        if not progress:
            return
        if total > 0:
            frac = min(1.0, done / total)
            progress(
                f"Downloading {model_size}… {done / 1_048_576:.0f} / "
                f"{total / 1_048_576:.0f} MB",
                pct_start + int(frac * span),
            )
        else:
            progress(f"Downloading {model_size}… {done / 1_048_576:.0f} MB", pct_start)

    os.makedirs(target, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download

        kwargs = dict(
            repo_id=repo,
            local_dir=target,
            allow_patterns=["*.bin", "*.json", "*.txt", "*.model"],
        )
        try:
            snapshot_download(tqdm_class=_progress_tqdm_class(report, token), **kwargs)
        except TypeError:
            # Older hub versions do not accept tqdm_class.
            snapshot_download(**kwargs)
    except Cancelled:
        # A partial snapshot is safe: the hub resumes it on the next attempt,
        # and is_cached() stays False so we never load half a model.
        raise
    except Exception as exc:
        if progress:
            progress(
                f"Direct download unavailable ({exc}); falling back to "
                "faster-whisper's own downloader…",
                pct_start,
            )
        return ""  # caller falls back to download_root=cache_root()

    token.check("model download")
    if progress:
        progress(f"Model {model_size} cached — future runs start instantly.", pct_end)
    return target
