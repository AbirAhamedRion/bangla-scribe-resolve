"""
srt_repair.py
-------------
Final safety pass over generated cues before anything reaches Resolve.

Whisper occasionally emits timestamps that are fine individually but invalid as
a subtitle file: segments that arrive out of chronological order, cues that
overlap the next one, zero- or negative-length cues, NaN/negative starts, and
duplicated text at identical times. Resolve either refuses such an SRT or
silently drops cues, so we normalise them here.

The pass is deterministic and reports exactly what it changed so the fixes can
be shown in the log.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Sequence

from bn_srt import Cue

MIN_DURATION = 0.30      # shorter than this is unreadable / invalid in Resolve
MIN_GAP = 0.04           # frame-ish separation so cues never touch
MAX_DURATION = 10.0      # a runaway cue is almost always a timestamp glitch


@dataclass
class RepairReport:
    reordered: int = 0
    overlaps_fixed: int = 0
    durations_fixed: int = 0
    negatives_fixed: int = 0
    duplicates_merged: int = 0
    empty_removed: int = 0
    notes: List[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            self.reordered
            + self.overlaps_fixed
            + self.durations_fixed
            + self.negatives_fixed
            + self.duplicates_merged
            + self.empty_removed
        )

    def summary(self) -> str:
        if self.total == 0:
            return "Timing check passed — no overlaps or out-of-order cues."
        parts = []
        if self.reordered:
            parts.append(f"{self.reordered} out-of-order")
        if self.overlaps_fixed:
            parts.append(f"{self.overlaps_fixed} overlapping")
        if self.durations_fixed:
            parts.append(f"{self.durations_fixed} bad duration")
        if self.negatives_fixed:
            parts.append(f"{self.negatives_fixed} negative/invalid")
        if self.duplicates_merged:
            parts.append(f"{self.duplicates_merged} duplicate")
        if self.empty_removed:
            parts.append(f"{self.empty_removed} empty")
        return "Timing repaired — fixed " + ", ".join(parts) + " cue(s)."


def _clean_number(value: float, fallback: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return fallback
    if math.isnan(f) or math.isinf(f) or f < 0:
        return fallback
    return f


def repair_cues(
    cues: Sequence[Cue], report: RepairReport | None = None
) -> tuple[List[Cue], RepairReport]:
    """
    Return a chronologically sorted, non-overlapping, positive-duration copy
    of `cues` plus a report of what was corrected.
    """
    rep = report or RepairReport()

    # 1. Drop empties and sanitise the numbers themselves.
    cleaned: List[Cue] = []
    for cue in cues:
        text = (cue.text or "").strip()
        if not text:
            rep.empty_removed += 1
            continue
        start = _clean_number(cue.start, 0.0)
        end = _clean_number(cue.end, start + MIN_DURATION)
        if start != cue.start or end != cue.end:
            rep.negatives_fixed += 1
        cleaned.append(Cue(start, end, text))

    if not cleaned:
        return [], rep

    # 2. Chronological order. Count how many cues actually moved.
    ordered = sorted(cleaned, key=lambda c: (c.start, c.end))
    if ordered != cleaned:
        rep.reordered = sum(1 for a, b in zip(cleaned, ordered) if a is not b)
        if rep.reordered:
            rep.notes.append("Segments were re-sorted into chronological order.")

    # 3. Merge exact duplicates (same text at effectively the same time).
    merged: List[Cue] = []
    for cue in ordered:
        if merged:
            prev = merged[-1]
            if prev.text == cue.text and abs(prev.start - cue.start) < 0.05:
                merged[-1] = Cue(prev.start, max(prev.end, cue.end), prev.text)
                rep.duplicates_merged += 1
                continue
        merged.append(cue)

    # 4. Walk forward, removing overlaps and enforcing sane durations.
    fixed: List[Cue] = []
    for i, cue in enumerate(merged):
        start, end = cue.start, cue.end

        if fixed and start < fixed[-1].end + MIN_GAP:
            start = fixed[-1].end + MIN_GAP
            rep.overlaps_fixed += 1

        if end <= start:
            end = start + MIN_DURATION
            rep.durations_fixed += 1
        elif end - start > MAX_DURATION:
            end = start + MAX_DURATION
            rep.durations_fixed += 1
        elif end - start < MIN_DURATION:
            end = start + MIN_DURATION
            rep.durations_fixed += 1

        # Never grow past the next cue's start; shrink instead of overlapping.
        if i + 1 < len(merged):
            ceiling = merged[i + 1].start - MIN_GAP
            if end > ceiling > start:
                end = ceiling
                rep.overlaps_fixed += 1

        fixed.append(Cue(start, end, cue.text))

    return fixed, rep


def validate(cues: Sequence[Cue]) -> List[str]:
    """Return human-readable problems left in `cues` (should be empty after repair)."""
    problems: List[str] = []
    for i, cue in enumerate(cues):
        if cue.end <= cue.start:
            problems.append(f"Cue {i + 1} has a non-positive duration.")
        if i and cue.start < cues[i - 1].end:
            problems.append(f"Cue {i + 1} overlaps cue {i}.")
    return problems
