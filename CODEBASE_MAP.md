# Codebase Map

## Project Overview
A macOS remote control server that lets a mobile app (or web app) control a MacBook over the local network — media playback, volume, brightness, keyboard/mouse lock, screen/camera streaming, audio streaming, and system commands. Runs as a macOS menu bar app with mDNS/UDP discovery.

## Tech Stack
- **Language:** Python 3
- **Web framework:** Flask (blueprints), flask-cors, flask-sock
- **Streaming:** OpenCV (MJPEG), aiortc (WebRTC), PyAudio + Web Audio (system audio)
- **macOS integration:** pyobjc-core + 3 frameworks (Cocoa, Quartz, ApplicationServices), CoreBrightness (private framework, runtime-loaded), rumps (menu bar), pynput (keyboard/mouse), subprocess+osascript
- **Discovery:** zeroconf (mDNS), UDP beacon on port 53535
- **Auth:** JWT (PyJWT), QR-code pairing flow with rate limiting
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

**Auth flow:** Mobile app loads `/auth/qr` → server generates temp JWT + QR code → app scans QR → POSTs to `/auth/connect` with temp token (rate-limited: 10 req/min/IP) → server validates, marks temp token used, generates permanent JWT (30-day expiry) → all subsequent requests carry permanent JWT via `auth_manager.auth_middleware()`. JWT expiry is enforced natively via `jwt.decode()`.

**Discovery flow:** mDNS broadcasts `_macpyctrlserver._tcp.local.` + UDP beacon on port 53535 responds to `DISCOVER_MACBOOK_SERVER` messages. The `/connections/ping` HTTP endpoint also returns `<ip>:<SERVER_PORT>` for fallback discovery.

**Keyboard backlight:** Apple Silicon Macs don't respond to traditional key codes (107/113), so `system_controller.set_keyboard_light()` uses Apple's private `CoreBrightness.framework` via `objc.loadBundle()` and the `KeyboardBrightnessClient` class with keyboard ID `1`.

## Patterns & Conventions
- **Blueprint pattern:** Each controller is a Flask Blueprint with `before_request(auth_manager.auth_middleware())`
- **Logging:** `setup_logger()` from `src/utils/logger.py` for code that runs in the main process (rotating file + console, with a handler guard to prevent duplicates). Streaming servers, mdns_service, and keyboardMouseController use `logging.getLogger(name)` directly since they may run in subprocesses.
- **macOS commands:** All shell-out uses `subprocess.run()` with arg lists (no `os.system()`, no shell=True) to prevent command injection.
- **Streaming servers:** Run as isolated `multiprocessing.Process` instances, managed by the menu bar app. They have no auth (manually started, local-only by design).
- **Audio resources:** `PyAudio()` is lazy-initialized via `get_pyaudio()` in `alerts.py`; `cleanup_audio()` registered with `atexit` to release on shutdown.
- **Token cleanup:** Temp tokens are cleaned via `cleanup_expired_tokens()` whenever a new one is generated, preventing unbounded growth.
- **Config:** `config.py` at project root, loaded via `app.config.from_pyfile()`. `DEBUG_MODE` reads from env (defaults `false`). Secrets and per-machine config (AUTH_SECRET_KEY, WEB_APP_URL, certs) live in `.env`.
- **CORS:** Origins list filters out `None` so the app starts cleanly even without `WEB_APP_URL` set.
- **Naming:** Snake_case throughout source. The file `keyboardMouseController.py` is camelCase but renaming would break imports — internal identifiers within it follow snake_case.

## Last Updated
2026-05-02 — Reflects completion of all 25 audit issues: bug fixes, security hardening (subprocess everywhere, rate limiting, debug-mode env var, removed token leaks, JWT expiry enforced), perf (lazy PyAudio, no save-on-every-request, temp token cleanup), code quality (zero `print()` in src/, unused imports removed, debug methods deleted), keyboard backlight via CoreBrightness, and dependency cleanup (pyobjc trimmed from 160+ to 3 frameworks, deprecated `dotenv` wrapper removed).
