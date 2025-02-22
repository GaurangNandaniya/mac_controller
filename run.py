from src.server import create_app
from zeroconf import ServiceInfo, Zeroconf, IPVersion
import socket
import threading
import time

app = create_app()
SERVER_TYPE = "_maccontroller._tcp.local."  # Service type must start with _

def get_local_ip():
    """Reliable IP detection that works across different networks"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return socket.gethostbyname(socket.gethostname())

class MDNSController:
    def __init__(self):
        self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        self.service_info = None
        self.running = True
        self.update_interval = 60  # Seconds between IP checks
        
    def register_service(self):
        local_ip = get_local_ip()
        hostname = socket.gethostname()
        
        # Correct service name format: "Instance Name._service._tcp.local."
        service_name = f"{hostname}._maccontroller._tcp.local."
        
        self.service_info = ServiceInfo(
            SERVER_TYPE,
            service_name,
            addresses=[socket.inet_aton(local_ip)],
            port=app.config['SERVER_PORT'],
            properties={"description": "MacBook Controller"},
            server=f"{hostname}.local.",
        )
        
        self.zeroconf.register_service(self.service_info, ttl=10)
        
    def start(self):
        self.register_service()
        threading.Thread(target=self._ip_monitor, daemon=True).start()
        
    def _ip_monitor(self):
        """Periodically check for IP changes"""
        last_ip = get_local_ip()
        while self.running:
            time.sleep(self.update_interval)
            current_ip = get_local_ip()
            if current_ip != last_ip:
                print(f"IP changed from {last_ip} to {current_ip}, updating mDNS...")
                self.zeroconf.unregister_service(self.service_info)
                self.register_service()
                last_ip = current_ip
                
    def shutdown(self):
        self.running = False
        self.zeroconf.unregister_all_services()
        self.zeroconf.close()

if __name__ == "__main__":
    mdns = MDNSController()
    mdns.start()
    
    try:
        print(f"Server running at: http://{get_local_ip()}:{app.config['SERVER_PORT']}")
        app.run(
            host='0.0.0.0',
            port=app.config['SERVER_PORT'],
            debug=app.config['DEBUG_MODE'],
            use_reloader=False
        )
    finally:
        mdns.shutdown()