import threading
import webbrowser
import rumps #https://rumps.readthedocs.io/en/latest/index.html
import atexit
import signal
import multiprocessing
from src.server import create_app
from src.streams.screen_share_server import run_screen_share_server
from src.streams.webrtc_server import run_webrtc_server
from src.streams.audio_server import run_audio_server
from src.utils.socket import get_local_ip
from src.utils.auth_manager import auth_manager
from src.utils.keyboardMouseController import unlock_keyboard, unlock_mouse
from dotenv import load_dotenv
import os
load_dotenv()

def global_cleanup():
    """
    Global cleanup function registered with atexit.
    This runs when the Python interpreter exits to clean up any remaining resources.
    """
    try:
        import multiprocessing
        # Clean up any multiprocessing processes that might be lingering
        for process in multiprocessing.active_children():
            try:
                process.terminate()
                process.join(timeout=1.0)
            except:
                pass
    except Exception as e:
        print(f"Global cleanup error: {e}")

# Register the global cleanup function to run on exit
atexit.register(global_cleanup)

def run_flask_server():
    """
    Function to run the Flask server in a separate process.
    This isolates the Flask server from the menu bar app.
    """
    # Create a new Flask app instance in this process
    app = create_app()
    
    print(f"Starting Flask server on {app.config['SERVER_HOST']}:{app.config['SERVER_PORT']}")
    
    # Start the Flask development server
    app.run(
        host=app.config['SERVER_HOST'],
        port=app.config['SERVER_PORT'],
        debug=app.config['DEBUG_MODE'],
        use_reloader=False,  # Disable reloader to avoid subprocess issues.
        threaded=True,       # serve the mouse WebSocket alongside HTTP requests
        ssl_context=(os.getenv("CERTIFICATE_PATH"), os.getenv("PRIVATE_KEY_PATH"))
    )

