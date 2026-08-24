"""Friendly Video Maker errors (no traceback in normal UI)."""

from __future__ import annotations


class VideoMakerError(Exception):
    """User-facing video generation failure."""

    def __init__(self, message: str, *, technical: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.technical = technical or message


class MediaValidationError(VideoMakerError):
    pass


class MissingMediaError(VideoMakerError):
    pass


class RenderCancelled(VideoMakerError):
    def __init__(self) -> None:
        super().__init__("Video rendering was cancelled.")
