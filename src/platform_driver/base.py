"""
Abstract Base Class defining the Platform Driver contract (`PlatformDriver`).
All OS-specific drivers (`MacDriver`, `WinDriver`) must implement this interface.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List


class PlatformDriver(ABC):
    """Abstract contract for OS-specific system and media operations."""

    # --- System Operations ---
    @abstractmethod
    def lock_screen(self) -> None:
        """Lock the workstation / put displays to sleep."""
        pass

    @abstractmethod
    def sleep_system(self) -> None:
        """Put the host machine into system sleep/suspend."""
        pass

    @abstractmethod
    def get_battery_percentage(self) -> Optional[int]:
        """Return the current battery percentage (0-100), or None if unavailable/desktop."""
        pass

    @abstractmethod
    def adjust_display_brightness(self, up: bool) -> None:
        """Step primary display brightness up (`up=True`) or down (`up=False`)."""
        pass

    @abstractmethod
    def set_display_brightness(self, level: int) -> None:
        """Set primary display brightness percentage (0-100)."""
        pass

    @abstractmethod
    def set_keyboard_brightness(self, level: int) -> None:
        """Set laptop keyboard backlight brightness percentage (0-100)."""
        pass

    @abstractmethod
    def capture_screen_and_webcam(self, session_path: str) -> None:
        """Capture screenshot and webcam image into the specified directory (`screenshot.png` and `webcam.jpg`), then lock screen."""
        pass

    @abstractmethod
    def press_special_key(self, key: str, modifiers: List[str]) -> None:
        """Press a key with optional modifier keys (`cmd`, `option`, `ctrl`, `shift`)."""
        pass

    # --- Media Operations ---
    @abstractmethod
    def set_volume(self, level: int) -> None:
        """Set system master output volume percentage (0-100)."""
        pass

    @abstractmethod
    def toggle_mute(self) -> None:
        """Toggle system master output mute state."""
        pass

    @abstractmethod
    def get_media_status(self) -> Dict[str, Any]:
        """Return dict with keys: 'volume' (int|None), 'muted' (bool), and 'nowPlaying' (dict)."""
        pass

    # --- Audio Streaming Operations ---
    @abstractmethod
    def get_loopback_pyaudio_params(self, pyaudio_instance: Any) -> Dict[str, Any]:
        """Return kwargs dictionary for `p.open(...)` to capture system output audio (e.g. BlackHole device index on Mac or WASAPI loopback on Win)."""
        pass
