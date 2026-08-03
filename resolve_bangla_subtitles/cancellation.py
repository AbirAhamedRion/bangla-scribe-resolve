"""
cancellation.py
---------------
One tiny, dependency-free cancellation primitive shared by the GUI, the
pipeline, the Resolve automation and the Whisper engine.

Design goals:
  * thread-safe (the GUI thread sets it, the worker thread reads it)
  * cooperative — every long loop calls ``token.check()`` so we never kill a
    thread mid-write and never leave a half-written .srt behind
  * distinguishable from real errors, so the UI can say "Cancelled" instead of
    showing a red failure.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional


class Cancelled(Exception):
    """Raised when the user aborted the run. Not an error condition."""

    def __init__(self, message: str = "Cancelled by user.") -> None:
        super().__init__(message)


class CancelToken:
    """A one-way flag with optional abort hooks (e.g. stop a Resolve render)."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._hooks: list[Callable[[], None]] = []

    # -- state ------------------------------------------------------------
    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def __bool__(self) -> bool:  # allows `if token:`
        return self.cancelled

    def __call__(self) -> bool:  # allows passing the token as `cancelled=`
        return self.cancelled

    def cancel(self) -> None:
        """Flag the run and fire every registered abort hook exactly once."""
        if self._event.is_set():
            return
        self._event.set()
        with self._lock:
            hooks, self._hooks = list(self._hooks), []
        for hook in hooks:
            try:
                hook()
            except Exception:
                pass  # an abort hook must never mask the cancellation itself

    def reset(self) -> None:
        self._event.clear()
        with self._lock:
            self._hooks = []

    # -- cooperative checkpoints -----------------------------------------
    def check(self, stage: str = "") -> None:
        if self._event.is_set():
            raise Cancelled(f"Cancelled by user{f' during {stage}' if stage else ''}.")

    def wait(self, seconds: float) -> bool:
        """Interruptible sleep. Returns True if cancellation woke us early."""
        return self._event.wait(seconds)

    # -- abort hooks ------------------------------------------------------
    def add_hook(self, hook: Callable[[], None]) -> None:
        """Register an abort action (e.g. ``project.StopRendering``)."""
        if self._event.is_set():
            try:
                hook()
            except Exception:
                pass
            return
        with self._lock:
            self._hooks.append(hook)

    def remove_hook(self, hook: Callable[[], None]) -> None:
        with self._lock:
            if hook in self._hooks:
                self._hooks.remove(hook)


def as_token(cancelled: Optional[object]) -> CancelToken:
    """Accept a CancelToken, a plain callable, or None and return a token."""
    if isinstance(cancelled, CancelToken):
        return cancelled
    token = CancelToken()
    if callable(cancelled):
        # Bridge a legacy `lambda: bool` predicate onto the token lazily.
        original_check = token.check

        def check(stage: str = "") -> None:
            if cancelled():  # type: ignore[operator]
                token.cancel()
            original_check(stage)

        token.check = check  # type: ignore[method-assign]
        token.__call__ = lambda: bool(cancelled()) or token.cancelled  # type: ignore[assignment]
    return token
