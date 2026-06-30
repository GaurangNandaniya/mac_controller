from flask import Blueprint, jsonify, request, send_file
import os
import re
import shutil
from ..utils import setup_logger
import cv2
import subprocess
import time
from datetime import datetime
from src.utils.auth_manager import auth_manager
from src.utils.keyboardMouseController import lock_keyboard, unlock_keyboard, lock_mouse, unlock_mouse
from pynput.keyboard import Key, Controller
from pynput.mouse import Button, Controller as MouseController
import mss

logger = setup_logger()

# Shared keyboard controller for remote typing (/system/keyboardType)
_keyboard = Controller()
# Shared mouse controller for tap-to-click on the screen stream (/system/mouse-click)
_mouse = MouseController()

# Named special keys the client can send via {"key": "..."}
SPECIAL_KEYS = {
    "enter": Key.enter, "return": Key.enter,
    "backspace": Key.backspace, "delete": Key.delete,
    "tab": Key.tab, "escape": Key.esc, "esc": Key.esc, "space": Key.space,
    "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
}

# macOS virtual key codes for non-printable keys + modifiers (for /system/pressKey)
KEY_CODES = {
    "esc": 53, "tab": 48, "return": 36, "enter": 36, "delete": 51, "backspace": 51,
    "forwarddelete": 117, "space": 49, "caps": 57,
    "left": 123, "right": 124, "down": 125, "up": 126,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98,
    "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "cmd": 55, "option": 58, "ctrl": 59, "shift": 56,
}

# Modifier name -> AppleScript phrase
MODIFIER_PHRASES = {
    "cmd": "command down", "option": "option down",
    "ctrl": "control down", "shift": "shift down",
}


system_bp = Blueprint('system', __name__)
system_bp.before_request(auth_manager.auth_middleware())

@system_bp.route('/lock', methods=['POST'])
def lock_screen():
    try:
        subprocess.run(["pmset", "displaysleepnow"], capture_output=True)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@system_bp.route('/brightness-up', methods=['POST'])
def brightness_up():
    try:
        subprocess.run(["osascript", "-e", 'tell application "System Events" to Key Code 144'], capture_output=True)  
        logger.info("Brightness up successful")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error in brightness up: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@system_bp.route('/brightness-down', methods=['POST'])
def brightness_down():
    try:
        subprocess.run(["osascript", "-e", 'tell application "System Events" to Key Code 145'], capture_output=True) 
        logger.info("Brightness down successful")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error in brightness down: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@system_bp.route('/sleep', methods=['POST'])
def sleep_mac():
    try:
        subprocess.run(["pmset", "sleepnow"], capture_output=True)
        logger.info("System sleep successful")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error in system sleep: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@system_bp.route('/battery', methods=['POST'])
