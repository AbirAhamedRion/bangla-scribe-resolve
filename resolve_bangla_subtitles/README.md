# Bangla Subtitle Studio — DaVinci Resolve Studio plugin

Local, offline Bengali subtitle generation for the active Resolve timeline.
Audio is exported by Resolve, transcribed on your machine with
`faster-whisper` (CTranslate2), formatted into clean Bengali cues, then
imported **and placed automatically onto a subtitle track** of your timeline.

```
app.py          PySide6 GUI (frameless dark glass UI, QSS in style.qss)
pipeline.py     Orchestrates export -> transcribe -> format -> place -> cleanup
resolve_api.py  All DaVinci Resolve scripting (render queue, subtitle track)
ai_engine.py    faster-whisper wrapper
bn_srt.py       Bengali punctuation, cue splitting, line wrapping, SRT output
style.qss       Premium dark theme
```


## 1. Requirements

- DaVinci Resolve **Studio** 18/19/20/21 (free edition has no scripting API)
- Python 3.10–3.12 (64-bit)
- ~3 GB free disk for the `large-v3` model (downloaded once, cached in
  `~/.cache/huggingface`)

## 2. Install

```bash
cd resolve_bangla_subtitles
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
```

GPU (optional, NVIDIA only): install the CUDA 12 build of cuDNN/cuBLAS; the app
auto-detects CUDA and switches to `float16`. Otherwise it runs `int8` on CPU,
which uses roughly 2 GB RAM and is the safe default on a standard laptop.

## 3. Enable Resolve scripting

Resolve → **Preferences → System → General** → set
*External scripting using* = **Local**, then restart Resolve.

If the app can't find the API, set these env vars before running:

**Windows**
```
set RESOLVE_SCRIPT_API=C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting
set RESOLVE_SCRIPT_LIB=C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll
```

**macOS**
```
export RESOLVE_SCRIPT_API="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
export RESOLVE_SCRIPT_LIB="/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
```

**Linux**
```
export RESOLVE_SCRIPT_API="/opt/resolve/Developer/Scripting"
export RESOLVE_SCRIPT_LIB="/opt/resolve/libs/Fusion/fusionscript.so"
```

## 4. Run

Open Resolve, load a project and a timeline, then:

```bash
python app.py          # GUI
python pipeline.py     # headless CLI, same pipeline
```

Click **Generate Bengali Subtitles**. The app adds a subtitle track if your
timeline has none, imports the `.srt` and drops it on that track for you — no
dragging. Select the track and style it once from the Inspector to format every
caption at the same time.

### Formatting controls

- **Max characters per line** (20–70, default 42) — the readability budget for
  each line.
- **Lines** (1–3, default 2) — maximum rows per caption.
- **Place subtitles on the timeline** — turn off if you only want the SRT in
  the Media Pool.

What the formatter does (`bn_srt.py`):

- normalises Bengali punctuation: Latin `.` after Bengali text becomes a danda
  `।`, `...` becomes `…`, `।।` becomes `॥`, spacing around punctuation is
  fixed, and ZWSP/BOM noise is stripped
- splits over-long Whisper segments at sentence (`। ॥ ? ! …`) and then clause
  (`, ; : —`) boundaries, re-timing each new cue in proportion to its length
- wraps lines only at safe break points — never before a matra, hasant (্),
  ZWJ/ZWNJ or trailing punctuation, so conjuncts never split — and balances
  two-line cues so the rows are similar lengths
- enforces a 0.7 s minimum / 7 s maximum cue duration and removes overlaps


## 5. Where to place the scripts (optional Resolve menu entry)

Copy the folder into Resolve's Utility scripts directory so it shows up under
**Workspace → Scripts**:

