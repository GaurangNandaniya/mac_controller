"""
Windows System Tray Application for Mac/Win Controller (`WinPyCtrlSystemTray`).
Uses `pystray` and `PIL.Image` to provide the exact same functionality as `MacPyCtrlMenuBar`.
"""

import os
import atexit
import signal
import threading
import webbrowser
import multiprocessing
from PIL import Image, ImageDraw
import pystray
from dotenv import load_dotenv

from src.server import create_app
from src.streams.screen_share_server import run_screen_share_server
from src.streams.webrtc_server import run_webrtc_server
from src.streams.audio_server import run_audio_server
from src.utils.socket import get_local_ip
from src.utils.auth_manager import auth_manager
from src.utils.keyboardMouseController import unlock_keyboard, unlock_mouse

load_dotenv()


def global_cleanup():
    """Clean up any active multiprocessing children on interpreter exit."""
    try:
        for process in multiprocessing.active_children():
            try:
                process.terminate()
                process.join(timeout=1.0)
            except Exception:
                pass
    except Exception as e:
        print(f"Global cleanup error: {e}")


atexit.register(global_cleanup)


def run_flask_server():
    """Function to run the Flask server in a separate process."""
    app = create_app()
    print(f"Starting Flask server on {app.config['SERVER_HOST']}:{app.config['SERVER_PORT']}")
    app.run(
        host=app.config['SERVER_HOST'],
        port=app.config['SERVER_PORT'],
        debug=app.config['DEBUG_MODE'],
        use_reloader=False,
        threaded=True,
        ssl_context=(os.getenv("CERTIFICATE_PATH"), os.getenv("PRIVATE_KEY_PATH"))
    )


def _create_tray_icon(color="green"):
    """Create a simple 64x64 colored circle icon for pystray using Pillow."""
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    rgb = (40, 200, 40) if color == "green" else (220, 40, 40)
    dc.ellipse([8, 8, 56, 56], fill=rgb)
    return image