def get_battery():
    try:
        output = subprocess.check_output(["pmset", "-g", "batt"], text=True)
        match = re.search(r'(\d+)%', output)
        if match:
            return jsonify({"status": "success", "percentage": int(match.group(1))})
        else:
            return jsonify({"status": "error", "error": "Battery info not found"}), 500
    except Exception as e:
        logger.error(f"Error getting battery percentage: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@system_bp.route('/keyboard-light-set/<int:level>', methods=['POST'])
def set_keyboard_light(level):
    try:
        import objc
        # Ensure level is between 0 and 100
        level = max(0, min(100, level))
        brightness_value = level / 100.0

        # Use CoreBrightness private framework (works on Apple Silicon Macs)
        CoreBrightness = objc.loadBundle(
            'CoreBrightness',
            bundle_path='/System/Library/PrivateFrameworks/CoreBrightness.framework',
            module_globals={}
        )
        KBClient = objc.lookUpClass('KeyboardBrightnessClient')
        client = KBClient.alloc().init()
        client.setBrightness_forKeyboard_(brightness_value, 1)

        logger.info(f"Keyboard brightness set to {level}% successful")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error setting keyboard brightness to {level}%: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500
    
@system_bp.route('/capture-and-lock', methods=['POST'])
def capture_and_lock():
    try:
         # Generate timestamp once for consistency
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        # Get save path from request or use default
        base_path = os.path.expanduser("~/Desktop/intruders")
        session_path = os.path.join(base_path, f"session_{timestamp}")

        # Ensure directory exists
        os.makedirs(session_path, exist_ok=True)
        
        # 1. Capture Screen (macOS native command)
        screenshot_path = os.path.join(session_path, "screenshot.png")
        subprocess.run(
            ["screencapture", "-x", screenshot_path],  # -x = disable sound
            check=True
        )
        
        # 2. Capture Webcam
        webcam_path = os.path.join(session_path, "webcam.jpg")
        cap = cv2.VideoCapture(0)  # 0 = default camera

        if not cap.isOpened():
            raise RuntimeError("Could not access webcam")

        try:
            # Set camera properties for better quality
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_BRIGHTNESS, 0.6)  # Adjust brightness (0-1)
            cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)      # Enable autofocus
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)  # Enable auto-exposure

            # Warm-up the camera sensor
            for _ in range(5):
                cap.read()

            # Capture frame with retries
            ret, frame = False, None
            for _ in range(3):  # Try 3 times to get a good frame
                ret, frame = cap.read()
                if ret and frame is not None:
                    break
                time.sleep(0.1)

            if not ret or frame is None:
                raise RuntimeError("Failed to capture webcam frame")

            # Adjust image properties in software
            frame = cv2.convertScaleAbs(frame, alpha=1.2, beta=20)  # Increase contrast and brightness

        finally:
            cap.release()  # Always release camera

        cv2.imwrite(webcam_path, frame)

        # 3. Lock MacBook (same as before)
        subprocess.run(["pmset", "displaysleepnow"], check=True)

        logger.info("Capture and lock successful")
        return jsonify({"status": "success"})

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500
    

@system_bp.route('/keyboard-lock', methods=['POST'])
def keyboard_lock():
    lock_keyboard()
    return jsonify({"status": "success", "message": "keyboard locked"})

@system_bp.route('/keyboard-unlock', methods=['POST'])
def keyboard_unlock():
    unlock_keyboard()
    return  jsonify({"status": "success", "message": "keyboard unlocked"})

@system_bp.route('/mouse-lock', methods=['POST'])
def mouse_lock():
    lock_mouse()
    return jsonify({"status": "success", "message": "mouse locked"})

@system_bp.route('/mouse-unlock', methods=['POST'])
def mouse_unlock():
    unlock_mouse()
    return jsonify({"status": "success", "message": "mouse unlocked"})

@system_bp.route('/keyboardType', methods=['POST'])
def keyboard_type():
    """Type text, or press a named special key, at the Mac's current keyboard focus.

    Body: {"text": "hello"}  OR  {"key": "enter"|"backspace"|"tab"|...}
    Typed text lands wherever the Mac's focus is.
    """
    try:
        data = request.get_json(silent=True) or {}
        key = data.get("key")
        text = data.get("text")

        if key:
            mapped = SPECIAL_KEYS.get(str(key).lower())
            if mapped is None:
                return jsonify({"status": "error", "error": f"Unknown key: {key}"}), 400
            _keyboard.press(mapped)
            _keyboard.release(mapped)
            logger.info(f"Remote keyboard key pressed: {key}")
        elif text is not None:
            _keyboard.type(str(text))
            logger.info(f"Remote keyboard typed {len(str(text))} chars")
        else:
            return jsonify({"status": "error", "error": "Provide 'text' or 'key'"}), 400

        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error in keyboardType: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

_INTRUDERS_BASE = os.path.realpath(os.path.expanduser("~/Desktop/intruders"))


def _intruder_path(*parts):
    """Resolve a path inside the intruders dir, or None if it escapes it."""
    target = os.path.realpath(os.path.join(_INTRUDERS_BASE, *parts))
    if target == _INTRUDERS_BASE or target.startswith(_INTRUDERS_BASE + os.sep):
        return target
    return None


