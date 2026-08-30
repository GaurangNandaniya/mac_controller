"""
/system/vnc_ws — WebSocket <-> TCP bridge to the macOS Screen Sharing server.

Why this exists: a locked Mac's lock screen is drawn by loginwindow in a secure
context. `mss` (running as the logged-in user) captures a black frame there, and
synthetic key events are dropped by Secure Event Input, so the normal screen +
keyboard endpoints cannot unlock the machine. macOS's own `screensharingd` runs
as root and is the one process allowed to render and drive that screen, so the
client talks to it instead — over RFB (VNC) on 127.0.0.1:5900.

This module is a dumb byte pipe: it never parses RFB. Authentication (Apple's
DH-based security type 30) happens end-to-end between the browser's noVNC and
screensharingd, so this bridge never sees the macOS account password.

The socket is JWT-gated via ?token= exactly like mouse_ws/mic_ws/audio_ws.
That gate is the only thing standing between the network and a raw pipe to
port 5900 — do not remove it.
"""
import errno
import select
import socket

from flask import request

from ..utils import setup_logger
from src.utils.auth_manager import auth_manager
from config import VNC_HOST, VNC_PORT

logger = setup_logger()

# One read is capped at this; the pump drains in a loop, so it is a chunk size,
# not a throughput ceiling.
_CHUNK = 65536
# Idle wait when neither side has data. Bounds keystroke latency (imperceptible
# at 10ms) while keeping an idle lock screen off the CPU.
_IDLE_TIMEOUT = 0.01


def register_vnc_ws(sock):
    """Register /system/vnc_ws on a flask_sock Sock instance."""

    @sock.route("/system/vnc_ws")
    def vnc_ws(ws):
        # Auth via ?token= (a browser WebSocket can't set an Authorization header).
        token = request.args.get("token", "")
        _, err = auth_manager.validate_permanent_token(token)
        if err:
            logger.info(f"vnc_ws rejected: {err}")
            return  # closes the socket

        try:
            tcp = socket.create_connection((VNC_HOST, VNC_PORT), timeout=5)
        except OSError as e:
            # Almost always "Screen Sharing is switched off" rather than a bug.
            logger.error(f"vnc_ws could not reach {VNC_HOST}:{VNC_PORT}: {e}")
            return

        tcp.setblocking(False)
        logger.info(f"vnc_ws connected -> {VNC_HOST}:{VNC_PORT}")

        # Single-threaded pump on purpose. simple_websocket fills an input buffer
        # from its own thread, so receive(timeout=0) is a non-blocking queue pop,
        # and with SOCK_SERVER_OPTIONS unset there is no ping_interval — meaning
        # this thread is the only writer to the socket. Two pump threads would
        # race the library's writer for no gain.
        try:
            while True:
                moved = False

                # screensharingd -> browser (framebuffer updates)
                while True:
                    try:
                        chunk = tcp.recv(_CHUNK)
                    except (BlockingIOError, InterruptedError):
                        break
                    except OSError as e:
                        if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                            break
                        raise
                    if not chunk:
                        logger.info("vnc_ws: screen sharing server closed the connection")
                        return
                    ws.send(chunk)  # bytes -> binary frame, which is what noVNC expects
                    moved = True

                # browser -> screensharingd (auth handshake, keys, pointer)
                while True:
                    data = ws.receive(timeout=0)
                    if data is None:
                        break
                    if isinstance(data, str):
                        # RFB is a binary protocol; a text frame means a
                        # misconfigured client, not something to forward.
                        logger.warning("vnc_ws: ignoring unexpected text frame")
                        continue
                    tcp.sendall(data)
                    moved = True

                if not moved:
                    # Nothing pending either way: block until the Mac sends
                    # something or the timeout lets us re-check the browser side.
                    if not ws.connected:
                        break
                    select.select([tcp], [], [], _IDLE_TIMEOUT)
        except Exception as e:
            logger.info(f"vnc_ws closed: {e}")
        finally:
            try:
                tcp.close()
            except Exception:
                pass
            logger.info("vnc_ws disconnected")
