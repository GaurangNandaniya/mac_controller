"""
macOS implementation of the Platform Driver (`MacDriver`).
Encapsulates all `osascript`, `pmset`, `screencapture`, `CoreBrightness`, and `BlackHole` logic.
"""

import os
import re
import time
import logging
import subprocess
import cv2
from typing import Dict, Any, Optional, List
from .base import PlatformDriver

logger = logging.getLogger('mac_platform')

# macOS virtual key codes for non-printable keys + modifiers (for pressKey)
KEY_CODES = {
    "esc": 53, "tab": 48, "return": 36, "enter": 36, "delete": 51, "backspace": 51,
    "forwarddelete": 117, "space": 49, "caps": 57,
    "left": 123, "right": 124, "down": 125, "up": 126,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98,
    "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "cmd": 55, "option": 58, "ctrl": 59, "shift": 56,
}

MODIFIER_PHRASES = {
    "cmd": "command down", "option": "option down",
    "ctrl": "control down", "shift": "shift down",
}

_NOW_PLAYING_SCRIPTS = [
    '''
if application "Spotify" is running then
    tell application "Spotify"
        if player state is playing then return "Spotify|" & (name of current track) & "|" & (artist of current track)
    end tell
end if
return ""
''',
    '''
if application "Music" is running then
    tell application "Music"
        if player state is playing then return "Music|" & (name of current track) & "|" & (artist of current track)
    end tell
end if
return ""
''',
]


def _run_osa(script: str) -> str:
    """Run an AppleScript and return trimmed stdout (empty string on failure)."""
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        return r.stdout.strip()
    except Exception:
        return ""


class MacDriver(PlatformDriver):
    """macOS concrete platform implementation."""

    def lock_screen(self) -> None:
        subprocess.run(["pmset", "displaysleepnow"], capture_output=True, check=True)

    def sleep_system(self) -> None:
        subprocess.run(["pmset", "sleepnow"], capture_output=True, check=True)

    def get_battery_percentage(self) -> Optional[int]:
        try:
            output = subprocess.check_output(["pmset", "-g", "batt"], text=True)
            match = re.search(r'(\d+)%', output)
            if match:
                return int(match.group(1))
        except Exception as e:
            logger.error(f"Error getting battery percentage on macOS: {e}")
        return None

    def adjust_display_brightness(self, up: bool) -> None:
        key_code = 144 if up else 145
        subprocess.run(["osascript", "-e", f'tell application "System Events" to Key Code {key_code}'], capture_output=True, check=True)

    def set_display_brightness(self, level: int) -> None:
        # Not supported on macOS: there is no reliable public API to set an absolute
        # display-brightness level (it needs the private CoreDisplay/DisplayServices
        # framework or a third-party CLI). Raise instead of silently doing nothing so
        # a caller that wires this up gets a clear error. Use adjust_display_brightness
        # (the F1/F2 key-code steps) for relative changes, which is what the routes use.
        raise NotImplementedError(
            "Absolute display brightness is not supported on macOS; use adjust_display_brightness()"
        )

    def set_keyboard_brightness(self, level: int) -> None:
        import objc
        level = max(0, min(100, level))
        brightness_value = level / 100.0

        CoreBrightness = objc.loadBundle(
            'CoreBrightness',
            bundle_path='/System/Library/PrivateFrameworks/CoreBrightness.framework',
            module_globals={}
        )
        KBClient = objc.lookUpClass('KeyboardBrightnessClient')
        client = KBClient.alloc().init()
        client.setBrightness_forKeyboard_(brightness_value, 1)
        logger.info(f"macOS keyboard brightness set to {level}%")

    def capture_screen_and_webcam(self, session_path: str) -> None:
        # Ensure directory exists
        os.makedirs(session_path, exist_ok=True)

        # 1. Capture Screen (macOS native command)
        screenshot_path = os.path.join(session_path, "screenshot.png")
        subprocess.run(["screencapture", "-x", screenshot_path], check=True)

        # 2. Capture Webcam
        webcam_path = os.path.join(session_path, "webcam.jpg")
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            raise RuntimeError("Could not access webcam")

        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_BRIGHTNESS, 0.6)
            cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)

            for _ in range(5):
                cap.read()

            ret, frame = False, None
            for _ in range(3):
                ret, frame = cap.read()
                if ret and frame is not None:
                    break
                time.sleep(0.1)

            if not ret or frame is None:
                raise RuntimeError("Failed to capture webcam frame")

            frame = cv2.convertScaleAbs(frame, alpha=1.2, beta=20)
        finally:
            cap.release()

        cv2.imwrite(webcam_path, frame)

        # 3. Lock MacBook
        self.lock_screen()

    def press_special_key(self, key: str, modifiers: List[str]) -> None:
        phrases = [MODIFIER_PHRASES[m] for m in modifiers if m in MODIFIER_PHRASES]
        using = f" using {{{', '.join(phrases)}}}" if phrases else ""

        if key.lower() in KEY_CODES:
            action = f"key code {KEY_CODES[key.lower()]}{using}"
        elif len(key) == 1:
            ch = key.replace("\\", "\\\\").replace('"', '\\"')
            action = f'keystroke "{ch}"{using}'
        else:
            raise ValueError(f"Unknown key: {key}")

        script = f'tell application "System Events" to {action}'
        subprocess.run(["osascript", "-e", script], capture_output=True, check=True)

    def set_volume(self, level: int) -> None:
        level = max(0, min(100, level))
        subprocess.run(["osascript", "-e", f"set volume output volume {level}"], capture_output=True, check=True)

    def toggle_mute(self) -> None:
        subprocess.run(["osascript", "-e", "set volume output muted not (output muted of (get volume settings))"], capture_output=True, check=True)

    def get_media_status(self) -> Dict[str, Any]:
        vol_raw = _run_osa("output volume of (get volume settings)")
        muted_raw = _run_osa("output muted of (get volume settings)")
        volume = int(vol_raw) if vol_raw.lstrip("-").isdigit() else None

        now_playing = {"playing": False, "app": None, "track": None, "artist": None}
        for script in _NOW_PLAYING_SCRIPTS:
            out = _run_osa(script)
            if out:
                parts = out.split("|")
                if len(parts) >= 3:
                    now_playing = {"playing": True, "app": parts[0], "track": parts[1], "artist": parts[2]}
                    break

        return {
            "volume": volume,
            "muted": muted_raw == "true",
            "nowPlaying": now_playing,
        }

    def get_loopback_pyaudio_params(self, pyaudio_instance: Any) -> Dict[str, Any]:
        """Find the BlackHole virtual audio device index on macOS."""
        for i in range(pyaudio_instance.get_device_count()):
            dev_info = pyaudio_instance.get_device_info_by_index(i)
            if "BlackHole" in dev_info.get("name", "") and dev_info.get("maxInputChannels", 0) > 0:
                return {"input_device_index": i}
        return {}
