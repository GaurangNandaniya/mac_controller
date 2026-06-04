# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A macOS remote-control server that lets a phone/web client control a MacBook over the local network (media, volume, brightness, keyboard backlight, screen/camera/audio streaming, keyboard-mouse lock, and a "capture-and-lock" intruder defense). It runs as a menu bar app, pairs clients via QR + JWT, and advertises itself over mDNS. The companion client lives in a separate repo (`mac-control-web-app`).

There is a deeper architectural reference in **`CODEBASE_MAP.md`** — read it for module-by-module detail, the auth/discovery flow internals, and the rationale behind macOS-specific workarounds. This file is the quick-start; that file is the map.

## Commands

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run (primary): menu bar app — auto-starts HTTPS server + mDNS, spawns stream processes
python3 mac_controller_app.py

# Run (legacy): standalone Flask + mDNS, no menu bar
python3 run.py

# Production-style start (used by the Automator/login-item wrapper)
./start_mac_controller_server.sh   # requires `export macControllerDirPath=<repo path>`

# Debug logging
DEBUG_MODE=true python3 mac_controller_app.py
```

There is **no test suite or linter configured**. `test.py` is a throwaway pyttsx3 voice-exploration script, not a test — do not treat it as one.

HTTPS is mandatory: the server won't serve without mkcert-generated certs whose paths are set in `.env`. See `readme.md` for the mkcert + iPhone trust-profile setup.

## Required environment (`.env`, git-ignored)

`AUTH_SECRET_KEY` (JWT signing), `MAX_DEVICES`, `WEB_APP_URL` (CORS origin for the deployed PWA), `CERTIFICATE_PATH`, `PRIVATE_KEY_PATH`. The app starts cleanly if `WEB_APP_URL` is unset (the CORS list filters out `None`), but auth and TLS require the secret key and certs.

## Architecture (the big picture)

**Two implementations exist; only Python is active.** `mac_controller_rust/` is an experimental Actix port — do not assume changes there affect runtime behavior.

**Entry point → Flask factory → blueprints.** `mac_controller_app.py` (rumps menu bar) is the real entry point. It calls `create_app()` in `src/server.py`, which wires CORS and registers 7 Flask blueprints from `src/controllers/`. Every blueprint gates requests through `auth_manager.auth_middleware()` (a shared singleton in `src/utils/auth_manager.py`). Understanding any request means reading: the blueprint → the auth middleware → `config.py`. `run.py` duplicates the mDNS/server bootstrap for headless use — **changes to startup logic usually need to be mirrored in both.**

**Streaming runs out-of-process.** The MJPEG screen share (9090), WebRTC (9091), and system-audio (9092) servers in `src/streams/` are launched as separate `multiprocessing.Process` instances by the menu bar app. They are intentionally **unauthenticated and local-only** (manually started, not part of the JWT-gated Flask app). Ports and stream params live in `config.py`. System-audio capture depends on a BlackHole loopback device.

**Auth is a two-token QR flow.** `/auth/qr` issues a short-lived temp JWT inside a QR code; the client POSTs it to `/auth/connect` (rate-limited 10/min/IP) to exchange for a 30-day permanent JWT. Expiry is enforced natively by `jwt.decode()`. The QR's embedded `serviceUrl` uses the host's single `.local` mDNS name — see `CODEBASE_MAP.md` for why the `.local` suffix must not be doubled.

**Discovery has three layers:** mDNS service `_macpyctrlserver._tcp.local.` (via `src/services/mdns_service.py`), a UDP beacon on port 53535 answering `DISCOVER_MACBOOK_SERVER`, and an HTTP `/connections/ping` fallback.

## Conventions to follow

- **Never shell out via `os.system` or `shell=True`.** All macOS commands use `subprocess.run()` with argument lists — this is a deliberate command-injection guard; keep it.
- **Logging, not `print`.** Code in the main process uses `setup_logger()` from `src/utils/logger.py`. Code that may run in a subprocess (streams, `mdns_service`, `keyboardMouseController`) uses `logging.getLogger(__name__)` directly. `src/` should contain zero `print()` calls.
- **macOS-specific quirks are intentional.** Keyboard backlight on Apple Silicon goes through Apple's private `CoreBrightness.framework` loaded at runtime (legacy key codes don't work). Don't "simplify" these into standard APIs without testing on Apple Silicon.
- **Naming:** snake_case everywhere. `keyboardMouseController.py` is the lone camelCase filename — leave it; renaming breaks imports. Identifiers inside it are still snake_case.
- **Dependencies are deliberately minimal.** pyobjc is pinned to only 3 frameworks (Cocoa, Quartz, ApplicationServices) — don't pull in the full pyobjc meta-package.

## Self-Update Protocol

Claude Code has a built-in learnings loop — **auto memory** (on by default, Claude-written, machine-local) under `~/.claude/projects/<project>/memory/`, browsable with `/memory`. Don't build a parallel system; treat auto memory as the fast first-capture tier and **promote** durable learnings up so git and teammates inherit them. One home per fact — when you promote, remove the copy; never duplicate across tiers.

1. **Auto memory** (`/memory`; machine-local, *not* in git) — discovered build/debug/preference notes Claude jots mid-session. Cheap and automatic.
2. **Committed project knowledge → `CODEBASE_MAP.md`** — promote a learning here once it's durable and worth sharing (a real gotcha, a dead-end not to repeat, a fragile area). This is the team-visible, version-controlled tier:
   - a fix or trap → *Troubleshooting / Operational Gotchas*
   - unfinished or risky work → *Known Open Items*
   - what changed and why → *Last Updated*
3. **Cross-project / methodology lessons → global `~/.claude/CLAUDE.md` *Learned Rules***, not here. Mixing scopes dilutes both.

This is what stops a future session re-walking a dead end (e.g. re-chasing a keep-alive server swap when mDNS is the actually-fragile layer).

**Entry standards** — lean prompt-additives, not prose: *atomic* (one insight per bullet), *dated* `[YYYY-MM-DD]`, *specific & actionable* ("Cheroot's `BuiltinSSLAdapter` fails iOS WebKit on the SNI/`.local` path; use a stdlib-`ssl` server" beats "be careful with TLS"), *append-or-correct-with-a-dated-note* — never silently overwrite.

**Keep it lean** (CLAUDE.md adherence drops past ~200 lines; bloated files get skipped): consolidate periodically — drop superseded or contradicting entries, merge duplicates, and promote a recurring gotcha into *Patterns & Conventions* as a standing rule.

<!-- Maintainer note (stripped from Claude's context): these docs are guidance, not enforced. For a hard end-of-session trigger, add a Stop/PreCompact hook that prompts a reflection — see the update-config skill. -->
