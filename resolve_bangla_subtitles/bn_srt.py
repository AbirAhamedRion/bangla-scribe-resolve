"""
bn_srt.py
---------
Bengali-aware subtitle formatting.

Whisper returns one long, loosely punctuated run of text per segment. For
readable captions in Resolve we need to:

  * normalise Bengali punctuation (danda ।, ellipses, stray spaces, Latin
    full stops used mid-Bengali, ZWNJ/ZWSP noise)
  * split over-long segments into several cues at sentence/clause boundaries,
    re-timing each cue proportionally to its character length
  * wrap each cue onto at most N lines of at most `max_chars` characters,
    breaking only at safe points — never before a matra, hasant (্),
    ZWJ/ZWNJ, or a closing punctuation mark, so conjuncts stay intact
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence

# Combining marks / joiners that must never start a line.
BN_COMBINING = (
    "\u0981\u0982\u0983"          # candrabindu, anusvara, visarga
    "\u09bc"                       # nukta
    "\u09be\u09bf\u09c0\u09c1\u09c2\u09c3\u09c4"  # aa..vocalic rr matras
    "\u09c7\u09c8\u09cb\u09cc"    # e, ai, o, au matras
    "\u09cd"                       # hasant / virama
    "\u09d7"                       # au length mark
    "\u200c\u200d"                 # ZWNJ, ZWJ
)
# Punctuation that must stay glued to the preceding word.
TRAILING_PUNCT = "।॥,;:?!.\u2026)]}\"'"

SENTENCE_END = re.compile(r"(?<=[।॥?!\u2026])\s+")
CLAUSE_SPLIT = re.compile(r"(?<=[,;:—–-])\s+")

DEFAULT_MAX_CHARS = 42
DEFAULT_MAX_LINES = 2
MIN_CUE_SECONDS = 0.7
MAX_CUE_SECONDS = 7.0
MIN_GAP_SECONDS = 0.04


@dataclass
class Cue:
    start: float
    end: float
    text: str


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------
def normalize_bengali(text: str) -> str:
    t = text.strip()
    if not t:
        return ""

    t = t.replace("\u200b", "").replace("\ufeff", "")
    t = re.sub(r"[ \t\r\n]+", " ", t)

    # Whisper often emits a Latin full stop after Bengali text; make it a danda.
    t = re.sub(r"(?<=[\u0980-\u09ff])\s*\.(?=\s|$)", "।", t)
    t = t.replace("...", "\u2026").replace("।।", "॥")

    # No space before punctuation, exactly one after.
    t = re.sub(r"\s+([।॥,;:?!\u2026])", r"\1", t)
    t = re.sub(r"([।॥,;:?!\u2026])(?=[^\s\d])", r"\1 ", t)

    # Collapse repeated punctuation and stray quotes/hyphen runs.
    t = re.sub(r"([।॥?!,])\1+", r"\1", t)
    t = re.sub(r"\s*-{2,}\s*", " — ", t)
    t = re.sub(r"\s{2,}", " ", t)

    return t.strip(" -–—")


# --------------------------------------------------------------------------
# Line wrapping
# --------------------------------------------------------------------------
def _safe_break(token: str) -> bool:
    """A token may start a new line only if it doesn't open with a mark."""
    return bool(token) and token[0] not in BN_COMBINING and token[0] not in TRAILING_PUNCT


def wrap_text(text: str, max_chars: int = DEFAULT_MAX_CHARS,
              max_lines: int = DEFAULT_MAX_LINES) -> str:
    """Wrap into <= max_lines balanced lines, breaking only at safe points."""
    text = text.strip()
    if len(text) <= max_chars:
        return text

    tokens = text.split(" ")
    lines: List[str] = []
    cur = ""
    for tok in tokens:
        candidate = f"{cur} {tok}".strip()
        if cur and len(candidate) > max_chars and _safe_break(tok):
            lines.append(cur)
            cur = tok
        else:
            cur = candidate
    if cur:
        lines.append(cur)

    if len(lines) <= max_lines:
        return _balance(lines, max_chars) if len(lines) == 2 else "\n".join(lines)

    # Too many lines: merge the tail so the cue never exceeds max_lines.
    head = lines[: max_lines - 1]
    head.append(" ".join(lines[max_lines - 1:]))
    return "\n".join(head)


