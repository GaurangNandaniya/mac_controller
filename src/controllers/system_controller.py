from flask import Blueprint, jsonify
import os
from ..utils import setup_logger
import subprocess
import re
import cv2 
import time
from datetime import datetime

logger = setup_logger()


system_bp = Blueprint('system', __name__)

@system_bp.route('/lock', methods=['POST'])
def lock_screen():
    try:
        os.system("pmset displaysleepnow")
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@system_bp.route('/brightness-up', methods=['POST'])
def brightness_up():
    try:
        os.system('''osascript -e 'tell application "System Events" to Key Code 144' ''')  
        logger.info("Brightness up successful")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error in brightness up: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@system_bp.route('/brightness-down', methods=['POST'])
def brightness_down():
    try:
        os.system('''osascript -e 'tell application "System Events" to Key Code 145' ''') 
        logger.info("Brightness down successful")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error in brightness down: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@system_bp.route('/sleep', methods=['POST'])
def sleep_mac():
    try:
        os.system("pmset sleepnow")
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
        # Ensure level is between 0 and 100
        level = max(0, min(100, level))
        # Convert to hex (0x00 to 0xFF)
        hex_value = hex(int((level/100) * 255))[2:]
        os.system(f"ioreg -n AppleHSKeyboardBacklight -r -d 1 | grep -i 'brightness' | awk '{{print $3}}' | sudo ioreg -c AppleHSKeyboardBacklight -w0 -f -r -d 1 | grep -i 'brightness' | awk '{{print $3}}' | xargs -I % sudo ioreg -c AppleHSKeyboardBacklight -w0 -f -r -d 1 -w {hex_value}")
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