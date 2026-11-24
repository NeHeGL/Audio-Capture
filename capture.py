"""WASAPI loopback capture (playback device / speakers)."""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pyaudiowpatch as pyaudio

from audio_util import downmix_stereo


@dataclass
class LoopbackDevice:
    index: int
    name: str
    default_sample_rate: float
    max_input_channels: int


def list_loopback_devices() -> list[LoopbackDevice]:
    pa = pyaudio.PyAudio()
    try:
        devices: list[LoopbackDevice] = []
        seen: set[int] = set()
        try:
            for info in pa.get_loopback_device_info_generator():
                idx = int(info["index"])
                if idx in seen:
                    continue
                seen.add(idx)
                devices.append(
                    LoopbackDevice(
                        index=idx,
                        name=info["name"],
                        default_sample_rate=float(info["defaultSampleRate"]),
                        max_input_channels=int(info["maxInputChannels"]),
                    )
                )
        except (OSError, AttributeError):
            pass
        if devices:
            return devices
        try:
            wasapi_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        except OSError:
            return []
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info.get("hostApi") != wasapi_info["index"]:
                continue
            if info.get("maxInputChannels", 0) < 1:
                continue
            if "loopback" in info["name"].lower():
                devices.append(
                    LoopbackDevice(
                        index=i,
                        name=info["name"],
                        default_sample_rate=float(info["defaultSampleRate"]),
                        max_input_channels=int(info["maxInputChannels"]),
                    )
                )
        return devices
    finally:
        pa.terminate()


def default_loopback_device_index() -> int | None:
    pa = pyaudio.PyAudio()
    try:
        wasapi_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = pa.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
        for loopback in pa.get_loopback_device_info_generator():
            if default_speakers["name"] in loopback["name"]:
                return int(loopback["index"])
    except (OSError, ValueError, KeyError):
        pass
    finally:
        pa.terminate()
    devices = list_loopback_devices()
    return devices[0].index if devices else None


class LoopbackRecorder:
    def __init__(
        self,
        device_index: int,
        on_level: Callable[[float], None] | None = None,
        block_duration_sec: float = 0.05,
    ) -> None:
        self._device_index = device_index
        self._on_level = on_level
        self._block_duration_sec = block_duration_sec
        self._pa: pyaudio.PyAudio | None = None
        self._stream: pyaudio.Stream | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._chunks: queue.Queue[np.ndarray] = queue.Queue()
        self._frames_captured = 0
        self._sample_rate = 48000
        self._channels = 2

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def channels(self) -> int:
        return self._channels

    @property
    def frames_captured(self) -> int:
        return self._frames_captured

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._frames_captured = 0
        while not self._chunks.empty():
            try:
                self._chunks.get_nowait()
            except queue.Empty:
                break
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop_and_join(self) -> np.ndarray:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        parts: list[np.ndarray] = []
        while not self._chunks.empty():
            try:
                parts.append(self._chunks.get_nowait())
            except queue.Empty:
                break
        if not parts:
            return np.zeros((0, 2), dtype=np.float32)
        return np.concatenate(parts, axis=0)

    def _run(self) -> None:
        pa = pyaudio.PyAudio()
        self._pa = pa
        try:
            info = pa.get_device_info_by_index(self._device_index)
            self._sample_rate = int(info["defaultSampleRate"])
            open_channels = int(info["maxInputChannels"])
            if open_channels < 1:
                open_channels = 2
            self._channels = open_channels
            frames_per_buffer = int(self._sample_rate * self._block_duration_sec)
            # int24/32 paths via float on some drivers are quieter; int16 loopback is full-scale on Windows.
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=open_channels,
                rate=self._sample_rate,
                input=True,
                input_device_index=self._device_index,
                frames_per_buffer=frames_per_buffer,
            )
            self._stream = stream
            while not self._stop.is_set():
                try:
                    data = stream.read(frames_per_buffer, exception_on_overflow=False)
                except OSError:
                    break
                arr = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                arr = downmix_stereo(arr.reshape(-1, open_channels))
                self._frames_captured += arr.shape[0]
                self._chunks.put(arr)
                if self._on_level:
                    peak = float(np.max(np.abs(arr))) if arr.size else 0.0
                    self._on_level(peak)
        finally:
            if self._stream:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                except OSError:
                    pass
                self._stream = None
            pa.terminate()
            self._pa = None