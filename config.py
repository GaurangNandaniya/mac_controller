import os

# Basic configuration
SERVER_HOST = '0.0.0.0'  # Allow external connections
SERVER_PORT = 8080
DEBUG_MODE = os.environ.get('DEBUG_MODE', 'false').lower() == 'true'

# Screen Share Server configuration (MJPEG)
SCREEN_SHARE_PORT = 9090
SCREEN_SHARE_FPS = 30     # Max FPS for desktop mode
SCREEN_SHARE_QUALITY = 80 # Default JPEG quality

# WebRTC Screen Share configuration (Experimental)
WEBRTC_SHARE_PORT = 9091
WEBRTC_FPS = 30

# System Audio Share configuration (BlackHole loopback)
AUDIO_SHARE_PORT = 9092
AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 2
AUDIO_CHUNK_SIZE = 1024  # ~21ms buffering at 48kHz (lower lag; was 2048 ≈ 43ms)
