"""Speaker loopback recorder with trim and export."""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import numpy as np

from capture import LoopbackDevice, LoopbackRecorder, default_loopback_device_index, list_loopback_devices
from audio_util import apply_gain_db, peak_dbfs
from export_audio import SAVE_FILETYPES, export_file
from playback import AudioPlayer
from trim_bar import TrimTimeline


class AudioCaptureApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Audio Capture — Speaker Loopback")
        self.geometry("660x452")
        self.resizable(False, False)

        self._recorder: LoopbackRecorder | None = None
        self._recording = False
        self._samples = np.zeros((0, 2), dtype=np.float32)
        self._raw_samples = np.zeros((0, 2), dtype=np.float32)
        self._gain_db = tk.DoubleVar(value=0.0)
        self._sample_rate = 48000
        self._devices: list[LoopbackDevice] = []
        self._trim_start = tk.DoubleVar(value=0.0)
        self._trim_end = tk.DoubleVar(value=0.0)
        self._duration_sec = 0.0
        self._player = AudioPlayer()
        self._stopping = False

        self._build_ui()
        self._refresh_devices()
        self.bind("<space>", lambda _e: self._toggle_play())
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        pad = {"padx": 16, "pady": 6}

        header = ctk.CTkLabel(
            self,
            text="Records what you hear (WASAPI loopback — not the microphone).",
            wraplength=600,
            justify="left",
        )
        header.pack(anchor="w", **pad)

        dev_row = ctk.CTkFrame(self, fg_color="transparent")
        dev_row.pack(fill="x", **pad)
        dev_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(dev_row, text="Device:").grid(row=0, column=0, sticky="w")
        self._device_combo = ctk.CTkComboBox(dev_row, state="readonly")
        self._device_combo.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ctk.CTkButton(dev_row, text="Refresh", width=96, command=self._refresh_devices).grid(
            row=0, column=2, sticky="e"
        )

        meter_row = ctk.CTkFrame(self, fg_color="transparent")
        meter_row.pack(fill="x", **pad)
        ctk.CTkLabel(meter_row, text="Level:").pack(side="left")
        self._meter = ctk.CTkProgressBar(meter_row, width=400)
        self._meter.pack(side="left", padx=(12, 0))
        self._meter.set(0)
        self._status = ctk.CTkLabel(meter_row, text="Idle")
        self._status.pack(side="left", padx=(12, 0))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", **pad)
        self._record_btn = ctk.CTkButton(
            btn_row, text="● Record", fg_color="#c0392b", hover_color="#e74c3c", command=self._toggle_record
        )
        self._record_btn.pack(side="left")
        ctk.CTkButton(
            btn_row,
            text="Clear",
            width=80,
            fg_color="#34495e",
            hover_color="#4a6278",
            command=self._clear_recording,
        ).pack(side="left", padx=(12, 0))
        self._duration_label = ctk.CTkLabel(btn_row, text="Duration: 0.0 s")
        self._duration_label.pack(side="left", padx=(20, 0))
        self._peak_label = ctk.CTkLabel(btn_row, text="", text_color="gray")
        self._peak_label.pack(side="left", padx=(12, 0))

        gain_row = ctk.CTkFrame(self, fg_color="transparent")
        gain_row.pack(fill="x", **pad)
        ctk.CTkLabel(gain_row, text="Gain (dB):").pack(side="left")
        self._gain_slider = ctk.CTkSlider(
            gain_row,
            from_=-6,
            to=24,
            number_of_steps=60,
            command=self._on_gain_slider,
            width=260,
        )
        self._gain_slider.set(0)
        self._gain_slider.pack(side="left", padx=(8, 8))
        self._gain_value = ctk.CTkLabel(gain_row, text="0 dB")
        self._gain_value.pack(side="left", padx=(0, 12))
        ctk.CTkLabel(
            self,
            text="Use the loopback device that matches your active playback output.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=628,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 2))

        trim_frame = ctk.CTkFrame(self)
        trim_frame.pack(fill="x", padx=16, pady=(8, 4))
        ctk.CTkLabel(trim_frame, text="Trim", font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=12, pady=(6, 2)
        )

        self._trim_bar = TrimTimeline(trim_frame, height=88, on_change=self._on_trim_bar_change)
        self._trim_bar.pack(fill="x", padx=8, pady=2)

        trim_btns = ctk.CTkFrame(trim_frame, fg_color="transparent")
        trim_btns.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkButton(trim_btns, text="Full clip", width=90, command=self._reset_trim).pack(side="left", padx=(0, 8))
        self._play_btn = ctk.CTkButton(
            trim_btns,
            text="Play",
            width=88,
            fg_color="#27ae60",
            hover_color="#2ecc71",
            command=self._toggle_play,
        )
        self._play_btn.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            trim_btns,
            text="Space — play / stop",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(side="left")

        export_row = ctk.CTkFrame(self, fg_color="transparent")
        export_row.pack(fill="x", padx=16, pady=(4, 4))
        ctk.CTkLabel(export_row, text="Save as:").pack(side="left")
        self._format_var = ctk.StringVar(value="WAV (.wav)")
        export_formats = [
            "WAV (.wav)",
            "OGG (.ogg)",
            "OGA (.oga)",
            "FLAC (.flac)",
            "MP3 (.mp3)",
            "AIFF (.aiff)",
            "AU (.au)",
        ]
        self._format_menu = ctk.CTkOptionMenu(
            export_row,
            values=export_formats,
            variable=self._format_var,
            width=200,
        )
        self._format_menu.pack(side="left", padx=(12, 0))
        ctk.CTkButton(export_row, text="Export…", width=120, command=self._export).pack(side="left", padx=(16, 0))
        ctk.CTkLabel(
            export_row,
            text="Jeff Molofee (NeHe) 2026",
            font=ctk.CTkFont(family="Helvetica", size=13),
            text_color="#8AA0A0",
        ).pack(side="right")

    def _on_trim_bar_change(self, start: float, end: float) -> None:
        self._trim_start.set(start)
        self._trim_end.set(end)
        if self._player.is_playing:
            self._player.stop()
            self._set_play_button(False)
        self._trim_bar.set_playhead(None)

    def _set_play_button(self, playing: bool) -> None:
        if playing:
            self._play_btn.configure(text="Stop", fg_color="#7f8c8d", hover_color="#95a5a6")
        else:
            self._play_btn.configure(text="Play", fg_color="#27ae60", hover_color="#2ecc71")

    def _toggle_play(self) -> None:
        if self._player.is_playing:
            self._player.stop()
            self._set_play_button(False)
            return
        if self._samples.size == 0:
            messagebox.showinfo("No audio", "Record something first.")
            return
        start, end = self._trim_bar.get_range()
        if end <= start:
            messagebox.showinfo("Trim", "Widen the selection between S and E.")
            return
        self._set_play_button(True)
        self._status.configure(text="Playing…")

        def on_progress(t: float) -> None:
            self.after(0, lambda sec=t: self._trim_bar.set_playhead(sec))

        def on_done() -> None:
            def _ui() -> None:
                self._set_play_button(False)
                self._trim_bar.set_playhead(None)
                self._status.configure(text="Stopped")

            self.after(0, _ui)

        self._player.play(
            self._samples,
            self._sample_rate,
            start,
            end,
            on_progress=on_progress,
            on_finished=on_done,
        )

    def _refresh_devices(self) -> None:
        self._devices = list_loopback_devices()
        if not self._devices:
            self._device_combo.configure(values=["No loopback device found"])
            self._device_combo.set("No loopback device found")
            return
        names = [d.name for d in self._devices]
        self._device_combo.configure(values=names)
        default_idx = default_loopback_device_index()
        pick = 0
        if default_idx is not None:
            for i, d in enumerate(self._devices):
                if d.index == default_idx:
                    pick = i
                    break
        self._device_combo.set(names[pick])

    def _selected_device_index(self) -> int | None:
        if not self._devices:
            return None
        name = self._device_combo.get()
        for d in self._devices:
            if d.name == name:
                return d.index
        return self._devices[0].index

    def _toggle_record(self) -> None:
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        if self._stopping:
            return
        self._player.stop()
        self._set_play_button(False)
        dev = self._selected_device_index()
        if dev is None:
            messagebox.showerror("Device", "No WASAPI loopback device found. Enable stereo mix or use default output.")
            return
        self._samples = np.zeros((0, 2), dtype=np.float32)
        self._raw_samples = np.zeros((0, 2), dtype=np.float32)
        self._recorder = LoopbackRecorder(dev, on_level=self._set_level)
        self._sample_rate = self._recorder.sample_rate
        self._recorder.start()
        self._recording = True
        self._record_btn.configure(text="■ Stop", fg_color="#7f8c8d", hover_color="#95a5a6")
        self._status.configure(text="Recording…")
        self._tick_duration()

    def _stop_recording(self) -> None:
        if not self._recording or self._stopping:
            return
        self._recording = False
        self._stopping = True
        recorder = self._recorder
        self._recorder = None

        self._record_btn.configure(
            text="● Record",
            fg_color="#c0392b",
            hover_color="#e74c3c",
            state="disabled",
        )
        self._status.configure(text="Stopped", text_color="#e74c3c")
        self._meter.set(0)
        self.update_idletasks()

        def work() -> None:
            raw = np.zeros((0, 2), dtype=np.float32)
            sample_rate = self._sample_rate
            if recorder:
                raw = recorder.stop_and_join()
                sample_rate = recorder.sample_rate

            def on_main() -> None:
                if not self.winfo_exists():
                    return
                self._raw_samples = raw
                self._sample_rate = sample_rate
                self._apply_gain_to_samples()
                self._update_duration_ui()
                self._stopping = False
                self._record_btn.configure(state="normal")
                self._status.configure(text="Stopped", text_color="gray")

            self.after(0, on_main)

        threading.Thread(target=work, daemon=True).start()

    def _on_gain_slider(self, value: float) -> None:
        self._gain_db.set(float(value))
        self._gain_value.configure(text=f"{float(value):+.0f} dB")
        self._apply_gain_to_samples()
        if self._samples.size:
            self._trim_bar.set_audio(self._samples, self._duration_sec, self._sample_rate)
            self._peak_label.configure(text=f"Peak {peak_dbfs(self._samples):.1f} dBFS")

    def _apply_gain_to_samples(self) -> None:
        if self._raw_samples.size == 0:
            self._samples = self._raw_samples
            return
        self._samples = apply_gain_db(self._raw_samples, self._gain_db.get())

    def _set_level(self, peak: float) -> None:
        self.after(0, lambda: self._meter.set(min(1.0, peak * 1.2)))

    def _tick_duration(self) -> None:
        if not self._recording or not self._recorder:
            return
        frames = self._recorder.frames_captured
        self._duration_sec = frames / max(1, self._recorder.sample_rate)
        self._duration_label.configure(text=f"Duration: {self._duration_sec:.2f} s")
        self.after(150, self._tick_duration)

    def _update_duration_ui(self) -> None:
        if self._samples.size == 0:
            self._duration_sec = 0.0
        else:
            self._duration_sec = self._samples.shape[0] / max(1, self._sample_rate)
        self._duration_label.configure(text=f"Duration: {self._duration_sec:.2f} s")
        self._trim_start.set(0.0)
        self._trim_end.set(self._duration_sec)
        self._trim_bar.set_audio(self._samples, self._duration_sec, self._sample_rate)
        if self._samples.size:
            self._peak_label.configure(text=f"Peak {peak_dbfs(self._samples):.1f} dBFS")
        else:
            self._peak_label.configure(text="")

    def _reset_trim(self) -> None:
        self._trim_bar.reset_full()
        start, end = self._trim_bar.get_range()
        self._trim_start.set(start)
        self._trim_end.set(end)

    def _clear_recording(self) -> None:
        if self._recording:
            messagebox.showwarning("Recording", "Stop recording before clearing.")
            return
        if self._raw_samples.size == 0 and self._samples.size == 0:
            return
        self._player.stop()
        self._set_play_button(False)
        self._raw_samples = np.zeros((0, 2), dtype=np.float32)
        self._samples = np.zeros((0, 2), dtype=np.float32)
        self._duration_sec = 0.0
        self._gain_db.set(0.0)
        self._gain_slider.set(0)
        self._gain_value.configure(text="0 dB")
        self._trim_start.set(0.0)
        self._trim_end.set(0.0)
        self._trim_bar.set_playhead(None)
        self._status.configure(text="Idle")
        self._update_duration_ui()

    def _export(self) -> None:
        if self._recording:
            messagebox.showwarning("Recording", "Stop recording before export.")
            return
        if self._samples.size == 0:
            messagebox.showinfo("No audio", "Record something first.")
            return
        fmt_map = {
            "WAV (.wav)": ".wav",
            "OGG (.ogg)": ".ogg",
            "OGA (.oga)": ".oga",
            "FLAC (.flac)": ".flac",
            "MP3 (.mp3)": ".mp3",
            "AIFF (.aiff)": ".aiff",
            "AU (.au)": ".au",
        }
        ext = fmt_map.get(self._format_var.get(), ".wav")
        path = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=SAVE_FILETYPES,
        )
        if not path:
            return
        start, end = self._trim_bar.get_range()
        try:
            export_file(
                Path(path),
                self._samples,
                self._sample_rate,
                ext.lstrip("."),
                start,
                end,
            )
            messagebox.showinfo("Saved", f"Exported to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def _on_close(self) -> None:
        self._player.stop()
        self._recording = False
        if self._recorder:
            self._recorder.stop_and_join()
            self._recorder = None
        self.destroy()


def main() -> None:
    app = AudioCaptureApp()
    app.mainloop()


if __name__ == "__main__":
    main()