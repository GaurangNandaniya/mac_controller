import socket
import threading
from zeroconf import ServiceInfo, Zeroconf
from src.utils.socket import get_local_ip

# Suppress the specific resource_tracker warning
import warnings
warnings.filterwarnings("ignore", 
                        message="resource_tracker: There appear to be \\d+ leaked semaphore objects to clean up at shutdown",
                        category=UserWarning)

class MDNSService:
    """
    Manages Zero-Configuration Networking (mDNS/UDP Beacons) to allow 
    external web-apps to universally discover the MacBook on a Local Area Network.
    """
    def __init__(self, server_name="MacPyCTRLServer", port=8080):
        self.server_name = server_name
        self.port = port
        self.service_type = "_macpyctrlserver._tcp.local."
        
        self.mdns_zeroconf = None
        self.mdns_service_info = None
        self.mdns_lock = threading.Lock()
        
        self.mdns_refresh_interval = 60
        self._stop_event = threading.Event()
        
        self.mdns_refresh_thread = None
        self.udp_beacon_thread = None

    def start(self):
        self._stop_event.clear()
        self.register_mdns()
        
        # Start beacon thread
        self.udp_beacon_thread = threading.Thread(target=self._start_udp_beacon)
        self.udp_beacon_thread.daemon = True
        self.udp_beacon_thread.start()
        
        # Start refresh thread
        self.mdns_refresh_thread = threading.Thread(target=self._mdns_refresh_loop)
        self.mdns_refresh_thread.daemon = True
        self.mdns_refresh_thread.start()

    def stop(self):
        self._stop_event.set()
        
        if self.mdns_refresh_thread and self.mdns_refresh_thread.is_alive():
            self.mdns_refresh_thread.join(timeout=2.0)
            
        if self.udp_beacon_thread and self.udp_beacon_thread.is_alive():
            self.udp_beacon_thread.join(timeout=2.0)
            
        with self.mdns_lock:
            if self.mdns_zeroconf:
                try:
                    self.mdns_zeroconf.unregister_all_services()
                    self.mdns_zeroconf.close()
                except:
                    pass
                finally:
                    self.mdns_zeroconf = None
                    self.mdns_service_info = None

    def register_mdns(self):
        with self.mdns_lock:
            if self.mdns_zeroconf and self.mdns_service_info:
                try:
                    self.mdns_zeroconf.unregister_service(self.mdns_service_info)
                    self.mdns_zeroconf.close()
                except:
                    pass

            try:
                local_ip = get_local_ip()
                hostname = socket.gethostname()
                
                self.mdns_zeroconf = Zeroconf()
                self.mdns_service_info = ServiceInfo(
                    self.service_type,
                    f"{self.server_name}.{self.service_type}",
                    addresses=[socket.inet_aton(local_ip)],
                    port=self.port,
                    properties={"version": "1.0", "description": "MacPyCtrl Server"},
                    server=f"{hostname}.local",
                )
                
                self.mdns_zeroconf.register_service(self.mdns_service_info, ttl=60, allow_name_change=True)
                print(f"Registered mDNS: {local_ip}:{self.port}")
            except Exception as e:
                print(f"mDNS registration failed: {str(e)}")

    def _mdns_refresh_loop(self):
        while not self._stop_event.is_set():
            try:
                self.register_mdns()
            except Exception as e:
                print(f"Refresh loop error: {str(e)}")
            finally:
                self._stop_event.wait(self.mdns_refresh_interval)

    def _start_udp_beacon(self):
        UDP_PORT = 53535
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1)
            sock.bind(('', UDP_PORT))
            print("UDP beacon started, waiting for discovery requests...")

            while not self._stop_event.is_set():
                try:
                    data, addr = sock.recvfrom(1024)
                    if data.decode().strip() == "DISCOVER_MACBOOK_SERVER":
                        response = f"{get_local_ip()}:{self.port}".encode()
                        sock.sendto(response, addr)
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"UDP Beacon error: {e}")
                    break
        except Exception as e:
            print(f"Failed to start UDP beacon: {e}")
        finally:
            try:
                sock.close()
            except:
                pass
