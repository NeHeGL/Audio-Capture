"""Standard in/out trim bar: one waveform, two handles, slip selection."""
from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk
import numpy as np


MIN_GAP_SEC = 0.02
HANDLE_GRIP_W = 14
HANDLE_HIT = 12
TOP_GRIP_H = 10


def waveform_peaks(samples: np.ndarray, bars: int = 512) -> np.ndarray:
    if samples.size == 0:
        return np.zeros(bars, dtype=np.float32)
    if samples.ndim > 1:
        mono = np.max(np.abs(samples), axis=1)
    else:
        mono = np.abs(samples)
    n = mono.shape[0]
    if n <= bars:
        return mono.astype(np.float32)
    edges = np.linspace(0, n, bars + 1, dtype=int)
    peaks = np.zeros(bars, dtype=np.float32)
    for i in range(bars):
        seg = mono[edges[i] : edges[i + 1]]
        peaks[i] = float(np.max(seg)) if seg.size else 0.0
    return peaks


class TrimTimeline(ctk.CTkFrame):
    """
    Typical A/V trim strip:
    - Full-width waveform
    - Draggable in (left) and out (right) handles; they cannot cross
    - Drag the highlighted region to move the whole selection
  """
    def __init__(
        self,
        master,
        height: int = 100,
        on_change: Callable[[float, float], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self._height = height
        self._on_change = on_change
        self._duration = 0.0
        self._start_sec = 0.0
        self._end_sec = 0.0
        self._peaks = np.zeros(512, dtype=np.float32)
        self._drag: str | None = None
        self._move_anchor: float = 0.0
        self._playhead_sec: float | None = None

        self._canvas = tk.Canvas(
            self,
            height=height,
            highlightthickness=0,
            bg="#1e1e1e",
            cursor="sb_h_double_arrow",
        )
        self._canvas.pack(fill="x", padx=2, pady=2)
        self._canvas.bind("<Configure>", lambda _e: self._redraw())
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)

        self._time_label = ctk.CTkLabel(
            self,
            text="In 0:00.00  ·  Out 0:00.00  ·  0:00.00 selected",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self._time_label.pack(anchor="w", padx=8, pady=(0, 4))

    def set_audio(self, samples: np.ndarray, duration_sec: float, _sample_rate: int) -> None:
        self._duration = max(duration_sec, 0.0)
        self._peaks = waveform_peaks(samples) if samples.size else np.zeros(512, dtype=np.float32)
        self._start_sec = 0.0
        self._end_sec = self._duration
        self._playhead_sec = None
        self._redraw()
        self._emit_labels()

    def set_range(self, start_sec: float, end_sec: float) -> None:
        if self._duration <= 0:
            return
        gap = self._min_gap()
        start_sec = max(0.0, min(start_sec, self._duration - gap))
        end_sec = min(self._duration, max(end_sec, start_sec + gap))
        self._start_sec = start_sec
        self._end_sec = end_sec
        self._redraw()
        self._emit_labels()

    def get_range(self) -> tuple[float, float]:
        return self._start_sec, self._end_sec

    def reset_full(self) -> None:
        self.set_range(0.0, self._duration)

    def set_playhead(self, sec: float | None) -> None:
        self._playhead_sec = sec
        self._redraw()

    def _min_gap(self) -> float:
        if self._duration <= 0:
            return MIN_GAP_SEC
        return min(MIN_GAP_SEC, self._duration / 100)

    def _sec_to_x(self, sec: float) -> float:
        w = max(self._canvas.winfo_width(), 1)
        if self._duration <= 0:
            return 0.0
        return (sec / self._duration) * w

    def _x_to_sec(self, x: float) -> float:
        w = max(self._canvas.winfo_width(), 1)
        if self._duration <= 0:
            return 0.0
        return max(0.0, min(self._duration, (x / w) * self._duration))

    def _format_time(self, sec: float) -> str:
        m = int(sec // 60)
        s = sec % 60
        return f"{m}:{s:05.2f}"

    def _hit_test(self, x: float) -> str | None:
        sx = self._sec_to_x(self._start_sec)
        ex = self._sec_to_x(self._end_sec)
        if abs(x - sx) <= HANDLE_HIT:
            return "in"
        if abs(x - ex) <= HANDLE_HIT:
            return "out"
        if sx < x < ex:
            return "slip"
        return None

    def _on_press(self, event: tk.Event) -> None:
        if self._duration <= 0:
            return
        self._drag = self._hit_test(event.x)
        if self._drag == "slip":
            self._move_anchor = self._x_to_sec(event.x) - self._start_sec
            self._canvas.configure(cursor="fleur")
        elif self._drag in ("in", "out"):
            self._canvas.configure(cursor="sb_h_double_arrow")
        else:
            self._playhead_sec = self._x_to_sec(event.x)
            self._redraw()
        if self._drag:
            self._on_drag(event)

    def _apply_change(self) -> None:
        self._redraw()
        self._emit_labels()
        if self._on_change:
            self._on_change(self._start_sec, self._end_sec)

    def _on_drag(self, event: tk.Event) -> None:
        if not self._drag or self._duration <= 0:
            return
        gap = self._min_gap()
        t = self._x_to_sec(event.x)

        if self._drag == "in":
            self._start_sec = max(0.0, min(t, self._end_sec - gap))
        elif self._drag == "out":
            self._end_sec = min(self._duration, max(t, self._start_sec + gap))
        elif self._drag == "slip":
            length = self._end_sec - self._start_sec
            new_start = t - self._move_anchor
            new_start = max(0.0, min(new_start, self._duration - length))
            self._start_sec = new_start
            self._end_sec = new_start + length

        self._apply_change()

    def _on_release(self, _event: tk.Event) -> None:
        self._drag = None
        self._canvas.configure(cursor="sb_h_double_arrow")

    def _emit_labels(self) -> None:
        sel = max(0.0, self._end_sec - self._start_sec)
        self._time_label.configure(
            text=(
                f"In {self._format_time(self._start_sec)}  ·  "
                f"Out {self._format_time(self._end_sec)}  ·  "
                f"{self._format_time(sel)} selected"
            )
        )

    def _draw_handle(self, c: tk.Canvas, x: float, h: float, color: str) -> None:
        c.create_line(x, 0, x, h, fill=color, width=2)
        gw = HANDLE_GRIP_W
        c.create_rectangle(
            x - gw / 2,
            2,
            x + gw / 2,
            2 + TOP_GRIP_H,
            fill=color,
            outline="#ffffff",
            width=1,
        )

    def _redraw(self) -> None:
        c = self._canvas
        c.delete("all")
        w = max(c.winfo_width(), 1)
        h = max(c.winfo_height(), self._height)
        mid = h / 2
        c.create_rectangle(0, 0, w, h, fill="#1e1e1e", outline="#333333")

        if self._peaks.size and self._duration > 0:
            peaks = self._peaks
            n = len(peaks)
            bar_w = w / n
            scale = (h * 0.44) / max(float(np.max(peaks)), 1e-6)
            for i, pk in enumerate(peaks):
                x0 = i * bar_w
                x1 = x0 + max(bar_w * 0.8, 1)
                ph = pk * scale
                c.create_rectangle(x0, mid - ph, x1, mid + ph, fill="#606060", outline="")

        if self._duration <= 0:
            c.create_text(w / 2, mid, text="Record audio to trim", fill="#888888")
            return

        x_in = self._sec_to_x(self._start_sec)
        x_out = self._sec_to_x(self._end_sec)

        c.create_rectangle(0, 0, x_in, h, fill="#121212", outline="")
        c.create_rectangle(x_out, 0, w, h, fill="#121212", outline="")
        c.create_rectangle(x_in, 0, x_out, h, fill="#2a4a6b", outline="")

        if self._peaks.size:
            peaks = self._peaks
            n = len(peaks)
            bar_w = w / n
            scale = (h * 0.44) / max(float(np.max(peaks)), 1e-6)
            i0 = max(0, int((self._start_sec / self._duration) * n))
            i1 = min(n, int((self._end_sec / self._duration) * n) + 1)
            for i in range(i0, i1):
                pk = peaks[i]
                x0 = i * bar_w
                x1 = x0 + max(bar_w * 0.8, 1)
                ph = pk * scale
                c.create_rectangle(x0, mid - ph, x1, mid + ph, fill="#b8d4f0", outline="")

        self._draw_handle(c, x_in, h, "#5dade2")
        self._draw_handle(c, x_out, h, "#5dade2")

        if self._playhead_sec is not None and 0 <= self._playhead_sec <= self._duration:
            px = self._sec_to_x(self._playhead_sec)
            c.create_line(px, 0, px, h, fill="#e74c3c", width=2)
            c.create_polygon(px, 0, px - 6, 10, px + 6, 10, fill="#e74c3c", outline="")