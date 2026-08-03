import { createFileRoute, Link } from "@tanstack/react-router";

export const Route = createFileRoute("/guide")({
  head: () => ({
    meta: [
      { title: "Setup Guide — Bangla Subtitle Studio for DaVinci Resolve" },
      {
        name: "description",
        content:
          "Step-by-step install and usage guide: Python requirements, enabling Resolve external scripting, running the app, tuning subtitle formatting and troubleshooting.",
      },
      { property: "og:title", content: "Setup Guide — Bangla Subtitle Studio" },
      {
        property: "og:description",
        content:
          "Install, configure and run the offline Bengali subtitle plugin for DaVinci Resolve 18–20.",
      },
      { property: "og:type", content: "article" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Guide,
});

function Code({ children }: { children: string }) {
  return (
    <pre className="mt-4 overflow-x-auto rounded-xl border border-border bg-surface-raised/60 p-4 font-mono text-xs leading-relaxed text-foreground">
      {children}
    </pre>
  );
}

const SECTIONS = [
  { id: "requirements", label: "1. Requirements" },
  { id: "install", label: "2. Install" },
  { id: "scripting", label: "3. Enable scripting" },
  { id: "run", label: "4. Run the app" },
  { id: "use", label: "5. Generate subtitles" },
  { id: "cancel", label: "6. Cancelling" },
  { id: "style", label: "7. Style captions" },
  { id: "trouble", label: "8. Troubleshooting" },
];

function Guide() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-50 border-b border-border/60 bg-background/80 backdrop-blur-xl">
        <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link to="/" className="flex items-center gap-2.5">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-signal font-display text-sm font-bold text-signal-foreground">
              বা
            </span>
            <span className="font-display text-sm font-semibold">
              Bangla Subtitle Studio
            </span>
          </Link>
          <Link
            to="/"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            ← Back to overview
          </Link>
        </nav>
      </header>

      <main className="mx-auto grid max-w-6xl gap-12 px-6 py-16 lg:grid-cols-[220px_1fr]">
        <aside className="h-max lg:sticky lg:top-24">
          <p className="text-xs font-semibold tracking-[0.2em] text-muted-foreground uppercase">
            On this page
          </p>
          <ul className="mt-4 space-y-2 text-sm">
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <a
                  href={`#${s.id}`}
                  className="text-muted-foreground transition-colors hover:text-signal"
                >
                  {s.label}
                </a>
              </li>
            ))}
          </ul>
        </aside>

        <article className="max-w-3xl">
          <h1 className="font-display text-4xl font-bold">Full setup &amp; usage guide</h1>
          <p className="mt-4 leading-relaxed text-muted-foreground">
            From a clean machine to Bengali subtitles on your timeline in about fifteen
            minutes, most of which is the first model download.
          </p>

          <section id="requirements" className="mt-14">
            <h2 className="font-display text-2xl font-semibold">1. Requirements</h2>
            <ul className="mt-4 space-y-2 text-sm text-muted-foreground">
              <li>• DaVinci Resolve <strong className="text-foreground">Studio</strong> 18, 18.5, 19, 20 or 21 (external scripting is a Studio feature).</li>
              <li>• Python 3.10 – 3.12, 64-bit.</li>
              <li>• 8 GB RAM minimum for <span className="font-mono">large-v3</span> on CPU (16 GB comfortable); a CUDA GPU with 6 GB VRAM is optional but much faster.</li>
              <li>• ~3 GB free disk for the model cache, plus temp space for the exported WAV.</li>
            </ul>
          </section>

          <section id="install" className="mt-14">
            <h2 className="font-display text-2xl font-semibold">2. Install the plugin</h2>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
              Put the <span className="font-mono">resolve_bangla_subtitles</span> folder
              anywhere you like — it runs as its own process. If you also want it listed
              in Resolve's <em>Workspace → Scripts</em> menu, copy it into the Utility
              scripts folder:
            </p>
            <Code>{`Windows  %PROGRAMDATA%\\Blackmagic Design\\DaVinci Resolve\\Fusion\\Scripts\\Utility\\
macOS    /Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/
Linux    /opt/resolve/Fusion/Scripts/Utility/`}</Code>
            <p className="mt-5 text-sm leading-relaxed text-muted-foreground">
              Then create a virtual environment and install the dependencies:
            </p>
            <Code>{`cd resolve_bangla_subtitles
python -m venv .venv
# Windows:  .venv\\Scripts\\activate
source .venv/bin/activate
pip install -r requirements.txt`}</Code>
          </section>

          <section id="scripting" className="mt-14">
            <h2 className="font-display text-2xl font-semibold">3. Enable external scripting</h2>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
              In Resolve open <strong className="text-foreground">Preferences → System → General</strong> and set{" "}
              <em>External scripting using</em> to <strong className="text-foreground">Local</strong>. Restart Resolve.
              The plugin sets <span className="font-mono">RESOLVE_SCRIPT_API</span> and{" "}
              <span className="font-mono">RESOLVE_SCRIPT_LIB</span> for you when the
              installer did not, so no manual environment variables are usually needed.
            </p>
          </section>

          <section id="run" className="mt-14">
            <h2 className="font-display text-2xl font-semibold">4. Run the app</h2>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
              Open Resolve first, load the project and the timeline you want to caption,
              then launch the window:
            </p>
            <Code>{`python app.py

# headless / CI alternative:
python pipeline.py`}</Code>
          </section>

          <section id="use" className="mt-14">
            <h2 className="font-display text-2xl font-semibold">5. Generate subtitles</h2>
            <ol className="mt-4 space-y-3 text-sm text-muted-foreground">
              <li><strong className="text-foreground">1.</strong> Pick a model — <span className="font-mono">large-v3</span> for final work, <span className="font-mono">medium</span>/<span className="font-mono">small</span> for fast drafts. The line under the picker tells you whether it is already cached or still needs its one-time download.</li>
              <li><strong className="text-foreground">2.</strong> Leave “Use GPU when available” on; it silently falls back to CPU INT8.</li>
              <li><strong className="text-foreground">3.</strong> Keep “Trim leading and trailing silence” on so cues start on the actual voice; lower the threshold toward -70 dB for noisy rooms, raise it toward -25 dB for very quiet recordings.</li>
              <li><strong className="text-foreground">4.</strong> Set max characters per line (42 is a good default) and lines per caption (2).</li>
              <li><strong className="text-foreground">5.</strong> Keep “Place subtitles on a subtitle track” checked for automatic placement.</li>
              <li><strong className="text-foreground">6.</strong> Choose where the permanent <span className="font-mono">.srt</span> is saved — Resolve links to that file, so keep it around.</li>
              <li><strong className="text-foreground">7.</strong> Hit <strong className="text-foreground">Generate Bengali Subtitles</strong> and watch the four step dots. The log reports what the timing check corrected before the import.</li>
            </ol>
            <p className="mt-5 text-sm leading-relaxed text-muted-foreground">
              The first run downloads the model weights to{" "}
              <span className="font-mono">~/.cache/resolve_bangla_subtitles/models</span>{" "}
              (override with <span className="font-mono">RBS_MODEL_CACHE</span>) with a
              live progress bar. Every later run reuses that cache and is fully offline;
              “Clear cache” frees the space again.
            </p>
          </section>

          <section id="cancel" className="mt-14">
            <h2 className="font-display text-2xl font-semibold">6. Cancelling a run</h2>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
              Press <strong className="text-foreground">Cancel</strong> at any point. The
              button switches to “Cancelling…”, the Resolve render is stopped, the
              Whisper decoder exits at the next segment boundary and every partial file
              is deleted. The window stays responsive throughout, and your timeline is
              left untouched. Closing the window mid-run does the same thing before
              exiting.
            </p>
          </section>

          <section id="style" className="mt-14">
            <h2 className="font-display text-2xl font-semibold">7. Style the captions</h2>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
              Once the SRT is on a subtitle track, select the track and use the Inspector
              to set font, size, colour and position — a Bengali-capable font such as
              Noto Sans Bengali or SolaimanLipi renders conjuncts correctly. Changing the
              track style applies to every caption at once.
            </p>
          </section>

          <section id="trouble" className="mt-14">
            <h2 className="font-display text-2xl font-semibold">8. Troubleshooting</h2>
            <div className="mt-4 space-y-4 text-sm text-muted-foreground">
              <p>
                <strong className="text-foreground">“Could not import DaVinciResolveScript”</strong> — Resolve
                is not running, external scripting is not set to Local, or you are on the
                free (non-Studio) build.
              </p>
              <p>
                <strong className="text-foreground">“Resolve refused to queue the render job”</strong> — the
                timeline has no audio, or the Deliver page has an invalid custom preset.
                Reset the Deliver preset and retry.
              </p>
              <p>
                <strong className="text-foreground">Placement refused</strong> — older builds may reject the
                automatic edit; the SRT is still in the Media Pool, drag it onto a
                subtitle track.
              </p>
              <p>
                <strong className="text-foreground">Out of memory</strong> — switch to{" "}
                <span className="font-mono">medium</span> or disable GPU so the CPU INT8
                path is used.
              </p>
            </div>
          </section>

          <div className="mt-16 rounded-2xl border border-border bg-surface/50 p-6">
            <p className="text-sm text-muted-foreground">
              Everything on this page reflects the shipped code in{" "}
              <span className="font-mono text-foreground">resolve_bangla_subtitles/</span> —
              app.py, pipeline.py, resolve_api.py, ai_engine.py, bn_srt.py and
              cancellation.py.
            </p>
          </div>
        </article>
      </main>

      <footer className="border-t border-border/60">
        <div className="mx-auto max-w-6xl px-6 py-8 text-sm text-muted-foreground">
          Bangla Subtitle Studio — local Bengali captioning for DaVinci Resolve.
        </div>
      </footer>
    </div>
  );
}