@system_bp.route('/intruders/list', methods=['POST'])
def intruders_list():
    """List capture sessions from ~/Desktop/intruders (newest first)."""
    try:
        sessions = []
        if os.path.isdir(_INTRUDERS_BASE):
            for name in sorted(os.listdir(_INTRUDERS_BASE), reverse=True):
                sdir = os.path.join(_INTRUDERS_BASE, name)
                if not name.startswith("session_") or not os.path.isdir(sdir):
                    continue
                files = os.listdir(sdir)
                sessions.append({
                    "id": name,
                    "timestamp": name.replace("session_", ""),
                    "screenshot": "screenshot.png" if "screenshot.png" in files else None,
                    "webcam": "webcam.jpg" if "webcam.jpg" in files else None,
                })
        return jsonify({"status": "success", "sessions": sessions})
    except Exception as e:
        logger.error(f"Error listing intruders: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500


@system_bp.route('/intruders/file', methods=['GET'])
def intruders_file():
    """Serve a capture image. Query: session, name, token (for <img> auth)."""
    session = os.path.basename(request.args.get("session", ""))
    name = os.path.basename(request.args.get("name", ""))
    target = _intruder_path(session, name)
    if not target or not os.path.isfile(target):
        return jsonify({"status": "error", "error": "not found"}), 404
    return send_file(target)


@system_bp.route('/intruders/delete', methods=['POST'])
def intruders_delete():
    """Delete a capture session folder."""
    try:
        session = os.path.basename((request.get_json(silent=True) or {}).get("session", ""))
        target = _intruder_path(session)
        if not target or target == _INTRUDERS_BASE or not os.path.isdir(target):
            return jsonify({"status": "error", "error": "not found"}), 404
        shutil.rmtree(target)
        logger.info(f"Deleted intruder session {session}")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error deleting intruder session: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500


@system_bp.route('/mouse-click', methods=['POST'])
def mouse_click():
    """Tap-to-click on the screen stream. Body: {"rx": 0..1, "ry": 0..1}.
    Maps the normalized point onto the primary monitor (logical points, matching
    the MJPEG stream's coordinate space) and left-clicks there.
    """
    try:
        data = request.get_json(silent=True) or {}
        rx = float(data.get("rx", -1))
        ry = float(data.get("ry", -1))
        if not (0.0 <= rx <= 1.0 and 0.0 <= ry <= 1.0):
            return jsonify({"status": "error", "error": "rx/ry must be between 0 and 1"}), 400

        with mss.mss() as sct:
            mon = sct.monitors[1]  # primary monitor (logical size)
            x = mon["left"] + rx * mon["width"]
            y = mon["top"] + ry * mon["height"]

        _mouse.position = (x, y)
        _mouse.click(Button.left, 1)
        logger.info(f"mouse-click at ({x:.0f}, {y:.0f})")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error in mouse-click: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@system_bp.route('/pressKey', methods=['POST'])
def press_key():
    """Press a key (optionally with modifiers) on the Mac via macOS System Events.

    Body: {"key": "c", "modifiers": ["cmd", "shift"]}
      - key: a single printable char ("c", "1", "/") OR a named key in KEY_CODES.
      - modifiers: any of cmd/option/ctrl/shift (optional).
    osascript handles ALL modifiers reliably (unlike pynput's option/ctrl on macOS).
    """
    try:
        data = request.get_json(silent=True) or {}
        key = data.get("key")
        modifiers = data.get("modifiers") or []

        if not isinstance(key, str) or key == "":
            return jsonify({"status": "error", "error": "Missing 'key'"}), 400

        phrases = [MODIFIER_PHRASES[m] for m in modifiers if m in MODIFIER_PHRASES]
        using = f" using {{{', '.join(phrases)}}}" if phrases else ""

        if key.lower() in KEY_CODES:
            action = f"key code {KEY_CODES[key.lower()]}{using}"
        elif len(key) == 1:
            ch = key.replace("\\", "\\\\").replace('"', '\\"')  # escape for the AppleScript string literal
            action = f'keystroke "{ch}"{using}'
        else:
            return jsonify({"status": "error", "error": f"Unknown key: {key}"}), 400

        script = f'tell application "System Events" to {action}'
        subprocess.run(["osascript", "-e", script], capture_output=True)
        logger.info(f"pressKey: {modifiers}+{key}")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error in pressKey: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

