# Codebase Map

## Project Overview
A macOS remote control server that lets a mobile app (or web app) control a MacBook over the local network — media playback, volume, brightness, keyboard/mouse lock, screen/camera streaming, audio streaming, and system commands. Runs as a macOS menu bar app; clients reach it by the Mac's native `<hostname>.local` (Bonjour) name.

## Tech Stack
- **Language:** Python 3
- **Web framework:** Flask (blueprints), flask-cors, flask-sock
- **Streaming:** OpenCV (MJPEG), aiortc (WebRTC), PyAudio + Web Audio (system audio)
- **macOS integration:** pyobjc-core + 3 frameworks (Cocoa, Quartz, ApplicationServices), CoreBrightness (private framework, runtime-loaded), rumps (menu bar), pynput (keyboard/mouse), subprocess+osascript
- **Discovery:** native macOS Bonjour advertises `<hostname>.local` → current IP. The app runs **no** mDNS responder of its own (removed 2026-06-04 — see Last Updated).
- **Auth:** JWT (PyJWT), QR-code pairing flow with rate limiting
- **Config:** python-dotenv (.env), config.py

## Directory Structure
```
mac_controller/
├── config.py                  # Server/streaming ports, debug flag
├── run.py                     # Standalone Flask entry point (legacy)
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
(`src/services/` now holds only an empty `__init__.py` — its `mdns_service.py` was removed.)

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
  ├── src/streams/* → launched as separate multiprocessing.Process
  └── src/utils/auth_manager.py → auth_manager (singleton, shared across blueprints)

run.py (standalone entry point — legacy)
```

**Auth flow:** Mobile app loads `/auth/qr` → server generates temp JWT + QR code → app scans QR → POSTs to `/auth/connect` with temp token (rate-limited: 10 req/min/IP) → server validates, marks temp token used, generates permanent JWT (30-day expiry) → all subsequent requests carry permanent JWT via `auth_manager.auth_middleware()`. JWT expiry is enforced natively via `jwt.decode()`. The QR's embedded `serviceUrl` uses the host's single `.local` name (`https://<hostname>.local:<port>`) — `qr_generator.py` only appends `.local` when `socket.gethostname()` doesn't already end in it. The mkcert leaf cert must cover that single `.local` name. The IP is never pinned, so the same QR/cert keeps working across DHCP changes (macOS Bonjour maps `.local` to whatever the current IP is).

**Discovery flow:** macOS's own Bonjour responder advertises `<hostname>.local` → current IP on the LAN. A browser opening `https://<hostname>.local:<port>` resolves it via a plain mDNS A-record lookup that macOS answers natively — there is no app-level service record to discover. The `/connections/ping` HTTP endpoint returns `<ip>:<SERVER_PORT>` as an optional fallback.

**mDNS / `.local` primer:** `.local` names are zero-config LAN hostnames (mDNS, RFC 6762; Apple's brand is "Bonjour"). The OS multicasts "who is `<name>.local`?" on UDP 5353 and the owner replies with its IP — no DNS server or config, and it auto-tracks DHCP changes. It's the same tech behind AirDrop/AirPlay, `printer.local`, Chromecast, NAS boxes, `ssh user@host.local`, etc. **Cross-platform:** any same-network client that speaks mDNS can resolve the Mac's name — macOS, Linux (avahi), iOS/Android, and **Windows 10/11** (built-in resolver; older Windows needs Apple's Bonjour service). So `ping <hostname>.local` works from another laptop, and a request works once resolution + reachability are there — but *this* app additionally requires HTTPS on the configured port, mkcert trust (or `-k`), and a JWT for protected routes (open ones: `/api/hello`, `/auth/*`, `/connections/ping`). Caveat: resolution needs the Wi-Fi to forward mDNS multicast (AP/client isolation can block it even when unicast IP works).

**Keyboard backlight:** Apple Silicon Macs don't respond to traditional key codes (107/113), so `system_controller.set_keyboard_light()` uses Apple's private `CoreBrightness.framework` via `objc.loadBundle()` and the `KeyboardBrightnessClient` class with keyboard ID `1`.

## Patterns & Conventions
- **Blueprint pattern:** Each controller is a Flask Blueprint with `before_request(auth_manager.auth_middleware())`
- **Logging:** `setup_logger()` from `src/utils/logger.py` for code that runs in the main process (rotating file + console, with a handler guard to prevent duplicates). Streaming servers and keyboardMouseController use `logging.getLogger(name)` directly since they may run in subprocesses.
- **macOS commands:** All shell-out uses `subprocess.run()` with arg lists (no `os.system()`, no shell=True) to prevent command injection.
- **Discovery is the OS's job, not the app's.** Don't reintroduce a `python-zeroconf` (or any second mDNS responder) for hostname discovery — macOS already advertises `<hostname>.local`. A second responder on port 5353 wedges iOS resolution (see Last Updated 2026-06-04).
- **Streaming servers:** Run as isolated `multiprocessing.Process` instances, managed by the menu bar app. They have no auth (manually started, local-only by design).
- **Audio resources:** `PyAudio()` is lazy-initialized via `get_pyaudio()` in `alerts.py`; `cleanup_audio()` registered with `atexit` to release on shutdown.
- **Token cleanup:** Temp tokens are cleaned via `cleanup_expired_tokens()` whenever a new one is generated, preventing unbounded growth.
- **Config:** `config.py` at project root, loaded via `app.config.from_pyfile()`. `DEBUG_MODE` reads from env (defaults `false`). Secrets and per-machine config (AUTH_SECRET_KEY, WEB_APP_URL, certs) live in `.env`.
- **CORS:** Origins list filters out `None` so the app starts cleanly even without `WEB_APP_URL` set.
- **Naming:** Snake_case throughout source. The file `keyboardMouseController.py` is camelCase but renaming would break imports — internal identifiers within it follow snake_case.

## Troubleshooting / Operational Gotchas
- **iPhone can't resolve `<hostname>.local` (but the LAN IP works) — RESOLVED 2026-06-04** by deleting the app's own mDNS responder. The app used to run `python-zeroconf` on port 5353 alongside macOS's native Bonjour; its 60-second teardown/rebuild churn (broadcasting a malformed `.local.local` record) wedged iOS's strict resolver until a `killall -HUP mDNSResponder`, and re-wedged on every app restart. macOS Bonjour is now the sole responder, so this can't recur from the app. If `.local` ever fails again it's a **network** issue (mDNS multicast not crossing the Wi-Fi / AP isolation), not the app — confirm the Mac still advertises on the wire with `dig +short -p 5353 @224.0.0.251 <hostname>.local A` (must return the current IP). Note: `dns-sd … | head` block-buffers into pipes and drops answers — use the `dig` one-shot. A `127.0.0.1` answer on interface 1 (loopback) is normal and never leaves the Mac.
- **Command latency / HTTP keep-alive ceiling.** The Flask dev server (`werkzeug/serving.py`) hardcodes `Connection: close` and disables keep-alive, so every command pays a fresh TCP+TLS handshake (~250ms over Wi-Fi); `threaded=True` does **not** change this. Verified options if revisiting: **Cheroot** fixes keep-alive but its `BuiltinSSLAdapter` TLS is **rejected by iOS WebKit** on the SNI/`.local` path (works on IP/desktop/curl — none are valid iOS stand-ins); **Hypercorn** uses stdlib `ssl` (same stack as Werkzeug) and its TLS *is* iOS-compatible (verified with `nscurl`, Apple's stack) with keep-alive working. Any server swap MUST be tested against a real iPhone via the `.local` URL (use `nscurl` on the Mac as a faithful WebKit-stack proxy). Cheroot attempt parked in `git stash`.

## Known Open Items (Hardening)
- **Keep-alive perf (parked, optional).** Per-command latency is the dev server's hardcoded `Connection: close`. Hypercorn is the validated path (stdlib `ssl`, iOS-compatible, keep-alive) if you want to shave the per-command handshake; deprioritized because the value is small. Test on a real iPhone first.
- **Single-instance (minor now).** With the mDNS responder and UDP beacon gone, a second instance just fails to bind port 8080 — no longer wedges discovery. Still cleanest to `pkill -f mac_controller_app` before relaunching.

## Last Updated
2026-06-04 — **Fixed the recurring iOS `.local` wedge by removing the app's mDNS responder.** Deleted `src/services/mdns_service.py` (python-zeroconf + UDP beacon), stripped the duplicated inline mDNS from `run.py`, removed all `MDNSService` usage from `mac_controller_app.py`, and dropped the `zeroconf` dependency (net −256 lines). Root cause: a second mDNS responder on port 5353 (with a 60s rebuild loop and a malformed `.local.local` record) thrashed iOS's resolver; macOS Bonjour already advertises `<hostname>.local` natively, so the responder was pure liability. Verified: `.local` survives repeated app restarts on the iPhone with **no** `killall -HUP mDNSResponder` flush. (Diagnosis cross-checked with Gemini; web app is the only client and the beacon was unused.)

2026-06-03 — Diagnosed the same iOS "can't connect" symptom as a wedged `mDNSResponder` and worked around it with `killall -HUP mDNSResponder` + phone Wi-Fi toggle. Also confirmed (and reverted) that the Flask dev server's hardcoded `Connection: close` causes per-command handshake latency, and that Cheroot's keep-alive fix is rejected by iOS WebKit (parked in git stash). Superseded by the 2026-06-04 root-cause fix above.

2026-06-02 — Fixed QR `serviceUrl` host: `qr_generator.py` no longer doubles the `.local` suffix (the doubled `.local.local` name had no mDNS responder, causing a ~10s cold-resolution timeout that surfaced as multi-second lag on the first command after the client sat idle). Cert regenerated for the single `.local` name.

2026-05-02 — Reflects completion of all 25 audit issues: bug fixes, security hardening (subprocess everywhere, rate limiting, debug-mode env var, removed token leaks, JWT expiry enforced), perf (lazy PyAudio, no save-on-every-request, temp token cleanup), code quality (zero `print()` in src/, unused imports removed, debug methods deleted), keyboard backlight via CoreBrightness, and dependency cleanup (pyobjc trimmed from 160+ to 3 frameworks, deprecated `dotenv` wrapper removed).
