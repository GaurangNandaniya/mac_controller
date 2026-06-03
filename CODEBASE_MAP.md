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

**Auth flow:** Mobile app loads `/auth/qr` → server generates temp JWT + QR code → app scans QR → POSTs to `/auth/connect` with temp token (rate-limited: 10 req/min/IP) → server validates, marks temp token used, generates permanent JWT (30-day expiry) → all subsequent requests carry permanent JWT via `auth_manager.auth_middleware()`. JWT expiry is enforced natively via `jwt.decode()`. The QR's embedded `serviceUrl` uses the host's single `.local` mDNS name (`https://<hostname>.local:<port>`) — `qr_generator.py` only appends `.local` when `socket.gethostname()` doesn't already end in it, since a doubled `.local.local` name has no mDNS responder and times out (~10s) on every cold lookup. The mkcert leaf cert must therefore cover that single `.local` name.

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

## Troubleshooting / Operational Gotchas
- **iPhone can't connect via `<hostname>.local` but the LAN IP works** → macOS's mDNSResponder is wedged (common after running several server instances at once, or after a DHCP IP change). Note: the web app resolves `<hostname>.local` through **macOS Bonjour**, not the app's zeroconf — so this is a system-level issue, not an app bug. Fix on the Mac: `sudo killall -HUP mDNSResponder` (optionally `sudo dscacheutil -flushcache`), then toggle the **phone's Wi-Fi** to clear iOS's own mDNS cache. Verify what's advertised on the wire with `dig +short -p 5353 @224.0.0.251 <hostname>.local A` (must return the LAN IP). A `127.0.0.1` answer on interface 1 (loopback) is normal and never leaves the Mac. Do **not** trust `dns-sd … | head` — it block-buffers into pipes and drops answers; query to a file or use the `dig` one-shot.
- **Run only ONE instance.** Multiple menu-bar/server processes collide on the mDNS service name and the UDP beacon port (`Errno 48 Address already in use` on 53535), firing zeroconf's name-conflict loop and destabilizing `.local` resolution. Always `pkill -f mac_controller_app` before relaunching.
- **Latent doubled-`.local` in `mdns_service.py` (`server=f"{hostname}.local"`)** — `socket.gethostname()` already ends in `.local`, so the service advertises `….local.local` (same bug class fixed in `qr_generator.py`). Currently harmless (no client queries that name) — but de-dup carefully: naively switching to the single `.local` makes zeroconf conflict with macOS's own A-record for that name and rename itself to `…-2.local`. Use a distinct service-only hostname if fixing.
- **Command latency / HTTP keep-alive ceiling.** The Flask dev server (`werkzeug/serving.py`) hardcodes `Connection: close` and disables keep-alive, so every command pays a fresh TCP+TLS handshake (~250ms over Wi-Fi); `threaded=True` does **not** change this. A Cheroot swap fixed keep-alive on desktop (~250ms→~6ms) but its `BuiltinSSLAdapter` TLS is **rejected by iOS WebKit** — and curl/openssl/desktop-Chrome all accept it, so none are valid stand-ins for iOS. **Any keep-alive server change (gunicorn/hypercorn/Cheroot) MUST be tested against a real iPhone before shipping.** The Cheroot attempt is parked in `git stash`.

## Known Open Items (Hardening)
- **Single-instance enforcement (highest value).** The menu-bar app can be launched multiple times; duplicate instances collide on the mDNS service name + UDP beacon port and wedge `.local` resolution (root cause of the 2026-06-03 iOS regression). Add a guard that refuses to start a second instance (or kills/cleans up stale ones on launch).
- **De-dup `mdns_service.py:89` (`server=f"{hostname}.local"`).** Currently advertises the doubled `….local.local`. Fix carefully: naively switching to the single `.local` makes zeroconf collide with macOS's own A-record for that name and rename itself to `…-2.local` — so use a distinct service-only hostname, then re-test resolution on a real iPhone.
- **Keep-alive perf (parked).** Per-command latency is the Flask dev server's hardcoded `Connection: close`. A Cheroot swap fixed it on desktop but iOS WebKit rejected its TLS (parked in `git stash`). Revisit with gunicorn/hypercorn (stdlib `ssl`, like Werkzeug) and **test on a real iPhone before shipping**.

## Last Updated
2026-06-03 — Diagnosed an iOS "can't connect" regression: the iPhone couldn't resolve `Gaurangs-MacBook-Pro.local` (LAN IP worked) because macOS's mDNSResponder was wedged after a day of duplicate instances + a DHCP IP flip. Fixed with `killall -HUP mDNSResponder` + phone Wi-Fi toggle (no code change). Added the Troubleshooting section above. Also confirmed (and reverted) that the Flask dev server's hardcoded `Connection: close` causes the per-command handshake latency, and that a Cheroot keep-alive fix — while working on desktop — is rejected by iOS WebKit (parked in git stash).

2026-06-02 — Fixed QR `serviceUrl` host: `qr_generator.py` no longer doubles the `.local` suffix (the doubled `.local.local` name had no mDNS responder, causing a ~10s cold-resolution timeout that surfaced as multi-second lag on the first command after the client sat idle). Cert regenerated for the single `.local` name.

2026-05-02 — Reflects completion of all 25 audit issues: bug fixes, security hardening (subprocess everywhere, rate limiting, debug-mode env var, removed token leaks, JWT expiry enforced), perf (lazy PyAudio, no save-on-every-request, temp token cleanup), code quality (zero `print()` in src/, unused imports removed, debug methods deleted), keyboard backlight via CoreBrightness, and dependency cleanup (pyobjc trimmed from 160+ to 3 frameworks, deprecated `dotenv` wrapper removed).
