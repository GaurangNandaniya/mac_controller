import time
import cv2
import mss
import numpy as np
from flask import Blueprint, Response, request
from ..utils import setup_logger
from src.utils.auth_manager import auth_manager

logger = setup_logger()

# Important: We name this blueprint 'stream', but it will be attached to url_prefix='/system' 
# inside server.py so that the frontend's API contract never changes!
stream_bp = Blueprint('stream', __name__)
stream_bp.before_request(auth_manager.auth_middleware())


def generate_camera_frames(fps):
    """Generator that yields MJPEG frames from the webcam."""
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        logger.error("Could not open webcam for streaming")
        return

    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        
        frame_interval = 1.0 / fps
        
        while True:
            start_time = time.time()
            
            ret, frame = cap.read()
            if not ret:
                logger.warning("Failed to read camera frame")
                break
            
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ret:
                continue
            
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            elapsed = time.time() - start_time
            if elapsed < frame_interval:
                time.sleep(frame_interval - elapsed)
    
    except GeneratorExit:
        logger.info("Camera stream client disconnected")
    except Exception as e:
        logger.error(f"Camera stream error: {str(e)}")
    finally:
        cap.release()
        logger.info("Camera released after stream ended")


def generate_screen_frames(fps):
    """Generator that yields MJPEG frames of the screen capture."""
    try:
        frame_interval = 1.0 / fps
        
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            
            while True:
                start_time = time.time()
                screenshot = sct.grab(monitor)
                frame = np.array(screenshot)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if not ret:
                    continue
                
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
                elapsed = time.time() - start_time
                if elapsed < frame_interval:
                    time.sleep(frame_interval - elapsed)
    
    except GeneratorExit:
        logger.info("Screen stream client disconnected")
    except Exception as e:
        logger.error(f"Screen stream error: {str(e)}")


@stream_bp.route('/camera/stream', methods=['GET'])
def camera_stream():
    """Live webcam MJPEG stream. Use ?fps=N to set frame rate (default 15)."""
    fps = request.args.get('fps', 15, type=int)
    fps = max(1, min(60, fps))
    
    logger.info(f"Starting camera stream at {fps} fps")
    return Response(
        generate_camera_frames(fps),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@stream_bp.route('/screen/stream', methods=['GET'])
def screen_stream():
    """Live screen capture MJPEG stream. Use ?fps=N to set frame rate (default 10)."""
    fps = request.args.get('fps', 10, type=int)
    fps = max(1, min(60, fps))
    
    logger.info(f"Starting screen stream at {fps} fps")
    return Response(
        generate_screen_frames(fps),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )
