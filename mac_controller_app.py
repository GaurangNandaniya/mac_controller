import threading
import webbrowser
import rumps #https://rumps.readthedocs.io/en/latest/index.html
import atexit
import signal
import warnings
import multiprocessing
from src.server import create_app
from zeroconf import ServiceInfo, Zeroconf
import socket
from src.utils.socket import get_local_ip
from src.utils.auth_manager import auth_manager
from src.utils.keyboardMouseController import unlock_keyboard,unlock_mouse
from dotenv import load_dotenv
import os
load_dotenv()


# Suppress the specific resource_tracker warning
warnings.filterwarnings("ignore", 
                        message="resource_tracker: There appear to be \\d+ leaked semaphore objects to clean up at shutdown",
                        category=UserWarning)

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
        self.app = create_app() #The main reason is to get access to your Flask app's configuration settings:
        self.server_name = "MacPyCTRLServer"
        self.service_type = "_macpyctrlserver._tcp.local."

        #init auth manager for clean up devices
        self.auth_obj = auth_manager

        # mDNS service variables for zero-configuration networking
        self.mdns_zeroconf = None
        self.mdns_service_info = None
        self.mdns_lock = threading.Lock()  # Thread lock for mDNS operations
        self.mdns_refresh_interval = 60    # How often to refresh mDNS registration (seconds)
        self._stop_event = threading.Event()  # Event to signal threads to stop
        
        # Server process management
        self.server_process = None
        self.is_server_running = False
        
        # Background threads
        self.mdns_refresh_thread = None
        self.udp_beacon_thread = None
        
        # Create menu items with keys for easy access
        self.start_item = rumps.MenuItem("🟢 Start Server", callback=self.start_server)
        self.stop_item = rumps.MenuItem("🔴 Stop Server", callback=self.stop_server)
        self.status_item = rumps.MenuItem("ℹ️ Server Status", callback=None)
        self.ip_item = rumps.MenuItem("📡 IP Address", callback=None)
        self.qr_item = rumps.MenuItem("QR Code", callback=self.open_qr_page)
        self.revoke_all = rumps.MenuItem("Revoke All Devices", callback=self.revoke_all_devices)
        self.quit_button_item = rumps.MenuItem("Quit", callback=self.cleanup)

        # Define menu with key-based items
        self.menu = [
            self.start_item,
            self.stop_item,
            None,  # separator
            self.qr_item,
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
- mDNS Name: {self.server_name} (port {self.app.config['SERVER_PORT']})
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

    def register_mdns(self):
        """
        Register the Flask server with mDNS (multicast DNS) for zero-configuration 
        discovery on the local network. This allows other devices to find the server
        by its name without needing to know its IP address.
        """
        with self.mdns_lock:  # Ensure thread-safe access to mDNS resources
            # Unregister existing service if any
            if self.mdns_zeroconf and self.mdns_service_info:
                try:
                    self.mdns_zeroconf.unregister_service(self.mdns_service_info)
                    self.mdns_zeroconf.close()
                except Exception as e:
                    print(f"Error unregistering mDNS: {str(e)}")

            # Get fresh network info and register new service
            try:
                local_ip = get_local_ip()
                self.update_status() # updating IP in menu as well
                hostname = socket.gethostname()
                
                # Create a new Zeroconf instance for service registration
                self.mdns_zeroconf = Zeroconf()

                # Create service information for mDNS registration
                self.mdns_service_info = ServiceInfo(
                    self.service_type,  # Service type
                    f"{self.server_name}.{self.service_type}",  # Service name
                    addresses=[socket.inet_aton(local_ip)],  # IP address
                    port=self.app.config['SERVER_PORT'],  # Server port
                    properties={"version": "1.0", "description": "MacPyCtrl Server"},
                    server=f"{hostname}.local",  # Server hostname
                )
                
                # Register the service with mDNS
                self.mdns_zeroconf.register_service(self.mdns_service_info, ttl=60, allow_name_change=True)
                print(f"Registered mDNS: {local_ip}:{self.app.config['SERVER_PORT']}")
            except Exception as e:
                print(f"mDNS registration failed: {str(e)}")

    def mdns_refresh_loop(self):
        """
        Background thread that periodically refreshes the mDNS registration.
        This ensures the registration stays current even if network conditions change.
        """
        while not self._stop_event.is_set():  # Run until stop event is set
            try:
                self.register_mdns()  # Refresh mDNS registration
            except Exception as e:
                print(f"Refresh loop error: {str(e)}")
            finally:
                # Wait for the interval or until stop event is set
                self._stop_event.wait(self.mdns_refresh_interval)

    def start_udp_beacon(self):
        """
        Start a UDP beacon that listens for discovery requests on the network.
        When a discovery request is received, responds with server information.
        """
        UDP_PORT = 53535  # Custom port for discovery protocol
        try:
            # Create UDP socket for beacon
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1)  # Set timeout to check for stop event regularly
            sock.bind(('', UDP_PORT))
            print("UDP beacon started, waiting for discovery requests...")

            # Main beacon loop
            while not self._stop_event.is_set():
                try:
                    # Wait for discovery requests
                    data, addr = sock.recvfrom(1024)
                    if data.decode().strip() == "DISCOVER_MACBOOK_SERVER":
                        print("Received discovery request from:", addr)
                        # Respond with server IP and port
                        response = f"{get_local_ip()}:{self.app.config['SERVER_PORT']}".encode()
                        sock.sendto(response, addr)
                        print(f"Sent response: {response.decode()}")
                except socket.timeout:
                    continue  # Timeout is expected, just continue
                except Exception as e:
                    print(f"UDP beacon error: {e}")
                    break
        except OSError as e:
            print(f"Failed to start UDP beacon: {e}")
        except Exception as e:
            print(f"UDP beacon error: {e}")
        finally:
            # Ensure socket is closed on exit
            if 'sock' in locals():
                sock.close()

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
        
        # Register with mDNS for network discovery
        self.register_mdns()
        
        # Start mDNS refresh thread to keep registration current
        self.mdns_refresh_thread = threading.Thread(target=self.mdns_refresh_loop, daemon=True)
        self.mdns_refresh_thread.start()
        
        # Start UDP beacon thread for discovery protocol
        self.udp_beacon_thread = threading.Thread(target=self.start_udp_beacon, daemon=True)
        self.udp_beacon_thread.start()
        
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
        
        # Clean up mDNS registration
        self.cleanup_mdns()
        
        # Update UI to reflect stopped state
        self.is_server_running = False
        self.update_status("Stopped", "🔴")
        self.stop_item.set_callback(None)  # Disable stop button
        self.start_item.set_callback(self.start_server)  # Enable start button
        
        # Show notification that server has stopped
        rumps.notification("MacPyCtrl", "Server Stopped", "Server has been stopped")

    def cleanup_mdns(self):
        """
        Clean up mDNS resources by unregistering services and closing connections.
        This ensures no lingering mDNS registrations after the app closes.
        """
        with self.mdns_lock:  # Ensure thread-safe access to mDNS resources
            if self.mdns_zeroconf:
                try:
                    # Unregister all services and close zeroconf connection
                    self.mdns_zeroconf.unregister_all_services()
                    self.mdns_zeroconf.close()
                    print("Cleaned up mDNS services")
                except Exception as e:
                    print(f"Error cleaning up mDNS: {e}")
                finally:
                    self.mdns_zeroconf = None
                    self.mdns_service_info = None


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
        
        # Wait for threads to finish with timeout
        threads_to_join = []
        if hasattr(self, 'mdns_refresh_thread') and self.mdns_refresh_thread and self.mdns_refresh_thread.is_alive():
            threads_to_join.append(self.mdns_refresh_thread)
        if hasattr(self, 'udp_beacon_thread') and self.udp_beacon_thread and self.udp_beacon_thread.is_alive():
            threads_to_join.append(self.udp_beacon_thread)
        
        # Wait for threads with timeout (2 seconds per thread)
        for thread in threads_to_join:
            thread.join(timeout=2.0)
        
        # Clean up mDNS resources
        self.cleanup_mdns()
        rumps.quit_application()
        print("Cleanup completed")

# Entry point when the script is run directly
if __name__ == "__main__":
    # Create and run the menu bar application
    MacPyCtrlMenuBar().run()