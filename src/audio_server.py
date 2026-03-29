import os
import sys
import pyaudio
from flask import Flask
from flask_sock import Sock
from flask_cors import CORS

# Import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import AUDIO_SHARE_PORT, AUDIO_SAMPLE_RATE, AUDIO_CHANNELS, AUDIO_CHUNK_SIZE

app = Flask(__name__)
CORS(app)
sock = Sock(app)

def get_blackhole_device_index(p):
    """Finds the PyAudio device index for BlackHole."""
    for i in range(p.get_device_count()):
        dev_info = p.get_device_info_by_index(i)
        if "BlackHole" in dev_info.get("name", "") and dev_info.get("maxInputChannels") > 0:
            return i
    return None

@sock.route('/audio_ws')
def audio_stream(ws):
    """WebSocket endpoint that continuously blasts Int16 PCM arrays to the browser."""
    p = pyaudio.PyAudio()
    device_index = get_blackhole_device_index(p)
    
    if device_index is None:
        print("Warning: BlackHole virtual audio driver not found. Falling back to default input (Microphone).")
        # If BlackHole isn't installed, it will just pick up the MacBook microphone as a fallback.
        
    try:
        stream = p.open(
            format=pyaudio.paInt16, # Int16 provides the most stable backend mapping for BlackHole
            channels=AUDIO_CHANNELS,
            rate=AUDIO_SAMPLE_RATE,
            input=True,
            frames_per_buffer=AUDIO_CHUNK_SIZE,
            input_device_index=device_index
        )
        print(f"Audio WS Client Connected. Streaming Int16 from device index {device_index}...")

        while True:
            # Read raw bytes of Int16 PCM buffer
            # exception_on_overflow=False guarantees it drops chunks if CPU gets behind rather than crashing
            data = stream.read(AUDIO_CHUNK_SIZE, exception_on_overflow=False)
            ws.send(data)
            
    except Exception as e:
        print(f"Audio WS client disconnected or errored: {e}")
    finally:
        if 'stream' in locals() and stream.is_active():
            stream.stop_stream()
            stream.close()
        p.terminate()

def run_audio_server():
    """Entry point for the dedicated audio server process."""
    print(f"Starting Dedicated Audio WebSocket Server on port {AUDIO_SHARE_PORT}")
    app.run(
        host='0.0.0.0',
        port=AUDIO_SHARE_PORT,
        debug=False,
        use_reloader=False,
        threaded=True
    )

if __name__ == '__main__':
    run_audio_server()
