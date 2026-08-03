"""
app.py
------
Bangla Subtitle Studio — PySide6 desktop front-end for the Resolve pipeline.

Run it OUTSIDE Resolve (its own Python process), with Resolve open:

    python app.py
"""

from __future__ import annotations

import os
import sys
import traceback

from PySide6.QtCore import Qt, QObject, QThread, Signal, QPoint
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import ai_engine
import bn_srt
import pipeline
from cancellation import CancelToken, Cancelled

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = ["Export audio", "Transcribe", "Format SRT", "Place on timeline"]



# --------------------------------------------------------------------------
# Worker
# --------------------------------------------------------------------------
class Worker(QObject):
    progress = Signal(str, int)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal(str)

    def __init__(self, options: dict, token: CancelToken) -> None:
        super().__init__()
        self.options = options
        self.token = token

    def cancel(self) -> None:
        """Thread-safe: sets the flag and fires the Resolve render abort hook."""
        self.token.cancel()

    def run(self) -> None:
        try:
            result = pipeline.run_pipeline(
                model_size=self.options["model"],
                prefer_gpu=self.options["gpu"],
                keep_srt_copy=True,
                output_dir=self.options.get("output_dir") or None,
                max_chars=self.options["max_chars"],
                max_lines=self.options["max_lines"],
                place_on_timeline=self.options["place"],
                progress=lambda m, p: self.progress.emit(m, p),
                cancelled=self.token,
            )
            if getattr(result, "cancelled", False):
                self.cancelled.emit(result.message or "Cancelled.")
            else:
                self.finished.emit(result)
        except Cancelled as stop:
            self.cancelled.emit(str(stop))
        except Exception as exc:  # surfaced in the UI, never silently swallowed
            self.failed.emit(f"{exc}\n\n{traceback.format_exc(limit=3)}")



# --------------------------------------------------------------------------
# Small UI helpers
# --------------------------------------------------------------------------
def card(parent: QWidget | None = None) -> QFrame:
    f = QFrame(parent)
    f.setObjectName("Card")
    shadow = QGraphicsDropShadowEffect(f)
    shadow.setBlurRadius(38)
    shadow.setOffset(0, 12)
    shadow.setColor(QColor(0, 0, 0, 150))
    f.setGraphicsEffect(shadow)
    return f


def divider() -> QFrame:
    d = QFrame()
    d.setObjectName("Divider")
    d.setFrameShape(QFrame.Shape.HLine)
    return d


class StepTracker(QWidget):
    def __init__(self) -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.dots: list[QFrame] = []
        self.labels: list[QLabel] = []
        for i, name in enumerate(STEPS):
            dot = QFrame()
            dot.setObjectName("StepDot")
            lbl = QLabel(name)
            lbl.setObjectName("Muted")
            self.dots.append(dot)
            self.labels.append(lbl)
            row.addWidget(dot)
            row.addWidget(lbl)
            if i < len(STEPS) - 1:
                row.addSpacing(6)
        row.addStretch(1)

    def set_active(self, index: int) -> None:
        for i, dot in enumerate(self.dots):
            dot.setObjectName(
                "StepDotDone" if i < index else "StepDotActive" if i == index else "StepDot"
            )
            dot.style().unpolish(dot)
            dot.style().polish(dot)

    def reset(self) -> None:
        self.set_active(-1)


