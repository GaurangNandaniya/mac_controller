"""
Windows implementation of the Platform Driver (`WinDriver`).
Encapsulates `user32`, `pycaw`, `winsdk`, `screen_brightness_control`, and `WASAPI loopback`.
"""

import os
import time
import logging
import asyncio
import ctypes
import cv2
import mss
import psutil
from typing import Dict, Any, Optional, List
from .base import PlatformDriver

logger = logging.getLogger('win_platform')


class WinDriver(PlatformDriver):
    """Windows concrete platform implementation."""

    def lock_screen(self) -> None:
        try:
            ctypes.windll.user32.LockWorkStation()
            logger.info("Windows workstation locked")
        except Exception as e:
            logger.error(f"Error locking screen on Windows: {e}")

    def sleep_system(self) -> None:
        try:
            os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            logger.info("Windows system sleep initiated")
        except Exception as e:
            logger.error(f"Error putting Windows to sleep: {e}")

    def get_battery_percentage(self) -> Optional[int]:
        try:
            battery = psutil.sensors_battery()
            if battery is not None:
                return int(battery.percent)
        except Exception as e:
            logger.error(f"Error reading battery percentage on Windows: {e}")
        return None

    def adjust_display_brightness(self, up: bool) -> None:
        try:
            import screen_brightness_control as sbc
            current = sbc.get_brightness()
            if isinstance(current, list) and len(current) > 0:
                curr_val = current[0]
            elif isinstance(current, int):
                curr_val = current
            else:
                curr_val = 50
            new_val = max(0, min(100, curr_val + (10 if up else -10)))
            sbc.set_brightness(new_val)
            logger.info(f"Windows display brightness adjusted to {new_val}%")
        except Exception as e:
            logger.error(f"Error adjusting display brightness on Windows: {e}")

    def set_display_brightness(self, level: int) -> None:
        try:
            import screen_brightness_control as sbc
            level = max(0, min(100, level))
            sbc.set_brightness(level)
            logger.info(f"Windows display brightness set to {level}%")
        except Exception as e:
            logger.error(f"Error setting display brightness on Windows: {e}")

    def set_keyboard_brightness(self, level: int) -> None:
        # Windows desktop/laptop hardware backlighting is vendor-specific.
        logger.warning(f"Keyboard backlight setting ({level}%) is not supported natively via OS APIs on Windows desktop hardware.")

    def capture_screen_and_webcam(self, session_path: str) -> None:
        os.makedirs(session_path, exist_ok=True)

        # 1. Capture Screen via mss
        screenshot_path = os.path.join(session_path, "screenshot.png")
        with mss.mss() as sct:
            sct.shot(mon=1, output=screenshot_path)

        # 2. Capture Webcam via cv2
        webcam_path = os.path.join(session_path, "webcam.jpg")
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            raise RuntimeError("Could not access webcam on Windows")

        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            for _ in range(5):
                cap.read()
            ret, frame = False, None
            for _ in range(3):
                ret, frame = cap.read()
                if ret and frame is not None:
                    break
                time.sleep(0.1)
            if not ret or frame is None:
                raise RuntimeError("Failed to capture webcam frame on Windows")
            frame = cv2.convertScaleAbs(frame, alpha=1.2, beta=20)
        finally:
            cap.release()

        cv2.imwrite(webcam_path, frame)

        # 3. Lock Workstation
        self.lock_screen()

    def press_special_key(self, key: str, modifiers: List[str]) -> None:
        from pynput import keyboard
        kb = keyboard.Controller()
        mod_map = {
            "cmd": keyboard.Key.cmd,
            "option": keyboard.Key.alt,
            "ctrl": keyboard.Key.ctrl,
            "shift": keyboard.Key.shift,
        }
        active_mods = [mod_map[m.lower()] for m in modifiers if m.lower() in mod_map]

        for mod in active_mods:
            kb.press(mod)

        try:
            if hasattr(keyboard.Key, key.lower()):
                kb.press(getattr(keyboard.Key, key.lower()))
                kb.release(getattr(keyboard.Key, key.lower()))
            elif len(key) == 1:
                kb.press(key)
                kb.release(key)
            else:
                raise ValueError(f"Unknown key: {key}")
        finally:
            for mod in reversed(active_mods):
                kb.release(mod)

    def launch_app(self, name: str) -> None:
        # Windows equivalent of Spotlight: tap the Win key ALONE to open Start
        # (Win+Space switches keyboard layout, so it must be pressed on its own),
        # type the app name, let search resolve, then Enter to launch the top hit.
        from pynput import keyboard
        kb = keyboard.Controller()
        kb.press(keyboard.Key.cmd)   # Win key
        kb.release(keyboard.Key.cmd)
        time.sleep(0.5)              # let Start open and take focus
        kb.type(name)
        time.sleep(0.8)              # let search resolve the top result
        kb.press(keyboard.Key.enter)
        kb.release(keyboard.Key.enter)

    def _get_endpoint_volume(self):
        """Return the IAudioEndpointVolume COM interface for the default speakers.
        COM must already be initialized on the calling thread (see _with_com)."""
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))

    @staticmethod
    def _com_scope():
        """Initialize COM on the current thread and return a cleanup callable.

        Flask serves each request on a pooled worker thread, and pycaw's COM
        calls need CoInitialize on that thread or they fail intermittently with
        'CoInitialize has not been called'. CoInitialize is refcounted, so
        pairing it with CoUninitialize is safe even if COM was already up.
        """
        import comtypes
        comtypes.CoInitialize()
        return comtypes.CoUninitialize

    def set_volume(self, level: int) -> None:
        # No try/except that swallows: let failures propagate so the endpoint
        # returns 500 instead of a misleading "success" while nothing changed.
        cleanup = self._com_scope()
        try:
            level = max(0, min(100, level))
            self._get_endpoint_volume().SetMasterVolumeLevelScalar(level / 100.0, None)
            logger.info(f"Windows master volume set to {level}%")
        finally:
            cleanup()

    def toggle_mute(self) -> None:
        cleanup = self._com_scope()
        try:
            volume = self._get_endpoint_volume()
            new_mute = not volume.GetMute()
            volume.SetMute(new_mute, None)
            logger.info(f"Windows mute toggled to {new_mute}")
        finally:
            cleanup()

    def _get_winsdk_now_playing_sync(self) -> Dict[str, Any]:
        """Fetch media transport controls info via asyncio on Windows."""
        try:
            from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
            async def _fetch():
                manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
                session = manager.get_current_session()
                if not session:
                    return {"playing": False, "app": None, "track": None, "artist": None}
                props = await session.try_get_media_properties_async()
                info = session.get_playback_info()
                is_playing = info and info.playback_status == 4  # 4 = Playing
                return {
                    "playing": is_playing,
                    "app": session.source_app_user_model_id,
                    "track": props.title if props else None,
                    "artist": props.artist if props else None,
                }
            return asyncio.run(_fetch())
        except Exception as e:
            logger.debug(f"Could not get Windows media properties: {e}")
            return {"playing": False, "app": None, "track": None, "artist": None}

    def get_media_status(self) -> Dict[str, Any]:
        vol_int = None
        muted = False
        cleanup = self._com_scope()
        try:
            volume = self._get_endpoint_volume()
            vol_int = int(round(volume.GetMasterVolumeLevelScalar() * 100))
            muted = bool(volume.GetMute())
        except Exception as e:
            # Status is a poll, not a command — degrade gracefully (volume=None).
            logger.debug(f"Could not query pycaw volume: {e}")
        finally:
            cleanup()

        # Kept outside the COM scope: WinRT (winsdk) manages its own apartment init.
        now_playing = self._get_winsdk_now_playing_sync()
        return {
            "volume": vol_int,
            "muted": muted,
            "nowPlaying": now_playing,
        }

    def get_loopback_pyaudio_params(self, pyaudio_instance: Any) -> Dict[str, Any]:
        """Find default output device for WASAPI loopback capture on Windows."""
        try:
            import pyaudio
            wasapi_info = pyaudio_instance.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = pyaudio_instance.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            return {
                "input_device_index": default_speakers["index"],
                "as_loopback": True,
            }
        except Exception as e:
            logger.warning(f"Could not get WASAPI loopback params on Windows: {e}")
            return {}
