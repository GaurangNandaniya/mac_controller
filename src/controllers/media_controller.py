from flask import Blueprint, jsonify
from pynput.keyboard import Key, Controller
from ..utils import setup_logger
import os
from src.utils.auth_manager import AuthManager

# Initialize authentication
auth_manager = AuthManager()

logger = setup_logger()

media_bp = Blueprint('media', __name__)
media_bp.before_request(auth_manager.auth_middleware())
keyboard = Controller()

@media_bp.route('/play-pause', methods=['POST'])
def play_pause():
    try:
        keyboard.press(Key.media_play_pause)
        keyboard.release(Key.media_play_pause)
        logger.info("Media play/pause successful")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error in play/pause: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@media_bp.route('/previous', methods=['POST'])
def previous_track():
    try:
        keyboard.press(Key.media_previous)
        keyboard.release(Key.media_previous)
        logger.info("Media previous successful")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error in previous track: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500
    
@media_bp.route('/next', methods=['POST'])
def next_track():
    try:
        keyboard.press(Key.media_next)
        keyboard.release(Key.media_next)
        logger.info("Media previous successful")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error in previous track: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@media_bp.route('/volume-up', methods=['POST'])
def volume_up():
    try:
        keyboard.press(Key.media_volume_up)
        keyboard.release(Key.media_volume_up)
        logger.info("Volume up successful")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error in volume up: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@media_bp.route('/volume-down', methods=['POST'])
def volume_down():
    try:
        keyboard.press(Key.media_volume_down)
        keyboard.release(Key.media_volume_down)
        logger.info("Volume down successful")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error in volume down: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@media_bp.route('/volume-set/<int:level>', methods=['POST'])
def set_volume(level):
    try:
        # Ensure level is between 0 and 100
        level = max(0, min(100, level))
        os.system(f'''osascript -e "set volume output volume {level}"''')
        logger.info(f"Volume set to {level}% successful")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error setting volume to {level}%: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@media_bp.route('/mute', methods=['POST'])
def toggle_mute():
    try:
        os.system('''osascript -e "set volume output muted not (output muted of (get volume settings))"''')
        logger.info("Mute toggled successfully")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error toggling mute: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500
    
@media_bp.route('/up', methods=['POST'])
def arrow_up():
    try:
        keyboard.press(Key.up)
        keyboard.release(Key.up)
        logger.info("Arrow up pressed successfully")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error pressing arrow up: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@media_bp.route('/down', methods=['POST'])
def arrow_down():
    try:
        keyboard.press(Key.down)
        keyboard.release(Key.down)
        logger.info("Arrow down pressed successfully")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error pressing arrow down: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@media_bp.route('/left', methods=['POST'])
def arrow_left():
    try:
        keyboard.press(Key.left)
        keyboard.release(Key.left)
        logger.info("Arrow left pressed successfully")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error pressing arrow left: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@media_bp.route('/right', methods=['POST'])
def arrow_right():
    try:
        keyboard.press(Key.right)
        keyboard.release(Key.right)
        logger.info("Arrow right pressed successfully")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error pressing arrow right: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500    