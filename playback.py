"""Play recorded audio through the default output device."""
from __future__ import annotations

import threading
from typing import Callable

import numpy as np
import pyaudiowpatch as pyaudio


class AudioPlayer:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._playing = False

    @property
    def is_playing(self) -> bool:
        return self._playing

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._playing = False

    def play(
        self,
        samples: np.ndarray,
        sample_rate: int,
        start_sec: float,
        end_sec: float,
        on_progress: Callable[[float], None] | None = None,
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        self.stop()
        if samples.size == 0 or end_sec <= start_sec:
            return
        start_i = max(0, int(start_sec * sample_rate))
        end_i = min(samples.shape[0], int(end_sec * sample_rate))
        if end_i <= start_i:
            return
        clip = np.ascontiguousarray(samples[start_i:end_i], dtype=np.float32)
        if clip.ndim == 1:
            clip = clip.reshape(-1, 1)
        channels = clip.shape[1]

        self._stop.clear()
        self._playing = True

        def _run() -> None:
            pa = pyaudio.PyAudio()
            stream = None
            try:
                stream = pa.open(
                    format=pyaudio.paFloat32,
                    channels=channels,
                    rate=sample_rate,
                    output=True,
                )
                chunk_frames = 1024
                interleaved = clip.reshape(-1)
                pos = 0
                total = interleaved.size
                frames_done = 0
                if on_progress:
                    on_progress(start_sec)
                while pos < total and not self._stop.is_set():
                    frame_bytes = chunk_frames * channels
                    end = min(pos + frame_bytes, total)
                    stream.write(interleaved[pos:end].tobytes())
                    frames_this = (end - pos) // channels
                    frames_done += frames_this
                    pos = end
                    if on_progress:
                        on_progress(start_sec + frames_done / sample_rate)
            finally:
                if stream:
                    try:
                        stream.stop_stream()
                        stream.close()
                    except OSError:
                        pass
                pa.terminate()
                self._playing = False
                if on_finished:
                    on_finished()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()