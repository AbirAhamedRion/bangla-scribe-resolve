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

- DaVinci Resolve **Studio** 18/19/20 (free edition has no scripting API)
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
- **Cleanup:** the temporary WAV and the temp copy of the SRT are always
  deleted. The imported SRT itself is kept in your chosen folder — Resolve
  links to it on disk, so deleting it would make the Media Pool clip offline.
- The render queue is cleared before and after each run; existing jobs are
  removed, so queue anything you need after generating subtitles.
