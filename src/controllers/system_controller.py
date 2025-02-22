from flask import Blueprint, jsonify
import os
from ..utils import setup_logger

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