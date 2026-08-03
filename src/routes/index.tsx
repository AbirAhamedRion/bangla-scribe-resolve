import { createFileRoute, Link } from "@tanstack/react-router";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Bangla Subtitle Studio — Offline Bengali Subtitles for Resolve" },
      {
        name: "description",
        content:
          "A local PySide6 plugin that exports timeline audio, transcribes Bengali with faster-whisper large-v3 and places clean SRT subtitles on your DaVinci Resolve timeline.",
      },
      {
        property: "og:title",
        content: "Bangla Subtitle Studio — Offline Bengali Subtitles for Resolve",
      },
      {
        property: "og:description",
        content:
          "Export, transcribe and place Bengali subtitles inside DaVinci Resolve 18–20. 100% on-device, cancel-safe, no cloud APIs.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

const FEATURES = [
  {
    kicker: "01",
    title: "One-click timeline audio export",
    body: "Clears the render queue, configures a WAV / LPCM audio-only preset and renders your active timeline straight to the OS temp folder — no manual Deliver-page setup.",
  },
  {
    kicker: "02",
    title: "faster-whisper large-v3, locally",
    body: "CTranslate2 with INT8 on CPU or float16 on CUDA, VAD silence skipping and bounded threads, so a mainstream laptop finishes without swapping or crashing.",
  },
  {
    kicker: "03",
    title: "Download once, start instantly",
    body: "Model weights are cached to disk with a real progress bar — cancellable and resumable — and kept warm in memory, so every run after the first begins immediately and fully offline.",
  },
  {
    kicker: "04",
    title: "Bengali-aware line breaking",
    body: "Normalises dari (।), fixes punctuation spacing and never breaks a line before a matra, hasant or ZWJ — conjuncts stay intact and two-line cues stay balanced.",
  },
  {
    kicker: "05",
    title: "Automatic timing repair",
    body: "A final pass sorts cues, merges duplicates and removes overlaps, zero-length and negative timestamps, so Resolve never receives an SRT it would reject or silently drop.",
  },
  {
    kicker: "06",
    title: "Silence trimming",
    body: "Optionally strips leading and trailing room tone before transcription at an adjustable threshold, then adds the offset back so cues stay perfectly in sync with the timeline.",
  },
  {
    kicker: "07",
    title: "Automatic timeline placement",
    body: "Creates a subtitle track when your timeline has none, appends the SRT to it, and falls back to ImportIntoTimeline on older builds. No dragging from the Media Pool.",
  },
  {
    kicker: "08",
    title: "Cancel-safe at every stage",
    body: "Cancel stops the Resolve render, unwinds the decoder between segments and deletes partial files. The UI never freezes and no truncated SRT ever reaches your timeline.",
  },
  {
    kicker: "09",
    title: "Private by construction",
    body: "No cloud APIs, no telemetry, no account. Audio and transcripts never leave the machine, and temporary WAV files are deleted after every run.",
  },
];

const STEPS = [
  {
    n: "A",
    title: "Export",
    body: "Connects to the running Resolve instance, renders the current timeline to a temporary 48 kHz WAV and polls the job until it completes.",
  },
  {
    n: "B",
    title: "Transcribe",
    body: "Feeds the WAV to faster-whisper with language locked to bn, emitting start/end/text for every spoken segment with live progress.",
  },
  {
    n: "C",
    title: "Format & place",
    body: "Re-splits long segments at sentence and clause boundaries, writes the SRT atomically, then drops it on a subtitle track of your timeline.",
  },
  {
    n: "D",
    title: "Clean up",
    body: "Removes the temporary WAV and temp SRT, keeping only the permanent copy Resolve links to, so nothing bloats your drive.",
  },
];

const FAQ = [
  {
    q: "Is DaVinci Resolve Studio required?",
    a: "Scripting from an external Python process is a Studio feature, so Studio is required for the desktop app. The free build can still use the generated .srt by importing it manually.",
  },
  {
    q: "Which Resolve versions are supported?",
    a: "Resolve 18, 18.5, 19, 20 and 21. The plugin auto-discovers the scripting modules on Windows, macOS and Linux — including the newer per-user Fusion module paths — and falls back to the bare fusionscript module when DaVinciResolveScript is missing.",
  },
  {
    q: "How long does a transcription take?",
    a: "On CPU with INT8, expect roughly 1–2× realtime with large-v3 on a modern 8-core laptop. With a CUDA GPU in float16 it is typically 5–15× realtime. Switch to medium or small in the Engine panel for faster drafts.",
  },
  {
    q: "What happens if I hit Cancel?",
    a: "The render is stopped through the Resolve API, the Whisper decoder unwinds at the next segment boundary, partial WAV/SRT files are deleted, and the timeline is left exactly as it was.",
  },
  {
    q: "Does it need internet?",
    a: "Only the first time, to download the Whisper model weights. After that everything runs fully offline.",
  },
];

function Index() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-50 border-b border-border/60 bg-background/80 backdrop-blur-xl">
        <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <a href="#top" className="flex items-center gap-2.5">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-signal font-display text-sm font-bold text-signal-foreground">
              বা
            </span>
            <span className="font-display text-sm font-semibold tracking-tight">
              Bangla Subtitle Studio
            </span>
          </a>
          <div className="hidden items-center gap-7 text-sm text-muted-foreground md:flex">
            <a className="transition-colors hover:text-foreground" href="#features">
              Features
            </a>
            <a className="transition-colors hover:text-foreground" href="#workflow">
              Workflow
            </a>
            <a className="transition-colors hover:text-foreground" href="#compat">
              Compatibility
            </a>
            <a className="transition-colors hover:text-foreground" href="#faq">
              FAQ
            </a>
          </div>
          <Link
            to="/guide"
            className="rounded-full bg-signal px-4 py-2 text-sm font-semibold text-signal-foreground transition-opacity hover:opacity-90"
          >
            Setup guide
          </Link>
        </nav>
      </header>

      <main id="top">
        {/* Hero */}
        <section className="hero-glow relative overflow-hidden border-b border-border/60">
          <div className="mx-auto grid max-w-6xl gap-14 px-6 py-24 lg:grid-cols-[1.1fr_0.9fr] lg:py-32">
            <div>
              <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/70 px-3 py-1 text-xs font-medium text-muted-foreground">
                <span className="h-1.5 w-1.5 rounded-full bg-signal" />
                Runs offline · DaVinci Resolve 18 – 20
              </span>
              <h1 className="mt-6 font-display text-5xl leading-[1.05] font-extrabold sm:text-6xl">
                Bengali subtitles,
                <br />
                <span className="text-signal">generated inside Resolve.</span>
              </h1>
              <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted-foreground">
                A local desktop plugin that exports your timeline audio, transcribes it
                with faster-whisper <span className="font-mono text-sm">large-v3</span>,
                and places a clean, correctly-wrapped{" "}
                <span className="font-mono text-sm">.srt</span> on a subtitle track — in
                one click, with no cloud service in the loop.
              </p>
              <div className="mt-9 flex flex-wrap items-center gap-3">
                <Link
                  to="/guide"
                  className="rounded-xl bg-signal px-6 py-3 text-sm font-semibold text-signal-foreground shadow-[var(--shadow-glow)] transition-transform hover:-translate-y-0.5"
                >
                  Read the full setup guide
                </Link>
                <a
                  href="#workflow"
                  className="rounded-xl border border-border bg-surface/60 px-6 py-3 text-sm font-semibold text-foreground transition-colors hover:bg-surface-raised"
                >
                  See how it works
                </a>
              </div>
              <dl className="mt-12 grid max-w-lg grid-cols-3 gap-6 border-t border-border pt-7">
                {[
                  ["100%", "On-device"],
                  ["4", "Automated steps"],
                  ["0", "Cloud API keys"],
                ].map(([v, l]) => (
                  <div key={l}>
                    <dt className="font-display text-3xl font-bold text-foreground">{v}</dt>
                    <dd className="mt-1 text-xs tracking-wide text-muted-foreground uppercase">
                      {l}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>

            {/* App mock */}
            <div className="glass-card rounded-2xl p-5">
              <div className="flex items-center gap-2 pb-4">
                <span className="h-3 w-3 rounded-full bg-destructive/80" />
                <span className="h-3 w-3 rounded-full bg-highlight/80" />
                <span className="h-3 w-3 rounded-full bg-signal/80" />
                <span className="ml-3 text-xs text-muted-foreground">
                  Bangla Subtitle Studio
                </span>
              </div>
              <div className="rounded-xl border border-border bg-surface-raised/70 p-4">
                <p className="text-xs tracking-wider text-muted-foreground uppercase">
                  Progress
                </p>
                <div className="mt-3 flex items-center gap-2 text-[11px] text-muted-foreground">
                  {["Export", "Transcribe", "Format", "Place"].map((s, i) => (
                    <span key={s} className="flex items-center gap-1.5">
                      <span
                        className={`h-2 w-2 rounded-full ${i < 2 ? "bg-signal" : "bg-border"}`}
                      />
                      {s}
                    </span>
                  ))}
                </div>
                <div className="mt-4 h-2 overflow-hidden rounded-full bg-border">
                  <div className="h-full w-[62%] rounded-full bg-signal" />
                </div>
                <p className="mt-3 text-xs text-muted-foreground">
                  Transcribing… 62% · large-v3 (cpu/int8)
                </p>
              </div>
              <div className="mt-4 space-y-2 rounded-xl border border-border bg-background/60 p-4 font-mono text-[11px] leading-relaxed text-muted-foreground">
                <p>00:00:04,120 → 00:00:07,480</p>
                <p className="bn text-sm text-foreground">
                  আজকের পর্বে আমরা শিখব কীভাবে
                </p>
                <p className="bn text-sm text-foreground">
                  রিজলভে সাবটাইটেল যোগ করতে হয়।
                </p>
              </div>
              <div className="mt-4 flex justify-end gap-2">
                <span className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground">
                  Cancel
                </span>
                <span className="rounded-lg bg-signal px-3 py-1.5 text-xs font-semibold text-signal-foreground">
                  Generate
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* Features */}
        <section id="features" className="mx-auto max-w-6xl px-6 py-24">
          <p className="text-xs font-semibold tracking-[0.2em] text-signal uppercase">
            Everything included
          </p>
          <h2 className="mt-3 max-w-2xl font-display text-4xl font-bold">
            A complete captioning pipeline, not a script snippet.
          </h2>
          <div className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <article
                key={f.title}
                className="glass-card rounded-2xl p-6 transition-transform hover:-translate-y-1"
              >
                <span className="font-mono text-xs text-signal">{f.kicker}</span>
                <h3 className="mt-3 font-display text-lg font-semibold">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {f.body}
                </p>
              </article>
            ))}
          </div>
        </section>

        {/* Workflow */}
        <section id="workflow" className="border-y border-border/60 bg-surface/40">
          <div className="mx-auto max-w-6xl px-6 py-24">
            <p className="text-xs font-semibold tracking-[0.2em] text-highlight uppercase">
              The workflow
            </p>
            <h2 className="mt-3 font-display text-4xl font-bold">
              Four steps, fully automated.
            </h2>
            <div className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-4">
              {STEPS.map((s) => (
                <div key={s.n} className="rounded-2xl border border-border bg-background/50 p-6">
                  <span className="grid h-9 w-9 place-items-center rounded-lg bg-highlight font-display text-sm font-bold text-highlight-foreground">
                    {s.n}
                  </span>
                  <h3 className="mt-4 font-display text-lg font-semibold">{s.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {s.body}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Cancel safety */}
        <section className="mx-auto grid max-w-6xl gap-10 px-6 py-24 lg:grid-cols-2 lg:items-center">
          <div>
            <p className="text-xs font-semibold tracking-[0.2em] text-signal uppercase">
              Safe interruption
            </p>
            <h2 className="mt-3 font-display text-4xl font-bold">
              Cancel without breaking anything.
            </h2>
            <p className="mt-5 leading-relaxed text-muted-foreground">
              Long jobs need an exit. Cancel is cooperative: the GUI thread only trips a
              shared token, so the window keeps repainting while the worker unwinds at
              its next safe checkpoint.
            </p>
            <ul className="mt-7 space-y-3 text-sm">
              {[
                "Stops the Resolve render job through StopRendering() and clears the queue.",
                "Breaks out of the Whisper decode loop between segments, never mid-write.",
                "Deletes partial WAV and .srt files so nothing corrupt survives.",
                "Writes the final SRT atomically (temp file + rename) before any import.",
                "Closing the window mid-run cancels first, so Resolve is never left rendering.",
              ].map((t) => (
                <li key={t} className="flex gap-3 text-muted-foreground">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-signal" />
                  {t}
                </li>
              ))}
            </ul>
          </div>
          <pre className="glass-card overflow-x-auto rounded-2xl p-6 font-mono text-xs leading-relaxed text-muted-foreground">
{`# cancellation.py — one token, shared by every stage
token = CancelToken()
token.add_hook(project.StopRendering)   # abort the Resolve render

while project.IsRenderingInProgress():
    if token.cancelled:
        abort_render(); break
    token.wait(0.25)                    # interruptible poll

for segment in whisper_segments:        # checkpoint per segment
    token.check("transcription")

_atomic_write(srt_path, srt_text)       # never a truncated .srt`}
          </pre>
        </section>

        {/* Compatibility */}
        <section id="compat" className="border-y border-border/60 bg-surface/40">
          <div className="mx-auto max-w-6xl px-6 py-24">
            <p className="text-xs font-semibold tracking-[0.2em] text-highlight uppercase">
              Compatibility
            </p>
            <h2 className="mt-3 font-display text-4xl font-bold">
              Built for the latest Resolve builds.
            </h2>
            <div className="mt-12 grid gap-5 md:grid-cols-3">
              {[
                {
                  t: "Resolve 18 → 20",
                  b: "Version detection via GetVersion(), subtitle-track append with mediaType 3 on 18.5+, and an ImportIntoTimeline fallback for older builds.",
                },
                {
                  t: "Windows · macOS · Linux",
                  b: "Auto-discovers scripting modules in ProgramData, Program Files, %APPDATA%/Fusion, /Library, ~/Library and /opt/resolve, and sets RESOLVE_SCRIPT_API / _LIB when the installer did not.",
                },
                {
                  t: "Python 3.10+ · PySide6",
                  b: "Runs as its own desktop process next to Resolve, so you are not limited to Resolve's bundled interpreter or its console.",
                },
              ].map((c) => (
                <div key={c.t} className="glass-card rounded-2xl p-6">
                  <h3 className="font-display text-lg font-semibold">{c.t}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{c.b}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="mx-auto max-w-3xl px-6 py-24">
          <h2 className="font-display text-4xl font-bold">Questions, answered.</h2>
          <Accordion type="single" collapsible className="mt-8">
            {FAQ.map((item) => (
              <AccordionItem key={item.q} value={item.q}>
                <AccordionTrigger className="text-left font-display text-base">
                  {item.q}
                </AccordionTrigger>
                <AccordionContent className="text-sm leading-relaxed text-muted-foreground">
                  {item.a}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </section>

        {/* CTA */}
        <section className="mx-auto max-w-6xl px-6 pb-24">
          <div className="glass-card hero-glow rounded-3xl px-8 py-14 text-center">
            <h2 className="font-display text-4xl font-bold">
              Caption your next Bangla edit tonight.
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-muted-foreground">
              Install the requirements, drop the folder next to Resolve, and run{" "}
              <span className="font-mono text-sm text-foreground">python app.py</span>.
              The guide walks through every step.
            </p>
            <Link
              to="/guide"
              className="mt-8 inline-block rounded-xl bg-signal px-7 py-3 text-sm font-semibold text-signal-foreground shadow-[var(--shadow-glow)] transition-transform hover:-translate-y-0.5"
            >
              Open the setup guide
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-border/60">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-6 py-8 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <p>Bangla Subtitle Studio — local Bengali captioning for DaVinci Resolve.</p>
          <p className="font-mono text-xs">faster-whisper · CTranslate2 · PySide6</p>
        </div>
      </footer>
    </div>
  );
}
