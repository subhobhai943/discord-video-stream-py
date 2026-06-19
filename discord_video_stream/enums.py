"""Public enumerations for the library API."""

from enum import Enum, auto


class Codec(str, Enum):
    """Video codec to use for streaming."""
    H264 = "h264"
    VP8 = "vp8"


class StreamType(str, Enum):
    """How to present the stream in Discord."""
    GO_LIVE = "go_live"
    WEBCAM = "webcam"


class Resolution(str, Enum):
    """Common resolution presets."""
    R480P = "480p"
    R720P = "720p"
    R1080P = "1080p"
    SOURCE = "source"

    def dimensions(self) -> tuple[int, int]:
        """Return (width, height) for the preset."""
        mapping = {
            Resolution.R480P: (854, 480),
            Resolution.R720P: (1280, 720),
            Resolution.R1080P: (1920, 1080),
            Resolution.SOURCE: (0, 0),  # 0 = pass-through in FFmpeg
        }
        return mapping[self]