# --------------------------------------------------------------------------
# Main window
# --------------------------------------------------------------------------
class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Bangla Subtitle Studio")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(620, 640)
        self._drag: QPoint | None = None
        self.thread: QThread | None = None
        self.worker: Worker | None = None
        self.token: CancelToken | None = None


        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)

        shell = QFrame()
        shell.setObjectName("Shell")
        outer.addWidget(shell)

        root = QVBoxLayout(shell)
        root.setContentsMargins(24, 18, 24, 22)
        root.setSpacing(18)

        root.addWidget(self._title_bar())
        root.addWidget(self._hero())
        root.addWidget(self._settings_card())
        root.addWidget(self._progress_card(), 1)
        root.addLayout(self._actions())

    # -- sections ---------------------------------------------------------
    def _title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TitleBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        close = QPushButton()
        close.setObjectName("WinBtnClose")
        close.clicked.connect(self.close)
        mini = QPushButton()
        mini.setObjectName("WinBtnMin")
        mini.clicked.connect(self.showMinimized)
        row.addWidget(close)
        row.addWidget(mini)
        row.addStretch(1)

        title = QLabel("Bangla Subtitle Studio")
        title.setObjectName("AppTitle")
        row.addWidget(title)
        row.addStretch(1)

        sub = QLabel("for DaVinci Resolve Studio")
        sub.setObjectName("AppSubtitle")
        row.addWidget(sub)
        return bar

    def _hero(self) -> QWidget:
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(2, 4, 2, 0)
        col.setSpacing(6)
        h = QLabel("Auto Bengali subtitles, on-device")
        h.setObjectName("Hero")
        h.setWordWrap(True)
        p = QLabel(
            "Exports your active timeline's audio, transcribes it locally with "
            "faster-whisper, and drops a ready-to-use .srt in the Media Pool."
        )
        p.setObjectName("Muted")
        p.setWordWrap(True)
        col.addWidget(h)
        col.addWidget(p)
        return w

    def _settings_card(self) -> QWidget:
        c = card()
        col = QVBoxLayout(c)
        col.setContentsMargins(20, 18, 20, 18)
        col.setSpacing(14)

        head = QLabel("Engine")
        head.setObjectName("CardTitle")
        col.addWidget(head)

        row = QHBoxLayout()
        row.setSpacing(12)
        model_lbl = QLabel("Model")
        model_lbl.setObjectName("Muted")
        self.model_box = QComboBox()
        self.model_box.addItems(["large-v3", "medium", "small"])
        self.model_box.setCurrentText(ai_engine.DEFAULT_MODEL)
        self.model_box.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        row.addWidget(model_lbl)
        row.addWidget(self.model_box, 1)

        self.gpu_check = QCheckBox("Use GPU when available")
        self.gpu_check.setChecked(True)
        row.addWidget(self.gpu_check)
        col.addLayout(row)

        col.addWidget(divider())

        fmt_head = QLabel("Subtitle formatting")
        fmt_head.setObjectName("CardTitle")
        col.addWidget(fmt_head)

        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(12)
        chars_lbl = QLabel("Max characters per line")
        chars_lbl.setObjectName("Muted")
        self.chars_slider = QSlider(Qt.Orientation.Horizontal)
        self.chars_slider.setRange(20, 70)
        self.chars_slider.setValue(bn_srt.DEFAULT_MAX_CHARS)
        self.chars_value = QLabel(str(bn_srt.DEFAULT_MAX_CHARS))
        self.chars_value.setObjectName("Muted")
        self.chars_value.setMinimumWidth(24)
        self.chars_slider.valueChanged.connect(
            lambda v: self.chars_value.setText(str(v))
        )
        fmt_row.addWidget(chars_lbl)
        fmt_row.addWidget(self.chars_slider, 1)
        fmt_row.addWidget(self.chars_value)

        lines_lbl = QLabel("Lines")
        lines_lbl.setObjectName("Muted")
        self.lines_spin = QSpinBox()
        self.lines_spin.setRange(1, 3)
        self.lines_spin.setValue(bn_srt.DEFAULT_MAX_LINES)
        fmt_row.addWidget(lines_lbl)
        fmt_row.addWidget(self.lines_spin)
        col.addLayout(fmt_row)

        self.place_check = QCheckBox(
            "Place subtitles on a subtitle track of the active timeline"
        )
        self.place_check.setChecked(True)
        col.addWidget(self.place_check)

        col.addWidget(divider())

        out_row = QHBoxLayout()
        out_row.setSpacing(12)
        out_lbl = QLabel("Save SRT to")
        out_lbl.setObjectName("Muted")
        self.out_value = QLabel(
            os.path.join(os.path.expanduser("~"), "Documents", "Resolve Bangla Subtitles")
        )
        self.out_value.setObjectName("Muted")
        self.out_value.setWordWrap(True)
        browse = QPushButton("Change")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self._choose_dir)
        out_row.addWidget(out_lbl)
        out_row.addWidget(self.out_value, 1)
        out_row.addWidget(browse)
        col.addLayout(out_row)


        note = QLabel(
            "Language is locked to Bengali (bn). Temporary WAV files are deleted "
            "automatically after each run."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        col.addWidget(note)
        return c

    def _progress_card(self) -> QWidget:
        c = card()
        col = QVBoxLayout(c)
        col.setContentsMargins(20, 18, 20, 18)
        col.setSpacing(12)

        head = QLabel("Progress")
        head.setObjectName("CardTitle")
        col.addWidget(head)

        self.steps = StepTracker()
        self.steps.reset()
        col.addWidget(self.steps)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        col.addWidget(self.bar)

        self.status = QLabel("Idle — open a project and timeline in Resolve.")
        self.status.setObjectName("StatusLabel")
        self.status.setWordWrap(True)
        col.addWidget(self.status)

        self.log = QPlainTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        col.addWidget(self.log, 1)
        return c

    def _actions(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("Ghost")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        self.run_btn = QPushButton("Generate Bengali Subtitles")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self._start)
        row.addStretch(1)
        row.addWidget(self.cancel_btn)
        row.addWidget(self.run_btn)
        return row

    # -- behaviour --------------------------------------------------------
    def _choose_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose SRT folder", self.out_value.text())
        if d:
            self.out_value.setText(d)

    def _append(self, msg: str) -> None:
        self.log.appendPlainText(msg)

    def _set_status(self, msg: str, kind: str = "") -> None:
        self.status.setText(msg)
        self.status.setObjectName(
            {"ok": "StatusOk", "error": "StatusError"}.get(kind, "StatusLabel")
        )
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _start(self) -> None:
        if self.thread is not None:
            return
        self.log.clear()
        self.bar.setValue(0)
        self.steps.set_active(0)
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("Cancel")
        self._set_status("Starting…")

        options = {
            "model": self.model_box.currentText(),
            "gpu": self.gpu_check.isChecked(),
            "output_dir": self.out_value.text(),
            "max_chars": self.chars_slider.value(),
            "max_lines": self.lines_spin.value(),
            "place": self.place_check.isChecked(),
        }

        self.token = CancelToken()
        self.thread = QThread(self)
        self.worker = Worker(options, self.token)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.thread.start()

    def _cancel(self) -> None:
        """Never blocks the GUI thread: just trips the token and waits for the
        worker to unwind at its next safe checkpoint."""
        if not self.worker:
            return
        self.worker.cancel()
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("Cancelling…")
        self._set_status(
            "Cancelling safely — stopping the Resolve render and finishing the "
            "current step. Nothing partial will be written."
        )
        self._append("Cancel requested by user.")

    def _on_progress(self, msg: str, pct: int) -> None:
        if self.token is not None and self.token.cancelled:
            # Suppress stale progress so the UI keeps showing "Cancelling…".
            self._append(f"[{pct:3d}%] {msg}")
            return
        self.bar.setValue(max(0, min(100, pct)))
        self._set_status(msg)
        self._append(f"[{pct:3d}%] {msg}")
        self.steps.set_active(0 if pct < 30 else 1 if pct < 86 else 2 if pct < 90 else 3)

    def _on_cancelled(self, message: str) -> None:
        self.bar.setValue(0)
        self.steps.reset()
        self._set_status(message or "Cancelled — no files were written.")
        self._append(message or "Cancelled.")
        self._teardown()


    def _on_finished(self, result: pipeline.PipelineResult) -> None:
        self.bar.setValue(100)
        self.steps.set_active(len(STEPS))
        tail = (
            "placed on the timeline"
            if result.placed_on_timeline
            else "imported into the Media Pool"
        )
        self._set_status(
            f"Done — {result.segment_count} Bengali cues {tail}.",
            "ok" if result.placed_on_timeline else "",
        )
        if result.message:
            self._append(result.message)
        self._append(f"SRT saved to: {result.srt_path}")
        self._teardown()


    def _on_failed(self, message: str) -> None:
        self._set_status(message.splitlines()[0], "error")
        self._append(message)
        self._teardown()

    def _teardown(self) -> None:
        if self.thread:
            self.thread.quit()
            self.thread.wait(15000)
        self.thread = None
        self.worker = None
        self.token = None
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("Cancel")

    def closeEvent(self, event) -> None:
        """Closing mid-run cancels first so Resolve is never left rendering."""
        if self.worker:
            self.worker.cancel()
            if self.thread:
                self.thread.quit()
                self.thread.wait(15000)
        event.accept()


    # -- frameless dragging ----------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._drag and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event) -> None:
        self._drag = None


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Bangla Subtitle Studio")
    qss_path = os.path.join(HERE, "style.qss")
    if os.path.isfile(qss_path):
        with open(qss_path, "r", encoding="utf-8") as fh:
            app.setStyleSheet(fh.read())
    icon = os.path.join(HERE, "icon.png")
    if os.path.isfile(icon):
        app.setWindowIcon(QIcon(icon))

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
