# Bangla Subtitle Studio

Act as an expert Python Developer and DaVinci Resolve API Specialist. 

I want to build a fully functional, local, GUI-based plugin for DaVinci Resolve Studio that automatically extracts timeline audio, transcribes it into highly accurate Bengali (Bangla) subtitles using faster-whisper, and injects those subtitles back into the Resolve timeline.

Here are the strict requirements and architectural guidelines for the project:

### 1. Technology Stack
*   *Backend & API:* Python 3 (DaVinci Resolve native scripting environment).
*   *AI Engine:* faster-whisper (running locally using CTranslate2). Do not use cloud APIs. Optimize the compute settings (e.g., INT8) so it runs efficiently on standard hardware like a Lenovo laptop without crashing.
*   *GUI Framework:* PySide6. 

### 2. UI/UX Design Requirements
*   The application must be a standalone desktop window that runs alongside DaVinci Resolve.
*   Apply advanced QSS (Qt Style Sheets) to give the UI an ultra-premium, modern SaaS aesthetic. 
*   It should feature a sleek dark mode theme, rounded corners, subtle glassmorphism effects, and a macOS-inspired clean layout.
*   Include clear visual feedback (status labels or progress bars) so the user knows exactly what step the process is on.

### 3. Core Logic & DaVinci Resolve API Quirks
Because the Resolve API cannot read timeline audio directly into memory, the script must follow this exact sequence:

*   *Step A: Auto-Export Audio:* Write a function that connects to the active Resolve project, clears the render queue, configures a "WAV Audio Only" render preset, and exports the current timeline to the OS temporary directory (tempfile.gettempdir()). Monitor the render job until complete.
*   *Step B: AI Transcription:* Feed the temp .wav file into a local faster-whisper model. Force the model to large-v3 and set language="bn" for maximum Bengali accuracy. Extract the start, end, and text data for each spoken segment.
*   *Step C: Timeline Injection:* Instead of modifying Text+ nodes directly (which is slow and unstable via Python), format the Whisper output into a standard .srt file format and save it locally. Then, use project.GetMediaPool().ImportMedia() to bring the SRT into Resolve so the user can drag it onto a subtitle track and apply global formatting. 
*   *Step D: Cleanup:* Automatically delete the temporary .wav and .srt files from the local drive once the process is complete to save space.

### Output Requirements
Please provide the complete, production-ready Python codebase broken down into logical files (e.g., app.py for the GUI, resolve_api.py for timeline automation, and ai_engine.py for Whisper). Include instructions on how to run it and where to place the scripts for DaVinci Resolve to recognize them.

This project was built with [Lovable](https://lovable.dev).

**Live app**: https://bangla-scribe-resolve.lovable.app

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/e81715f1-6400-489b-9a91-d0266f694d25).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