class WinPyCtrlSystemTray:
    """Windows system tray controller app using pystray."""

    def __init__(self):
        self.app = create_app()
        self.auth_obj = auth_manager
        self._stop_event = threading.Event()

        self.server_process = None
        self.is_server_running = False

        self.screen_share_process = None
        self.audio_share_process = None
        self.is_screen_share_running = False

        self.audio_only_process = None
        self.is_audio_only_running = False

        self.webrtc_share_process = None
        self.is_webrtc_share_running = False

        self.status_text = "Stopped"
        try:
            self.ip_text = get_local_ip()
        except Exception:
            self.ip_text = "Unknown"

        self.icon = pystray.Icon(
            "WinPyCtrl",
            icon=_create_tray_icon("red"),
            title="WinPyCtrl - Stopped",
            menu=pystray.Menu(self._build_menu_items)
        )

        atexit.register(self.cleanup)
        try:
            signal.signal(signal.SIGTERM, lambda signum, frame: self.cleanup())
            signal.signal(signal.SIGINT, lambda signum, frame: self.cleanup())
        except Exception:
            pass

        self.auto_start_timer = threading.Timer(1.0, self.start_server_auto)
        self.auto_start_timer.daemon = True
        self.auto_start_timer.start()

        print(f"""
Server running at:
- Local URL: http://{self.ip_text}:{self.app.config['SERVER_PORT']}
- Reachable on local network using Windows mDNS/hostname
        """)

    def _build_menu_items(self):
        return [
            pystray.MenuItem(
                "🟢 Start Server",
                self.start_server,
                enabled=lambda item: not self.is_server_running
            ),
            pystray.MenuItem(
                "🔴 Stop Server",
                self.stop_server,
                enabled=lambda item: self.is_server_running
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("QR Code", self.open_qr_page),
            pystray.MenuItem("📷 Open Camera Test", self.open_camera_test),
            pystray.MenuItem("🖥️ Open Screen Test (Simple)", self.open_screen_test),
            pystray.MenuItem(
                lambda item: "🛑 Stop Screen + Audio Share" if self.is_screen_share_running else "🖥️ Start Screen + Audio Share",
                self.toggle_screen_share
            ),
            pystray.MenuItem(
                lambda item: "🛑 Stop Audio Only Share" if self.is_audio_only_running else "🔊 Start Audio Only Share",
                self.toggle_audio_only
            ),
            pystray.MenuItem(
                lambda item: "🛑 Stop WebRTC Share (Exp.)" if self.is_webrtc_share_running else "🌐 Start WebRTC Share (Exp.)",
                self.toggle_webrtc_share
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(f"ℹ️ Status: {self.status_text}", lambda item: None, enabled=False),
            pystray.MenuItem(f"📡 IP: {self.ip_text}", lambda item: None, enabled=False),
            pystray.MenuItem("Revoke All Devices", self.revoke_all_devices),
            pystray.MenuItem("Quit", self.cleanup)
        ]

    def _update_tray_state(self, status: str, color: str):
        self.status_text = status
        try:
            self.ip_text = get_local_ip()
        except Exception:
            pass
        self.icon.icon = _create_tray_icon(color)
        self.icon.title = f"WinPyCtrl - {status} ({self.ip_text})"
        self.icon.update_menu()

    def start_server_auto(self):
        if not self.is_server_running:
            print("Auto-starting server...")
            self.start_server(None)

    def revoke_all_devices(self, item=None):
        self.auth_obj.revoke_all_devices()
        if self.icon.HAS_NOTIFICATION:
            self.icon.notify("All devices have been revoked.", "WinPyCtrl")

    def open_qr_page(self, item=None):
        webbrowser.open(f"https://localhost:{self.app.config['SERVER_PORT']}/auth/qr")

    def open_camera_test(self, item=None):
        protocol = "https" if os.getenv("CERTIFICATE_PATH") else "http"
        token = self.auth_obj.generate_permanent_token("localhost_test", "Local Test")
        webbrowser.open(f"{protocol}://localhost:{self.app.config['SERVER_PORT']}/system/camera/stream?token={token}")

    def open_screen_test(self, item=None):
        protocol = "https" if os.getenv("CERTIFICATE_PATH") else "http"
        token = self.auth_obj.generate_permanent_token("localhost_test", "Local Test")
        webbrowser.open(f"{protocol}://localhost:{self.app.config['SERVER_PORT']}/system/screen/stream?token={token}")

    def toggle_screen_share(self, item=None):
        if self.is_screen_share_running:
            if self.screen_share_process and self.screen_share_process.is_alive():
                self.screen_share_process.terminate()
                self.screen_share_process.join(timeout=5.0)
                self.screen_share_process = None
            if self.audio_share_process and self.audio_share_process.is_alive():
                self.audio_share_process.terminate()
                self.audio_share_process.join(timeout=5.0)
                self.audio_share_process = None

            self.is_screen_share_running = False
            self.icon.update_menu()
            if self.icon.HAS_NOTIFICATION:
                self.icon.notify("Screen sharing has been stopped", "WinPyCtrl")
        else:
            if self.is_audio_only_running:
                if self.icon.HAS_NOTIFICATION:
                    self.icon.notify("Audio is already streaming via 'Audio Only Share' on port 9092.", "Stop Audio Only first")
                return

            self.screen_share_process = multiprocessing.Process(target=run_screen_share_server)
            self.screen_share_process.daemon = True
            self.screen_share_process.start()

            self.audio_share_process = multiprocessing.Process(target=run_audio_server)
            self.audio_share_process.daemon = True
            self.audio_share_process.start()

            self.is_screen_share_running = True
            self.icon.update_menu()

            share_url = f"http://{self.ip_text}:{self.app.config.get('SCREEN_SHARE_PORT', 9090)}"
            if self.icon.HAS_NOTIFICATION:
                self.icon.notify(f"Share this URL: {share_url}", "Screen Share Started")
            print(f"Screen Share running at: {share_url}")

    def toggle_audio_only(self, item=None):
        if self.is_audio_only_running:
            if self.audio_only_process and self.audio_only_process.is_alive():
                self.audio_only_process.terminate()
                self.audio_only_process.join(timeout=5.0)
                self.audio_only_process = None
            self.is_audio_only_running = False
            self.icon.update_menu()
            if self.icon.HAS_NOTIFICATION:
                self.icon.notify("Audio streaming has been stopped", "WinPyCtrl")
        else:
            if self.is_screen_share_running:
                if self.icon.HAS_NOTIFICATION:
                    self.icon.notify("Audio is already live via 'Screen + Audio Share'.", "Already streaming audio")
                return

            self.audio_only_process = multiprocessing.Process(target=run_audio_server)
            self.audio_only_process.daemon = True
            self.audio_only_process.start()

            self.is_audio_only_running = True
            self.icon.update_menu()

            share_url = f"http://{self.ip_text}:{self.app.config.get('AUDIO_SHARE_PORT', 9092)}"
            if self.icon.HAS_NOTIFICATION:
                self.icon.notify(f"Open and tap to listen: {share_url}", "Audio Only Started")
            print(f"Audio Only running at: {share_url}")

    def toggle_webrtc_share(self, item=None):
        if self.is_webrtc_share_running:
            if self.webrtc_share_process and self.webrtc_share_process.is_alive():
                self.webrtc_share_process.terminate()
                self.webrtc_share_process.join(timeout=5.0)
                self.webrtc_share_process = None
            self.is_webrtc_share_running = False
            self.icon.update_menu()
            if self.icon.HAS_NOTIFICATION:
                self.icon.notify("WebRTC stream has been stopped", "WinPyCtrl")
        else:
            self.webrtc_share_process = multiprocessing.Process(target=run_webrtc_server)
            self.webrtc_share_process.daemon = True
            self.webrtc_share_process.start()

            self.is_webrtc_share_running = True
            self.icon.update_menu()

            share_url = f"http://{self.ip_text}:{self.app.config.get('WEBRTC_SHARE_PORT', 9091)}"
            if self.icon.HAS_NOTIFICATION:
                self.icon.notify(f"Share this URL: {share_url}", "WebRTC Share Started")
            print(f"WebRTC Share running at: {share_url}")

    def start_server(self, item=None):
        if self.is_server_running:
            return
        self._stop_event.clear()
        self.server_process = multiprocessing.Process(target=run_flask_server)
        self.server_process.daemon = True
        self.server_process.start()

        self.is_server_running = True
        self._update_tray_state("Running", "green")
        if self.icon.HAS_NOTIFICATION:
            self.icon.notify(f"Server running at http://{self.ip_text}:{self.app.config['SERVER_PORT']}", "Server Started")

    def stop_server(self, item=None):
        if not self.is_server_running:
            return
        self._stop_event.set()
        if self.server_process and self.server_process.is_alive():
            self.server_process.terminate()
            self.server_process.join(timeout=5.0)
            self.server_process = None

        self.is_server_running = False
        self._update_tray_state("Stopped", "red")
        if self.icon.HAS_NOTIFICATION:
            self.icon.notify("Server has been stopped", "WinPyCtrl")

    def cleanup(self, item=None):
        print("Starting cleanup...")
        unlock_keyboard()
        unlock_mouse()
        self._stop_event.set()

        for proc in [
            self.server_process,
            self.screen_share_process,
            self.audio_share_process,
            self.webrtc_share_process,
            self.audio_only_process,
        ]:
            if proc and proc.is_alive():
                proc.terminate()
                proc.join(timeout=2.0)

        try:
            self.icon.stop()
        except Exception:
            pass
        print("Cleanup completed")

    def run(self):
        """Run the pystray blocking loop."""
        self.icon.run()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    WinPyCtrlSystemTray().run()
