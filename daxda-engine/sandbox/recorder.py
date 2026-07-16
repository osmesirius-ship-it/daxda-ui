"""
DAXDA Sandbox — Asciinema v2 Screen Recorder
Captures all terminal output from a sandbox run into a self-contained
.cast file that can be replayed with `asciinema play` or shared at
asciinema.io.

Format spec: https://github.com/asciinema/asciinema/blob/develop/doc/asciicast-v2.md
"""
from __future__ import annotations
import json
import os
import shutil
import time


class CastRecorder:
    """
    Records a DAXDA sandbox session to an asciinema v2 .cast file.

    Usage:
        rec = CastRecorder("run_logs/run_001.cast", title="DAXDA Run 001")
        rec.start()
        rec.write("Hello\\n")
        rec.write("World\\n")
        rec.stop()

    The .cast file can then be played back with:
        asciinema play run_logs/run_001.cast
    """

    def __init__(self, path: str, title: str = "DAXDA Sandbox",
                 width: int = 0, height: int = 50):
        self.path   = path
        self.title  = title
        self.width  = width or min(shutil.get_terminal_size((160, 50)).columns, 160)
        self.height = height
        self._file  = None
        self._start_time: float = 0.0
        self._frame_count: int  = 0

    def start(self):
        """Open the cast file and write the asciinema v2 header."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._file = open(self.path, "w", encoding="utf-8")
        self._start_time = time.time()

        header = {
            "version":   2,
            "width":     self.width,
            "height":    self.height,
            "timestamp": int(self._start_time),
            "title":     self.title,
            "env":       {"TERM": "xterm-256color", "SHELL": "/bin/zsh"},
        }
        self._file.write(json.dumps(header) + "\n")
        self._file.flush()

    def write(self, text: str):
        """
        Write a chunk of terminal output (may contain ANSI codes).
        Timestamps relative to start_time.
        """
        if self._file is None or self._file.closed:
            return
        ts = round(time.time() - self._start_time, 6)
        # asciinema event: [timestamp, "o", data]
        frame = json.dumps([ts, "o", text])
        self._file.write(frame + "\n")
        self._frame_count += 1
        # Flush every 50 frames so partial recordings are valid
        if self._frame_count % 50 == 0:
            self._file.flush()

    def write_lines(self, lines: list[str]):
        """Write a list of already-captured lines (from display.line_buffer)."""
        for line in lines:
            self.write(line)

    def stop(self):
        """Flush and close the cast file."""
        if self._file and not self._file.closed:
            self._file.flush()
            self._file.close()

    @property
    def duration(self) -> float:
        return time.time() - self._start_time if self._start_time else 0.0

    @property
    def frame_count(self) -> int:
        return self._frame_count


class MultiRecorder:
    """
    Wraps multiple CastRecorder instances and a plain-text log.
    Writes all output to both the .cast and a .log file simultaneously.
    """

    def __init__(self, cast_path: str, log_path: str, title: str):
        self.cast   = CastRecorder(cast_path, title=title)
        self.log_path = log_path
        self._log_file = None

    def start(self):
        self.cast.start()
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self._log_file = open(self.log_path, "w", encoding="utf-8")

    def write(self, text: str):
        self.cast.write(text)
        if self._log_file:
            self._log_file.write(text)

    def write_lines(self, lines: list[str]):
        for line in lines:
            self.write(line)

    def stop(self):
        self.cast.stop()
        if self._log_file:
            self._log_file.flush()
            self._log_file.close()
