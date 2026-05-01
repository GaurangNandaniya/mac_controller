"""
Dedicated Screen Share Server (Optimized MJPEG)

After evaluating H.264, WebSockets+DeltaTiles, and WebSockets+BoundingBox,
HTTP MJPEG (multipart/x-mixed-replace) is proven to be the most reliable, 
fastest, and lowest-latency method for this particular architecture because:
1. Natively handled by browser's low-level C++ rendering engine (zero JS overhead).
2. Completely immune to visual tearing and Javascript async queuing stutters.
3. Automatically applies hardware JPEG decoding.

This standalone Flask server runs on its own port and streams the screen
continuously at the highest achievable frame rate (~20-30 FPS).
"""

import logging
import time
import os
import sys

import mss
import numpy as np
import cv2
from flask import Flask, render_template, Response, jsonify
from flask_cors import CORS

# Import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import SCREEN_SHARE_PORT, SCREEN_SHARE_FPS, SCREEN_SHARE_QUALITY

logger = logging.getLogger('screen_share_server')

# Global stats for the /stats endpoint
stream_stats = {
    'bytes_sent': 0,
    'frames_sent': 0,
    'last_reset': time.time(),
    'fps': 0,
    'bps': 0
}


def generate_mjpeg_stream():
    """Generator that captures screen constantly and yields JPEG frames."""
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor
            logical_w = monitor['width']
            logical_h = monitor['height']

            frame_interval = 1.0 / SCREEN_SHARE_FPS

            logger.info(f"Starting optimized MJPEG capture sequence. Target FPS is {SCREEN_SHARE_FPS}")

            while True:
                start_time = time.time()

                # --- Capture ---
                screenshot = sct.grab(monitor)
                raw = np.array(screenshot)

                # --- Downscale if Retina ---
                if raw.shape[1] > logical_w:
                    # Near-instant 2x downsample via slicing
                    frame = raw[::2, ::2, :3]
                else:
                    frame = raw[:, :, :3]

                # --- Encode ---
                _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, SCREEN_SHARE_QUALITY])

                # --- Yield HTTP Stream Chunk ---
                chunk = (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')
                
                # Update statistics
                now = time.time()
                stream_stats['bytes_sent'] += len(chunk)
                stream_stats['frames_sent'] += 1
                
                if now - stream_stats['last_reset'] >= 1.0:
                    stream_stats['fps'] = stream_stats['frames_sent']
                    stream_stats['bps'] = stream_stats['bytes_sent']
                    stream_stats['frames_sent'] = 0
                    stream_stats['bytes_sent'] = 0
                    stream_stats['last_reset'] = now

                yield chunk

                # --- Throttle to target FPS ---
                elapsed = time.time() - start_time
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

    except GeneratorExit:
        logger.info("Screen share client disconnected")
    except Exception as e:
        logger.error(f"Screen share error: {e}")


def create_screen_share_app():
    """Create and configure the screen share Flask app."""
    app = Flask(__name__, template_folder='../templates')
    CORS(app)

    @app.route('/')
    def viewer_page():
        """Serve the full-screen viewer HTML page."""
        return render_template('screen_share.html')

    @app.route('/stream')
    def stream():
        """MJPEG video feed endpoint."""
        return Response(
           generate_mjpeg_stream(),
           mimetype='multipart/x-mixed-replace; boundary=frame'
        )
        
    @app.route('/stats')
    def stats():
        """Returns the current stream FPS and Bandwidth."""
        return jsonify({
            'fps': stream_stats['fps'],
            'bandwidth_bps': stream_stats['bps']
        })

    return app


def run_screen_share_server():
    """Entry point to run the screen share server (called from multiprocessing)."""
    app = create_screen_share_app()
    logger.info(f"Pure MJPEG Screen Share server starting on port {SCREEN_SHARE_PORT}")
    app.run(
        host='0.0.0.0',
        port=SCREEN_SHARE_PORT,
        debug=False,
        use_reloader=False,
        threaded=True  # Ensure threading is on so it won't stall the main process
    )


if __name__ == '__main__':
    run_screen_share_server()
