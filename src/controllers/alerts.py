from flask import Blueprint, request, jsonify
from src.utils import setup_logger
from datetime import datetime
from werkzeug.utils import secure_filename
import subprocess
import os
import pyaudio
import threading
import numpy as np
import wave

logger = setup_logger()

alerts_bp = Blueprint('alerts', __name__)

@alerts_bp.route('/upload/audio', methods=['POST'])
def handle_audio_upload():
    """Endpoint for receiving audio file uploads"""
    if 'audio' not in request.files:
        logger.warning("Audio upload attempt with no file")
        return jsonify({'error': 'No audio file provided'}), 400
        
    audio_file = request.files['audio']
    if audio_file.filename == '':
        logger.warning("Audio upload with empty filename")
        return jsonify({'error': 'Invalid file name'}), 400

    logger.info(f"Received audio upload: {audio_file.filename}")
    # Create destination directory if needed
    upload_dir = os.path.expanduser("~/Desktop/intruders/audios")
    os.makedirs(upload_dir, exist_ok=True)
    
    # Generate timestamped filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = secure_filename(audio_file.filename)
    filename = f"{timestamp}_{safe_name}"
    save_path = os.path.join(upload_dir, filename)
    
    try:
        # Save file
        audio_file.save(save_path)
        logger.info(f"Saved audio to {save_path}")
        
        # Play audio using macOS afplay in background
        subprocess.Popen(
            ["afplay", save_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
    except Exception as e:
        logger.error(f"Audio processing failed: {str(e)}")
        return jsonify({"error": "Audio processing failed"}), 500

    return jsonify({'status': 'processed', 'filename': filename, 'path': save_path}), 200


# Global audio variables
p = pyaudio.PyAudio()
stream = None
current_file = None
current_sample_rate = None
current_channels = None
playback_lock = threading.Lock()
file_lock = threading.Lock()

# Configuration
UPLOAD_DIR = os.path.expanduser("~/Desktop/intruders/streams")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@alerts_bp.route('/stream/audio', methods=['POST'])
def handle_audio_stream():
    """Endpoint for receiving real-time audio chunks"""
    global stream, current_file, current_sample_rate, current_channels
    
    logger.info("Incoming audio stream request")

    # Get audio metadata from headers
    try:
        sample_rate = int(request.headers.get('X-Sample-Rate', 44100))
        channels = int(request.headers.get('X-Channels', 1))
        audio_data = request.get_data()
        
        if not audio_data:
            logger.warning("Empty audio chunk received")
            return jsonify({'error': 'No audio data provided'}), 400

        # Initialize or reconfigure PyAudio stream if needed
        with playback_lock:
            if (not stream or 
                current_sample_rate != sample_rate or 
                current_channels != channels):
                
                if stream:
                    try:
                        stream.stop_stream()
                        stream.close()
                    except:
                        logger.warning("Error closing previous stream")
                    
                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=channels,
                    rate=sample_rate,
                    output=True,
                    frames_per_buffer=1024
                )
                current_sample_rate = sample_rate
                current_channels = channels
                logger.info(f"New audio stream: {sample_rate}Hz, {channels} channel(s)")

            # Audio processing
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Real-time playback
            try:
                stream.write(audio_array.tobytes())
            except Exception as e:
                logger.error(f"Playback error: {str(e)}")
                # Try to reinitialize stream on error
                try:
                    stream.stop_stream()
                    stream.close()
                    stream = p.open(
                        format=pyaudio.paInt16,
                        channels=channels,
                        rate=sample_rate,
                        output=True,
                        frames_per_buffer=1024
                    )
                except:
                    logger.error("Failed to recover audio stream")

        # File handling with proper locks
        with file_lock:
            try:
                # Create a new file if necessary
                if (not current_file or 
                    current_sample_rate != sample_rate or 
                    current_channels != channels):
                    
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    current_file = os.path.join(UPLOAD_DIR, 
                        f"{timestamp}_{sample_rate}Hz_{channels}ch.wav")
                    
                    # Initialize new WAV file
                    with wave.open(current_file, 'wb') as wf:
                        wf.setnchannels(channels)
                        wf.setsampwidth(2)  # 16-bit = 2 bytes
                        wf.setframerate(sample_rate)
                        wf.writeframes(audio_array.tobytes())
                else:
                    # Append to existing file
                    with wave.open(current_file, 'ab') as wf:
                        wf.writeframes(audio_array.tobytes())
                
                logger.info(f"Processed {len(audio_data)} bytes to {current_file}")
            except Exception as e:
                logger.error(f"File writing error: {str(e)}")
                return jsonify({"error": f"File writing failed: {str(e)}"}), 500

    except Exception as e:
        logger.error(f"Audio processing failed: {str(e)}")
        return jsonify({"error": f"Audio processing failed: {str(e)}"}), 500

    return jsonify({
        'status': 'processed',
        'filename': os.path.basename(current_file) if current_file else None,
        'sample_rate': sample_rate,
        'channels': channels
    }), 200

# Clean up function - you can register this with atexit in your main app
def cleanup_audio():
    global p, stream
    if stream:
        stream.stop_stream()
        stream.close()
    p.terminate()
    logger.info("Audio resources released")