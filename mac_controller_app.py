import threading
import webbrowser
import rumps
import atexit
from src.server import create_app
from zeroconf import ServiceInfo, Zeroconf
import socket
from src.utils.socket import get_local_ip

class MacPyCtrlMenuBar(rumps.App):
    def __init__(self):
        # super(MacPyCtrlMenuBar, self).__init__("MacPyCtrl", icon="🚀")
        super(MacPyCtrlMenuBar, self).__init__("MacPyCtrl",icon="./icon.jpg")
        
        # Initialize Flask app
        self.app = create_app()
        self.server_name = "MacPyCTRLServer"
        self.service_type = "_macpyctrlserver._tcp.local."
        
        # mDNS variables
        self.mdns_zeroconf = None
        self.mdns_service_info = None
        self.mdns_lock = threading.Lock()
        self.mdns_refresh_interval = 60
        self._stop_event = threading.Event()
        
        # Server process
        self.server_process = None
        self.server_thread = None
        
        # Menu items
        self.menu = [
            rumps.MenuItem("Start Server", callback=self.start_server),
            rumps.MenuItem("Stop Server", callback=self.stop_server),
            None,  # separator
            rumps.MenuItem("Open in Browser", callback=self.open_browser),
            None,  # separator
            rumps.MenuItem("Server Status", callback=None),
            rumps.MenuItem("IP Address", callback=None),
            None,  # separator
            rumps.MenuItem("Quit", callback=self.quit_app)
        ]
        
        # Set initial state
        self.update_status("Stopped", "🔴")
        
        # Register cleanup function
        atexit.register(self.cleanup)
        print("In it done")

    def update_status(self, status, icon=None):
        """Update the menu bar status"""
        if icon:
            self.title = f"{icon}"
        self.menu["Server Status"].title = f"Status: {status}"
        
        try:
            ip = get_local_ip()
            self.menu["IP Address"].title = f"IP: {ip}"
        except:
            self.menu["IP Address"].title = "IP: Unknown"

    def register_mdns(self):
        """Register mDNS service with current IP"""
        with self.mdns_lock:
            # Unregister existing service if any
            if self.mdns_zeroconf and self.mdns_service_info:
                try:
                    self.mdns_zeroconf.unregister_service(self.mdns_service_info)
                    self.mdns_zeroconf.close()
                except Exception as e:
                    print(f"Error unregistering mDNS: {str(e)}")

            # Get fresh network info
            try:
                local_ip = get_local_ip()
                hostname = socket.gethostname()
                
                # Create zeroconf instance
                self.mdns_zeroconf = Zeroconf()

                # Service information
                self.mdns_service_info = ServiceInfo(
                    self.service_type,
                    f"{self.server_name}.{self.service_type}",
                    addresses=[socket.inet_aton(local_ip)],
                    port=self.app.config['SERVER_PORT'],
                    properties={"version": "1.0", "description": "MacPyCtrl Server"},
                    server=f"{hostname}.local.",
                )
                
                # Register service
                self.mdns_zeroconf.register_service(self.mdns_service_info, ttl=60, allow_name_change=True)
                print(f"Registered mDNS: {local_ip}:{self.app.config['SERVER_PORT']}")
            except Exception as e:
                print(f"mDNS registration failed: {str(e)}")

    def mdns_refresh_loop(self):
        """Background thread to refresh mDNS registration"""
        while not self._stop_event.is_set():
            try:
                self.register_mdns()
            except Exception as e:
                print(f"Refresh loop error: {str(e)}")
            finally:
                # Wait for the interval or until stop event is set
                self._stop_event.wait(self.mdns_refresh_interval)

    def start_udp_beacon(self):
        """Start a UDP beacon to respond to discovery requests"""
        UDP_PORT = 53535
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1)  # Set timeout to check for stop event
            sock.bind(('', UDP_PORT))
            print("UDP beacon started, waiting for discovery requests...")

            while not self._stop_event.is_set():
                try:
                    data, addr = sock.recvfrom(1024)
                    if data.decode().strip() == "DISCOVER_MACBOOK_SERVER":
                        print("Received discovery request from:", addr)
                        response = f"{get_local_ip()}:{self.app.config['SERVER_PORT']}".encode()
                        sock.sendto(response, addr)
                        print(f"Sent response: {response.decode()}")
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"UDP beacon error: {e}")
                    break
        except OSError as e:
            print(f"Failed to start UDP beacon: {e}")
        except Exception as e:
            print(f"UDP beacon error: {e}")
        finally:
            if 'sock' in locals():
                sock.close()

    def run_flask_server(self):
        """Run the Flask server"""
        try:
            print(f"Starting Flask server on {self.app.config['SERVER_HOST']}:{self.app.config['SERVER_PORT']}")
            self.app.run(
                host=self.app.config['SERVER_HOST'],
                port=self.app.config['SERVER_PORT'],
                debug=self.app.config['DEBUG_MODE'],
                use_reloader=False
            )
        except Exception as e:
            print(f"Flask server error: {e}")

    def start_server(self, sender):
        """Start the server and all related services"""
        if self.server_process or self.server_thread:
            rumps.alert("Server is already running!")
            return
            
        # Start Flask server in a thread
        self.server_thread = threading.Thread(target=self.run_flask_server, daemon=True)
        self.server_thread.start()
        
        # Start mDNS registration
        self.register_mdns()
        
        # Start mDNS refresh thread
        self.mdns_refresh_thread = threading.Thread(target=self.mdns_refresh_loop, daemon=True)
        self.mdns_refresh_thread.start()
        
        # Start UDP beacon thread
        self.udp_beacon_thread = threading.Thread(target=self.start_udp_beacon, daemon=True)
        self.udp_beacon_thread.start()
        
        # Update UI
        self.update_status("Running", "🟢")
        self.menu["Start Server"].set_callback(None)
        self.menu["Stop Server"].set_callback(self.stop_server)
        
        rumps.notification("MacPyCtrl", "Server Started", 
                          f"Server running at http://{get_local_ip()}:{self.app.config['SERVER_PORT']}")

    def stop_server(self, sender):
        """Stop the server and all related services"""
        # Set stop event to terminate background threads
        self._stop_event.set()
        
        # Clean up mDNS
        self.cleanup_mdns()
        
        # Reset stop event for future use
        self._stop_event.clear()
        
        # Update UI
        self.update_status("Stopped", "🔴")
        self.menu["Stop Server"].set_callback(None)
        self.menu["Start Server"].set_callback(self.start_server)
        
        rumps.notification("MacPyCtrl", "Server Stopped", "Server has been stopped")

    def cleanup_mdns(self):
        """Ensure proper mDNS shutdown"""
        with self.mdns_lock:
            if self.mdns_zeroconf:
                try:
                    self.mdns_zeroconf.unregister_all_services()
                    self.mdns_zeroconf.close()
                    print("Cleaned up mDNS services")
                except Exception as e:
                    print(f"Error cleaning up mDNS: {e}")

    def open_browser(self, sender):
        """Open the server in browser"""
        webbrowser.open(f"http://localhost:{self.app.config['SERVER_PORT']}")

    def cleanup(self):
        """Cleanup on exit"""
        self._stop_event.set()
        self.cleanup_mdns()

    def quit_app(self, sender):
        """Quit the application"""
        self.cleanup()
        rumps.quit_application()

if __name__ == "__main__":
    MacPyCtrlMenuBar().run()