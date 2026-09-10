from __future__ import annotations

from abc import ABC, abstractmethod


class PlayerBackend(ABC):
    @abstractmethod
    def play(self, url: str, start: float = 0) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def pause(self) -> None: ...

    @abstractmethod
    def resume(self) -> None: ...

    @abstractmethod
    def seek(self, seconds: float) -> None: ...

    @abstractmethod
    def set_volume(self, value: float) -> None: ...

    @abstractmethod
    def get_position(self) -> float: ...

    @abstractmethod
    def get_duration(self) -> float: ...

    @abstractmethod
    def audio_tracks(self) -> list[dict]: ...

    @abstractmethod
    def subtitle_tracks(self) -> list[dict]: ...

    @abstractmethod
    def toggle_fullscreen(self): ...

    @abstractmethod
    def cycle_audio_track(self): ...

    @abstractmethod
    def cycle_subtitle_track(self): ...

