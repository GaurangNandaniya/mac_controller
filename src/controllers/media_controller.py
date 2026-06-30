from flask import Blueprint, jsonify
from pynput.keyboard import Key, Controller
from ..utils import setup_logger
import subprocess
from src.utils.auth_manager import auth_manager


logger = setup_logger()

media_bp = Blueprint('media', __name__)
media_bp.before_request(auth_manager.auth_middleware())
keyboard = Controller()


def _run_osa(script):
    """Run an AppleScript and return trimmed stdout (empty string on failure)."""
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        return r.stdout.strip()
    except Exception:
        return ""


# Best-effort now-playing. One script per app, run independently: referencing an
# app's dictionary (e.g. Spotify) fails to COMPILE if that app isn't installed,
# which would otherwise kill a combined script — so keep them separate and let an
# uninstalled app just yield "". Guarded by `is running` so it never launches one.
# (Generic system-wide now-playing needs the private MediaRemote framework.)
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


def _now_playing():
    for script in _NOW_PLAYING_SCRIPTS:
        out = _run_osa(script)
        if out:
            parts = out.split("|")
            if len(parts) >= 3:
                return {"playing": True, "app": parts[0], "track": parts[1], "artist": parts[2]}
    return {"playing": False, "app": None, "track": None, "artist": None}

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
        logger.info("Media next successful")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error in next track: {str(e)}")
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
        subprocess.run(["osascript", "-e", f"set volume output volume {level}"], capture_output=True)
        logger.info(f"Volume set to {level}% successful")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Error setting volume to {level}%: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@media_bp.route('/mute', methods=['POST'])
def toggle_mute():
    try:
        subprocess.run(["osascript", "-e", "set volume output muted not (output muted of (get volume settings))"], capture_output=True)
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

@media_bp.route('/status', methods=['POST'])
def media_status():
    """Current output volume + mute, plus best-effort now-playing (Spotify/Music)."""
    try:
        vol_raw = _run_osa("output volume of (get volume settings)")
        muted_raw = _run_osa("output muted of (get volume settings)")
        volume = int(vol_raw) if vol_raw.lstrip("-").isdigit() else None

        return jsonify({
            "status": "success",
            "volume": volume,
            "muted": muted_raw == "true",
            "nowPlaying": _now_playing(),
        })
    except Exception as e:
        logger.error(f"Error in media status: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500    