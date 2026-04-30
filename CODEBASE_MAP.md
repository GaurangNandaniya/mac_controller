# Codebase Map

## Project Overview
A macOS remote control server that lets a mobile app (or web app) control a MacBook over the local network — media playback, volume, brightness, keyboard/mouse lock, screen/camera streaming, audio streaming, and system commands. Runs as a macOS menu bar app with mDNS/UDP discovery.

## Tech Stack
- **Language:** Python 3
- **Web framework:** Flask (blueprints), flask-cors, flask-sock
- **Streaming:** OpenCV (MJPEG), aiortc (WebRTC), PyAudio + Web Audio (system audio)
- **macOS integration:** pyobjc, rumps (menu bar), pynput (keyboard/mouse), osascript commands
- **Discovery:** zeroconf (mDNS), UDP beacon on port 53535
- **Auth:** JWT (PyJWT), QR-code pairing flow
- **Config:** python-dotenv (.env), config.py

## Directory Structure
```
mac_controller/
├── config.py                  # Server/streaming ports, debug flag
├── run.py                     # Standalone Flask + mDNS entry point (legacy)
├── mac_controller_app.py      # Menu bar app entry point (rumps) — primary
├── requirements.txt
├── src/
│   ├── __init__.py            # Creates Flask app, exposes setup_logger
│   ├── server.py              # create_app() — Flask factory, CORS, blueprint registration
│   ├── controllers/
│   │   ├── media_controller.py    # /media/* — play/pause, next/prev, volume, arrow keys
│   │   ├── system_controller.py   # /system/* — lock, sleep, brightness, battery, capture, kb/mouse lock
│   │   ├── stream_controller.py   # /system/camera/stream, /system/screen/stream (MJPEG)
│   │   ├── alerts.py              # /alerts/* — audio upload, real-time audio stream playback
│   │   ├── connections.py         # /connections/ping — discovery ping response
│   │   ├── qr_generator.py       # /auth/* — QR pairing, token generation
│   │   └── api.py                 # /api/* — generic data receiver
│   ├── services/
│   │   └── mdns_service.py        # MDNSService class — mDNS + UDP beacon (used by menu bar app)
│   ├── streams/                   # Standalone streaming servers (separate processes)
│   │   ├── screen_share_server.py # MJPEG screen share on port 9090
│   │   ├── webrtc_server.py       # WebRTC screen share on port 9091
│   │   └── audio_server.py        # System audio stream on port 9092
│   └── utils/
│       ├── auth_manager.py        # AuthManager — JWT tokens, pairing, middleware
│       ├── keyboardMouseController.py  # Keyboard/mouse lock/unlock via pynput, TTS
│       ├── logger.py              # Rotating file + console logger
│       └── socket.py              # get_local_ip() helper
├── mac_controller_rust/           # Rust port (experimental, not active)
└── logs/                          # Rotating log files
```

## Key Modules & Relationships
```
mac_controller_app.py (menu bar — primary entry point)
  ├── src/server.py → create_app() → Flask app with 7 blueprints
  │     ├── media_controller (media_bp)
  │     ├── system_controller (system_bp)
  │     ├── stream_controller (stream_bp)    ← mounted at /system prefix
  │     ├── alerts (alerts_bp)
  │     ├── connections (connections_bp)
  │     ├── qr_generator (auth_bp)
  │     └── api (api_bp)
  ├── src/services/mdns_service.py → MDNSService (mDNS + UDP)
  ├── src/streams/* → launched as separate multiprocessing.Process
  └── src/utils/auth_manager.py → auth_manager (singleton, shared across blueprints)

run.py (standalone entry point — legacy, duplicates mDNS logic)
```

**Auth flow:** Mobile app hits `/auth/generate-qr` → gets temp token + QR code → scans QR → calls `/auth/authenticate` with temp token → gets permanent JWT → all subsequent requests use JWT via `auth_manager.auth_middleware()`.

**Discovery flow:** mDNS broadcasts `_macpyctrlserver._tcp.local.` + UDP beacon on port 53535 responds to `DISCOVER_MACBOOK_SERVER` messages.

## Patterns & Conventions
- **Blueprint pattern:** Each controller is a Flask Blueprint with `before_request(auth_manager.auth_middleware())`
- **Logging:** `setup_logger()` from `src/utils/logger.py` — rotating file handler + console
- **macOS commands:** Mix of `os.system()` with osascript and `subprocess.run()` (inconsistent — os.system is being phased out)
- **Streaming servers:** Run as isolated `multiprocessing.Process` instances, managed by the menu bar app
- **Config:** `config.py` at project root, loaded via `app.config.from_pyfile()`; secrets in `.env`
- **Naming:** Mostly snake_case, some camelCase in older files (keyboardMouseController)

## Last Updated
2026-04-30 — Initial map generated during bug fix batch (issues #2-8).
