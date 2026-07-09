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
import atexit
from src.utils.auth_manager import auth_manager

logger = setup_logger()

alerts_bp = Blueprint('alerts', __name__)
alerts_bp.before_request(auth_manager.auth_middleware())

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
p = None
stream = None
current_file = None
current_sample_rate = None
current_channels = None
playback_lock = threading.Lock()
file_lock = threading.Lock()

def get_pyaudio():
    """Lazy-initialize PyAudio on first use instead of at module import."""
    global p
    if p is None:
        p = pyaudio.PyAudio()
    return p

# Configuration
UPLOAD_DIR = os.path.expanduser("~/Desktop/intruders/streams")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# LEGACY — replaced by the /alerts/audio_ws WebSocket (see register_audio_in_ws
# below). This per-chunk HTTP POST path fired ~43 POSTs/sec; on the keep-alive-less
# Flask dev server (Connection: close) each chunk paid a fresh TCP+TLS handshake, so
# audio arrived with 40-190ms jitter (mean ~50ms vs a 23ms budget) -> constant
# output underruns / breaking. Kept for reference, not registered (decorator
# commented out) — the client now streams over the WebSocket.
# @alerts_bp.route('/stream/audio', methods=['POST'])
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
                    
                stream = get_pyaudio().open(
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
                    stream = get_pyaudio().open(
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

def register_audio_in_ws(sock):
    """Register /alerts/audio_ws — live phone->Mac mic audio over one WebSocket.

    Replaces the legacy per-chunk HTTP POST path. A single persistent socket has
    no per-chunk TCP+TLS handshake, so PCM arrives at the real-time rate instead
    of with 40-190ms jitter. A callback-driven PyAudio output stream is the jitter
    buffer: PyAudio pulls exactly frame_count samples at the audio clock, emitting
    silence on underrun; the WS thread only appends to the buffer and records to
    disk (off the audio callback, so file I/O never stalls playback). Auth via
    ?token= (same as mouse_ws/mic_ws); rate+channels come from query args because
    iOS AudioContext runs at 48kHz, not the old hardcoded 44.1kHz.
    """

    @sock.route('/alerts/audio_ws')
    def audio_in_ws(ws):
        token = request.args.get('token', '')
        _, err = auth_manager.validate_permanent_token(token)
        if err:
            logger.info(f"audio_ws rejected: {err}")
            return  # closes the socket

        rate = int(request.args.get('rate', 48000))
        channels = int(request.args.get('channels', 1))
        bytes_per_frame = 2 * channels  # paInt16 = 2 bytes/sample
        max_bytes = rate * bytes_per_frame  # ~1s cap so a burst can't build unbounded latency

        buf = bytearray()
        buf_lock = threading.Lock()

        def callback(in_data, frame_count, time_info, status):
            need = frame_count * bytes_per_frame
            with buf_lock:
                if len(buf) >= need:
                    out = bytes(buf[:need])
                    del buf[:need]
                else:
                    out = bytes(buf) + b'\x00' * (need - len(buf))  # underrun -> silence
                    buf.clear()
            return (out, pyaudio.paContinue)

        out_stream = None
        wav = None
        try:
            out_stream = get_pyaudio().open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                output=True,
                frames_per_buffer=1024,
                stream_callback=callback,
            )
            out_stream.start_stream()

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            wav_path = os.path.join(UPLOAD_DIR, f"{timestamp}_{rate}Hz_{channels}ch.wav")
            wav = wave.open(wav_path, 'wb')
            wav.setnchannels(channels)
            wav.setsampwidth(2)
            wav.setframerate(rate)

            logger.info(f"audio_ws connected — {rate}Hz {channels}ch, recording {os.path.basename(wav_path)}")

            while True:
                data = ws.receive()
                if data is None:
                    break
                if isinstance(data, str):
                    continue  # ignore text/control frames
                with buf_lock:
                    buf.extend(data)
                    if len(buf) > max_bytes:  # drop oldest to keep latency bounded
                        del buf[:len(buf) - max_bytes]
                wav.writeframes(data)  # WS thread, not the audio callback → never stalls playback

        except Exception as e:
            logger.info(f"audio_ws disconnected or errored: {e}")
        finally:
            if out_stream is not None:
                try:
                    out_stream.stop_stream()
                    out_stream.close()
                except Exception:
                    logger.warning("audio_ws: error closing output stream")
            if wav is not None:
                try:
                    wav.close()
                except Exception:
                    pass
            logger.info("audio_ws closed")


def cleanup_audio():
    global p, stream
    if stream:
        stream.stop_stream()
        stream.close()
    if p is not None:
        p.terminate()
    logger.info("Audio resources released")

atexit.register(cleanup_audio)