def _balance(lines: Sequence[str], max_chars: int) -> str:
    """Even out a two-line cue so the first line isn't visibly longer."""
    words = (lines[0] + " " + lines[1]).split(" ")
    best = "\n".join(lines)
    best_delta = abs(len(lines[0]) - len(lines[1]))
    for i in range(1, len(words)):
        if not _safe_break(words[i]):
            continue
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if len(a) > max_chars or len(b) > max_chars:
            continue
        delta = abs(len(a) - len(b))
        if delta < best_delta:
            best_delta, best = delta, f"{a}\n{b}"
    return best


# --------------------------------------------------------------------------
# Cue splitting
# --------------------------------------------------------------------------
def _split_sentences(text: str, budget: int) -> List[str]:
    parts = [p for p in SENTENCE_END.split(text) if p.strip()]
    out: List[str] = []
    for part in parts:
        if len(part) <= budget:
            out.append(part.strip())
            continue
        clauses = [c for c in CLAUSE_SPLIT.split(part) if c.strip()]
        buf = ""
        for clause in clauses:
            candidate = f"{buf} {clause}".strip()
            if buf and len(candidate) > budget:
                out.append(buf)
                buf = clause.strip()
            else:
                buf = candidate
        if buf:
            out.append(buf)
    # Anything still oversized gets a hard word-level split.
    final: List[str] = []
    for chunk in out:
        if len(chunk) <= budget:
            final.append(chunk)
            continue
        words, buf = chunk.split(" "), ""
        for w in words:
            candidate = f"{buf} {w}".strip()
            if buf and len(candidate) > budget:
                final.append(buf)
                buf = w
            else:
                buf = candidate
        if buf:
            final.append(buf)
    return final


def build_cues(
    segments: Iterable,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_lines: int = DEFAULT_MAX_LINES,
) -> List[Cue]:
    """
    Turn raw Whisper segments into readable cues.

    `segments` is any iterable of objects with .start/.end/.text.
    """
    budget = max(12, max_chars * max_lines)
    cues: List[Cue] = []

    for seg in segments:
        text = normalize_bengali(getattr(seg, "text", "") or "")
        if not text:
            continue
        start = float(seg.start)
        end = max(float(seg.end), start + 0.2)

        chunks = _split_sentences(text, budget) if len(text) > budget else [text]
        total_chars = sum(len(c) for c in chunks) or 1
        cursor = start
        span = end - start
        for i, chunk in enumerate(chunks):
            share = span * (len(chunk) / total_chars)
            c_end = end if i == len(chunks) - 1 else cursor + share
            cues.append(Cue(cursor, max(c_end, cursor + 0.2), wrap_text(chunk, max_chars, max_lines)))
            cursor = c_end

    return _fix_timings(cues)


def _fix_timings(cues: List[Cue]) -> List[Cue]:
    """Enforce minimum/maximum durations and remove overlaps."""
    out: List[Cue] = []
    for cue in cues:
        start, end = cue.start, cue.end
        if out and start < out[-1].end + MIN_GAP_SECONDS:
            start = out[-1].end + MIN_GAP_SECONDS
        end = max(end, start + MIN_CUE_SECONDS)
        end = min(end, start + MAX_CUE_SECONDS)
        # Never push past the next cue's original start.
        out.append(Cue(start, end, cue.text))
    for i in range(len(out) - 1):
        if out[i].end > out[i + 1].start - MIN_GAP_SECONDS:
            out[i] = Cue(
                out[i].start,
                max(out[i].start + 0.2, out[i + 1].start - MIN_GAP_SECONDS),
                out[i].text,
            )
    return out


# --------------------------------------------------------------------------
# SRT rendering
# --------------------------------------------------------------------------
def srt_timestamp(seconds: float) -> str:
    if seconds < 0 or math.isnan(seconds):
        seconds = 0.0
    ms_total = int(round(seconds * 1000))
    h, rem = divmod(ms_total, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def cues_to_srt(cues: Iterable[Cue]) -> str:
    blocks: List[str] = []
    for i, cue in enumerate(cues, start=1):
        blocks.append(
            f"{i}\n{srt_timestamp(cue.start)} --> {srt_timestamp(cue.end)}\n{cue.text}\n"
        )
    return "\n".join(blocks)