- Windows: `%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\`
- macOS: `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/`
- Linux: `/opt/resolve/Fusion/Scripts/Utility/`

Resolve's embedded Python usually has no PySide6, so add a tiny launcher next
to it that shells out to your venv:

```python
# BanglaSubtitles.py  (in the Utility folder)
import subprocess, os
PLUGIN = r"C:\path\to\resolve_bangla_subtitles"
PYTHON = os.path.join(PLUGIN, ".venv", "Scripts", "python.exe")  # .venv/bin/python on mac/linux
subprocess.Popen([PYTHON, os.path.join(PLUGIN, "app.py")], cwd=PLUGIN)
```

## 6. Notes on behaviour

- **Language is locked to `bn`** and `condition_on_previous_text` is disabled,
  which prevents the repetition loops Whisper falls into on Bengali speech.
- **Timeline placement:** the app appends to a subtitle track via the Media
  Pool, falling back to `Timeline.ImportIntoTimeline()`. If an older Resolve
  build refuses both, it says so and the clip is still waiting in the Media
  Pool to drag manually.
- **Cleanup:** the temporary WAV and the temp copy of the SRT are always
  deleted. The imported SRT itself is kept in your chosen folder — Resolve
  links to it on disk, so deleting it would make the Media Pool clip offline.

- The render queue is cleared before and after each run; existing jobs are
  removed, so queue anything you need after generating subtitles.

## Model caching, timing repair & silence trim

**Automatic model caching** (`model_cache.py`)
Weights are downloaded once into `~/.cache/resolve_bangla_subtitles/models`
(override with the `RBS_MODEL_CACHE` environment variable) with a real
byte-level progress bar, and the download is cancellable and resumable. The
Engine panel shows whether the selected model is cached and offers a
**Clear cache** button. A loaded model is also kept warm in-process
(`ai_engine.get_transcriber`), so a second run in the same session skips
loading entirely.

**Timing repair** (`srt_repair.py`)
Before the SRT is written, every cue is sorted chronologically, de-duplicated,
and checked for overlaps, zero/negative durations, NaN or negative starts and
runaway lengths. Corrections are applied automatically and summarised in the
log (e.g. "Timing repaired — fixed 2 overlapping, 1 bad duration cue(s)").
`srt_repair.validate()` confirms nothing invalid remains.

**Silence trimming** (`audio_trim.py`)
Optional pre-pass that removes leading and trailing silence from the exported
WAV (stdlib only — no ffmpeg, no `audioop`), with an adjustable threshold
(-70 … -25 dB, default -45 dB) and a 0.25 s pad. Interior silence is left
alone, and the removed head is added back to every timestamp so the subtitles
stay in sync with the timeline. Trimmed temp files are deleted with the rest.

## Transcript caching & saved settings

**Transcript cache (`transcript_cache.py`)** — after each successful run the
segments are stored as JSON in
`~/.cache/resolve_bangla_subtitles/transcripts` (override with
`RBS_TRANSCRIPT_CACHE`). The key is a fast content fingerprint of the exported
WAV (file size + SHA-256 of evenly spaced 128 KB chunks) combined with the
model, language and silence-trim settings. Re-running the same timeline skips
both the trim pass and Whisper entirely — subtitles regenerate in seconds, so
you can freely tweak line length or lines-per-caption. Edit the timeline and
the fingerprint changes, forcing a fresh transcription. Turn it off with the
"Reuse the cached transcript" checkbox; the last 40 entries are kept (LRU).

**Saved settings (`settings_store.py`)** — model, GPU toggle, silence trim and
threshold, max characters per line, lines per caption, timeline placement,
transcript reuse, output folder and window size are written to JSON on every
run and on close, then restored at startup:

- Windows: `%APPDATA%\ResolveBanglaSubtitles\settings.json`
- macOS: `~/Library/Application Support/ResolveBanglaSubtitles/settings.json`
- Linux: `~/.config/resolve_bangla_subtitles/settings.json`

Override the location with `RBS_CONFIG`. Values are clamped to valid ranges on
load, so a stale or hand-edited file can never break the UI.

## DaVinci Resolve 21

Resolve 21 is fully supported. Module discovery probes every product folder
Blackmagic ships (`DaVinci Resolve`, `DaVinci Resolve Studio`,
`DaVinci Resolve 21`, `DaVinci Resolve 20`) across ProgramData, %APPDATA%, both
Program Files roots, `/Library/Application Support`, per-user macOS paths and
`/opt/resolve`, and auto-fills `RESOLVE_SCRIPT_API` / `RESOLVE_SCRIPT_LIB` from
the first candidate that exists.


## Choosing which timeline (and how much of it) to transcribe

The **Source** section at the top of the window lists every timeline in the
open project:

- **Timeline** — pick any timeline, not just the one currently open. The
  selection is made current in Resolve before rendering, and it is remembered
  for next launch. Press **Refresh** after creating or renaming timelines.
- **Transcribe only the In/Out range** — mark In (`I`) and Out (`O`) in Resolve
  and only that span is rendered and transcribed. Cue timestamps are shifted by
  the In point, so the subtitles still land at the right place on the full
  timeline. If no marks are set, the run stops with a clear message instead of
  silently captioning everything.

Partial runs are cached separately from full-timeline runs, so a range and the
whole timeline never overwrite each other's transcripts.


## Window and layout

- Default window is roughly 8 × 6 inches (800 × 600 px at 96 dpi) with a
  740 × 560 minimum, so no label ever elides or overflows.
- Full window controls: **close**, **minimise** and **maximise/restore** in the
  macOS-style traffic-light cluster, plus a bottom-right size grip and drag
  anywhere on the frame.
- The settings and progress area scrolls, so shrinking the window reveals a
  scrollbar instead of squashing the controls.


## Turning it into a desktop application

The app is already a standalone desktop window. To ship it as a
double-clickable executable (no Python required on the target machine):

```bash
pip install pyinstaller
python build_desktop.py
```

Output lands in `dist/`:

| OS | Result |
|---|---|
| Windows | `dist/BanglaSubtitleStudio.exe` |
| macOS | `dist/BanglaSubtitleStudio.app` |
| Linux | `dist/BanglaSubtitleStudio` |

Notes:

- Build on the OS you want to ship for — PyInstaller does not cross-compile.
- Whisper weights are not bundled; they download once on first run into the
  model cache, so the executable stays a few hundred MB rather than several GB.
- Drop an `icon.ico` (Windows) or `icon.icns` (macOS) next to `app.py` before
  building to brand the executable.
- The user still needs DaVinci Resolve installed with **Preferences → System →
  General → External scripting using = Local**.
