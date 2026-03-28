"""
Dedicated Screen Share Server — H.264 via FFmpeg + WebSocket + fMP4

A standalone Flask server that streams the screen at high quality using:
- mss for screen capture
- FFmpeg for H.264 encoding (fragmented MP4)
- WebSocket for delivering encoded chunks to browser
- Media Source Extensions (MSE) in browser for playback

Designed to be started/stopped on-demand from the menu bar.
No auth — meant to be shared with anyone on the local network.
"""

import subprocess
import threading
import time
import os
import sys
import signal

import mss
import numpy as np
from flask import Flask, render_template
from flask_sock import Sock
from flask_cors import CORS

# Import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import SCREEN_SHARE_PORT, SCREEN_SHARE_FPS, SCREEN_SHARE_QUALITY


def create_screen_share_app():
    """Create and configure the screen share Flask app."""
    app = Flask(__name__, template_folder='templates')
    CORS(app)
    sock = Sock(app)

    @app.route('/')
    def viewer_page():
        """Serve the full-screen viewer HTML page."""
        return render_template('screen_share.html')

    @sock.route('/ws')
    def screen_ws(ws):
        """
        WebSocket endpoint that streams H.264 encoded screen capture.

        Flow:
        1. mss captures screen at target FPS (raw BGRA frames)
        2. Frames piped to ffmpeg as raw video input
        3. ffmpeg encodes to H.264 with fragmented MP4 output
        4. Encoded chunks read from ffmpeg stdout and sent over WebSocket
        """
        ffmpeg_process = None
        capture_thread = None
        stop_event = threading.Event()

        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # Primary monitor
                width = monitor['width']
                height = monitor['height']

                # Start ffmpeg subprocess for H.264 encoding
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-y',
                    '-f', 'rawvideo',
                    '-pix_fmt', 'bgra',
                    '-s', f'{width}x{height}',
                    '-r', str(SCREEN_SHARE_FPS),
                    '-i', 'pipe:0',
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-tune', 'zerolatency',
                    '-crf', str(SCREEN_SHARE_QUALITY),
                    '-pix_fmt', 'yuv420p',
                    '-g', str(SCREEN_SHARE_FPS),  # Keyframe every 1 second
                    '-f', 'mp4',
                    '-movflags', 'frag_keyframe+empty_moov+default_base_moof',
                    'pipe:1'
                ]

                ffmpeg_process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=0
                )

                def capture_frames():
                    """Background thread: capture screen frames and pipe to ffmpeg."""
                    frame_interval = 1.0 / SCREEN_SHARE_FPS

                    try:
                        while not stop_event.is_set():
                            start_time = time.time()

                            screenshot = sct.grab(monitor)
                            frame_bytes = bytes(screenshot.rgb)

                            # mss gives RGB, but we told ffmpeg bgra
                            # Actually mss .rgb gives RGB, let's use raw bgra
                            raw = np.array(screenshot)  # BGRA numpy array
                            raw_bytes = raw.tobytes()

                            try:
                                ffmpeg_process.stdin.write(raw_bytes)
                                ffmpeg_process.stdin.flush()
                            except (BrokenPipeError, OSError):
                                break

                            elapsed = time.time() - start_time
                            if elapsed < frame_interval:
                                time.sleep(frame_interval - elapsed)
                    except Exception as e:
                        print(f"Capture thread error: {e}")
                    finally:
                        try:
                            if ffmpeg_process.stdin:
                                ffmpeg_process.stdin.close()
                        except Exception:
                            pass

                # Start capture in background thread
                capture_thread = threading.Thread(target=capture_frames, daemon=True)
                capture_thread.start()

                # Read encoded H.264 chunks from ffmpeg stdout and send over WebSocket
                CHUNK_SIZE = 8192
                while True:
                    chunk = ffmpeg_process.stdout.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    try:
                        ws.send(chunk)
                    except Exception:
                        # Client disconnected
                        break

        except Exception as e:
            print(f"Screen share WebSocket error: {e}")
        finally:
            stop_event.set()

            if ffmpeg_process:
                try:
                    ffmpeg_process.stdin.close()
                except Exception:
                    pass
                try:
                    ffmpeg_process.terminate()
                    ffmpeg_process.wait(timeout=3)
                except Exception:
                    try:
                        ffmpeg_process.kill()
                    except Exception:
                        pass

            if capture_thread and capture_thread.is_alive():
                capture_thread.join(timeout=2)

            print("Screen share session ended")

    return app


def run_screen_share_server():
    """Entry point to run the screen share server (called from multiprocessing)."""
    app = create_screen_share_app()
    print(f"Screen Share server starting on port {SCREEN_SHARE_PORT}")
    app.run(
        host='0.0.0.0',
        port=SCREEN_SHARE_PORT,
        debug=False,
        use_reloader=False
    )


if __name__ == '__main__':
    run_screen_share_server()