class MacPyCtrlMenuBar(rumps.App):
    """
    Main menu bar application class that controls the Flask server and related services.
    Inherits from rumps.App to create a macOS menu bar application.
    """
    def __init__(self):
        # Initialize the menu bar app with name and icon
        super(MacPyCtrlMenuBar, self).__init__("MacPyCtrl", icon="./icon.jpg", quit_button=None)

        # Initialize Flask application configuration (but don't create the server yet)
        self.app = create_app()
        self.auth_obj = auth_manager
        
        # mDNS is handled natively by macOS (Bonjour advertises <hostname>.local);
        # the app no longer runs its own responder — that second responder churning
        # port 5353 was wedging the phone's .local resolution on restart.
        self._stop_event = threading.Event()  # Event to signal threads to stop
        
        # Server process management
        self.server_process = None
        self.is_server_running = False
        
        # Screen share & Audio process management
        self.screen_share_process = None
        self.audio_share_process = None
        self.is_screen_share_running = False

        # Audio-only share process management (also uses the 9092 audio server)
        self.audio_only_process = None
        self.is_audio_only_running = False

        # WebRTC process management
        self.webrtc_share_process = None
        self.is_webrtc_share_running = False
        
        # Create menu items with keys for easy access
        self.start_item = rumps.MenuItem("🟢 Start Server", callback=self.start_server)
        self.stop_item = rumps.MenuItem("🔴 Stop Server", callback=self.stop_server)
        self.status_item = rumps.MenuItem("ℹ️ Server Status", callback=None)
        self.ip_item = rumps.MenuItem("📡 IP Address", callback=None)
        self.qr_item = rumps.MenuItem("QR Code", callback=self.open_qr_page)
        self.camera_test_item = rumps.MenuItem("📷 Open Camera Test", callback=self.open_camera_test)
        self.screen_test_item = rumps.MenuItem("🖥️ Open Screen Test (Simple)", callback=self.open_screen_test)
        self.screen_share_item = rumps.MenuItem("🖥️ Start Screen + Audio Share", callback=self.toggle_screen_share)
        self.audio_only_item = rumps.MenuItem("🔊 Start Audio Only Share", callback=self.toggle_audio_only)
        self.webrtc_share_item = rumps.MenuItem("🌐 Start WebRTC Share (Exp.)", callback=self.toggle_webrtc_share)
        self.revoke_all = rumps.MenuItem("Revoke All Devices", callback=self.revoke_all_devices)
        self.quit_button_item = rumps.MenuItem("Quit", callback=self.cleanup)

        # Define menu with key-based items
        self.menu = [
            self.start_item,
            self.stop_item,
            None,  # separator
            self.qr_item,
            self.camera_test_item,
            self.screen_test_item,
            self.screen_share_item,
            self.audio_only_item,
            self.webrtc_share_item,
            None,  # separator
            self.status_item,
            self.ip_item,
            self.revoke_all,
            self.quit_button_item
        ]
        
        # Set initial state of the server
        self.update_status("Stopped", "🔴")
        
        # Register instance cleanup method to run on exit
        atexit.register(self.cleanup)
        # Register signal handlers for graceful shutdown on SIGTERM and SIGINT
        signal.signal(signal.SIGTERM, lambda signum, frame: self.cleanup())
        signal.signal(signal.SIGINT, lambda signum, frame: self.cleanup())
        # Auto-start the server when the app launches
        # Use a small delay to ensure the menu bar is fully initialized
        self.auto_start_timer = threading.Timer(1.0, self.start_server_auto)
        self.auto_start_timer.daemon = True
        self.auto_start_timer.start()
        print(f"""
Server running at:
- Local URL: http://{get_local_ip()}:{self.app.config['SERVER_PORT']}
- Reachable at <hostname>.local via macOS Bonjour (no app-level mDNS)
        """)
    def revoke_all_devices(self, sender):
        """Revoke all connected devices"""
        self.auth_obj.revoke_all_devices()
        rumps.alert("All devices have been revoked.")

    def start_server_auto(self):
        """
        Auto-start the server when the app launches.
        This is called with a slight delay to ensure the menu bar is fully initialized.
        """
        # Check if server is already running (shouldn't be, but just in case)
        if not self.is_server_running:
            print("Auto-starting server...")
            # Call start_server with None as sender since it's auto-start, not user-initiated
            self.start_server(None)        

    def open_qr_page(self, sender):
        """Open the QR authentication page in browser"""
        webbrowser.open(f"https://localhost:{self.app.config['SERVER_PORT']}/auth/qr")

    def open_camera_test(self, sender):
        """Open the camera stream page in browser for local testing"""
        protocol = "https" if os.getenv("CERTIFICATE_PATH") else "http"
        token = self.auth_obj.generate_permanent_token("localhost_test", "Local Test")
        webbrowser.open(f"{protocol}://localhost:{self.app.config['SERVER_PORT']}/system/camera/stream?token={token}")

    def open_screen_test(self, sender):
        """Open the simple screen stream page in browser for local testing"""
        protocol = "https" if os.getenv("CERTIFICATE_PATH") else "http"
        token = self.auth_obj.generate_permanent_token("localhost_test", "Local Test")
        webbrowser.open(f"{protocol}://localhost:{self.app.config['SERVER_PORT']}/system/screen/stream?token={token}")

    def toggle_screen_share(self, sender):
        """Start or stop the dedicated screen share server and its paired audio server."""
        if self.is_screen_share_running:
            # Stop screen share
            if self.screen_share_process and self.screen_share_process.is_alive():
                self.screen_share_process.terminate()
                self.screen_share_process.join(timeout=5.0)
                self.screen_share_process = None
                
            # Stop audio share
            if self.audio_share_process and self.audio_share_process.is_alive():
                self.audio_share_process.terminate()
                self.audio_share_process.join(timeout=5.0)
                self.audio_share_process = None
            
            self.is_screen_share_running = False
            self.screen_share_item.title = "🖥️ Start Screen + Audio Share"
            rumps.notification("MacPyCtrl", "Screen Share Stopped", "Screen sharing has been stopped")
        else:
            # Guard: the 9092 audio server can't run twice — Audio-Only uses the same port.
            if self.is_audio_only_running:
                rumps.notification("MacPyCtrl", "Stop Audio Only first",
                                   "Audio is already streaming via 'Audio Only Share' on port 9092.")
                return

            # Start screen share video
            self.screen_share_process = multiprocessing.Process(target=run_screen_share_server)
            self.screen_share_process.daemon = True
            self.screen_share_process.start()
            
            # Start screen share audio
            self.audio_share_process = multiprocessing.Process(target=run_audio_server)
            self.audio_share_process.daemon = True
            self.audio_share_process.start()
            
            self.is_screen_share_running = True
            self.screen_share_item.title = "🛑 Stop Screen + Audio Share"
            
            share_url = f"http://{get_local_ip()}:{self.app.config.get('SCREEN_SHARE_PORT', 9090)}"
            rumps.notification("MacPyCtrl", "Screen Share Started",
                              f"Share this URL: {share_url}")
            print(f"Screen Share running at: {share_url}")

    def toggle_audio_only(self, sender):
        """Start or stop audio-only streaming (system audio over WebSocket on port 9092)."""
        if self.is_audio_only_running:
            if self.audio_only_process and self.audio_only_process.is_alive():
                self.audio_only_process.terminate()
                self.audio_only_process.join(timeout=5.0)
                self.audio_only_process = None
            self.is_audio_only_running = False
            self.audio_only_item.title = "🔊 Start Audio Only Share"
            rumps.notification("MacPyCtrl", "Audio Only Stopped", "Audio streaming has been stopped")
        else:
            # Guard: the 9092 audio server is also used by Screen + Audio Share.
            if self.is_screen_share_running:
                rumps.notification("MacPyCtrl", "Already streaming audio",
                                   "Audio is already live via 'Screen + Audio Share'.")
                return

            self.audio_only_process = multiprocessing.Process(target=run_audio_server)
            self.audio_only_process.daemon = True
            self.audio_only_process.start()

            self.is_audio_only_running = True
            self.audio_only_item.title = "🛑 Stop Audio Only Share"

            share_url = f"http://{get_local_ip()}:{self.app.config.get('AUDIO_SHARE_PORT', 9092)}"
            rumps.notification("MacPyCtrl", "Audio Only Started",
                               f"Open and tap to listen: {share_url}")
            print(f"Audio Only running at: {share_url}")

    def toggle_webrtc_share(self, sender):
        """Start or stop the experimental WebRTC share server."""
        if self.is_webrtc_share_running:
            # Stop WebRTC share
            if self.webrtc_share_process and self.webrtc_share_process.is_alive():
                self.webrtc_share_process.terminate()
                self.webrtc_share_process.join(timeout=5.0)
                self.webrtc_share_process = None
            
            self.is_webrtc_share_running = False
            self.webrtc_share_item.title = "🌐 Start WebRTC Share (Exp.)"
            rumps.notification("MacPyCtrl", "WebRTC Share Stopped", "WebRTC stream has been stopped")
        else:
            # Start WebRTC share
            self.webrtc_share_process = multiprocessing.Process(target=run_webrtc_server)
            self.webrtc_share_process.daemon = True
            self.webrtc_share_process.start()
            
            self.is_webrtc_share_running = True
            self.webrtc_share_item.title = "🛑 Stop WebRTC Share (Exp.)"
            
            share_url = f"http://{get_local_ip()}:{self.app.config.get('WEBRTC_SHARE_PORT', 9091)}"
            rumps.notification("MacPyCtrl", "WebRTC Share Started",
                              f"Share this URL: {share_url}")
            print(f"WebRTC Share running at: {share_url}")

    def update_status(self, status=None, icon=None):
        """
        Update the menu bar status display and information items.
        
        Args:
            status (str): Text description of server status
            icon (str, optional): Icon to display in menu bar. Defaults to None.
        """
        if icon:
            self.title = f"{icon}"  # Set menu bar icon
        
        # Update status item using key-based access
        if status:
            self.status_item.title = f"ℹ️ Status: {status}"
        
        try:
            # Try to get and display the current IP address
            ip = get_local_ip()
            self.ip_item.title = f"📡 IP: {ip}"
        except Exception:
            # Fallback if IP address can't be determined
            self.ip_item.title = "📡 IP: Unknown"


    def start_server(self, sender):
        """
        Start the server and all related services.
        Called when the user selects "Start Server" from the menu.
        
        Args:
            sender: The menu item that triggered this action (not used)
        """
        if self.is_server_running:
            rumps.alert("Server is already running!")
            return
            
        # Reset stop event
        self._stop_event.clear()
        
        # Start Flask server in a separate process
        self.server_process = multiprocessing.Process(target=run_flask_server)
        self.server_process.daemon = True  # Make it a daemon so it exits with main process
        self.server_process.start()
        
        # Update UI to reflect running state
        self.is_server_running = True
        self.update_status("Running", "🟢")
        self.start_item.set_callback(None)  # Disable start button
        self.stop_item.set_callback(self.stop_server)  # Enable stop button

        # Show notification that server has started
        rumps.notification("MacPyCtrl", "Server Started", 
                          f"Server running at http://{get_local_ip()}:{self.app.config['SERVER_PORT']}")

    def stop_server(self, sender):
        """
        Stop the server and all related services.
        Called when the user selects "Stop Server" from the menu.
        
        Args:
            sender: The menu item that triggered this action (not used)
        """
        if not self.is_server_running:
            rumps.alert("Server is not running!")
            return
                
        # Signal all threads to stop
        self._stop_event.set()
        
        # Terminate the Flask server process
        if self.server_process and self.server_process.is_alive():
            self.server_process.terminate()
            self.server_process.join(timeout=5.0)  # Wait for process to terminate
            self.server_process = None
        
        # Update UI to reflect stopped state
        self.is_server_running = False
        self.update_status("Stopped", "🔴")
        self.stop_item.set_callback(None)  # Disable stop button
        self.start_item.set_callback(self.start_server)  # Enable start button
        rumps.notification("MacPyCtrl", "Server Stopped", "Server has been stopped")


    def cleanup(self,sender):
        """
        Comprehensive cleanup method that stops all services and threads.
        This method is called automatically when the app exits.
        """
        print("Starting cleanup...")
        unlock_keyboard()  # Ensure keyboard is unlocked when server stops
        unlock_mouse()  # Ensure mouse is unlocked when server stops
        # Signal all threads to stop
        self._stop_event.set()
        
        # Terminate the Flask server process if it's still running
        if self.server_process and self.server_process.is_alive():
            self.server_process.terminate()
            self.server_process.join(timeout=2.0)
        
        # Terminate the screen share server if running
        if self.screen_share_process and self.screen_share_process.is_alive():
            self.screen_share_process.terminate()
            self.screen_share_process.join(timeout=2.0)
            
        # Terminate the audio server if running
        if self.audio_share_process and self.audio_share_process.is_alive():
            self.audio_share_process.terminate()
            self.audio_share_process.join(timeout=2.0)
            
        # Terminate the WebRTC share server if running
        if self.webrtc_share_process and self.webrtc_share_process.is_alive():
            self.webrtc_share_process.terminate()
            self.webrtc_share_process.join(timeout=2.0)

        # Terminate the audio-only server if running
        if self.audio_only_process and self.audio_only_process.is_alive():
            self.audio_only_process.terminate()
            self.audio_only_process.join(timeout=2.0)

        rumps.quit_application()
        print("Cleanup completed")

# Entry point when the script is run directly
if __name__ == "__main__":
    # Create and run the menu bar application
    MacPyCtrlMenuBar().run()