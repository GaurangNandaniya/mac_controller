from src.server import create_app
from zeroconf import ServiceInfo, Zeroconf
import socket
import threading
from src.utils.socket import get_local_ip
import time
import atexit

app = create_app()
server_name = "MacPyCTRLServer"  # mDNS server name
service_type = "_macpyctrlserver._tcp.local."

# Global variables for mDNS management
mdns_lock = threading.Lock()
mdns_zeroconf = None
mdns_service_info = None
mdns_refresh_interval = 60  # Seconds between checks

def register_mdns():
    """Register/re-register mDNS service with current IP"""
    global mdns_zeroconf, mdns_service_info
    
    with mdns_lock:

        # Unregister existing service if any
        if mdns_zeroconf and mdns_service_info:
            try:
                mdns_zeroconf.unregister_service(mdns_service_info)
                mdns_zeroconf.close()
            except Exception as e:
                print(f"Error unregistering mDNS: {str(e)}")

        
        # Get fresh network info
        try:
            local_ip = get_local_ip()
            hostname = socket.gethostname()
            
            # Validate server_name matches actual hostname
            if not server_name.startswith(hostname):
                print(f"Warning: Configured server name {server_name} doesn't match hostname {hostname}")

            
            # Create zeroconf instance
            mdns_zeroconf = Zeroconf()

            # Service information
            mdns_service_info = ServiceInfo(
                service_type,  # Service type
                f"{server_name}.{service_type}",  # Service name
                addresses=[socket.inet_aton(local_ip)],  # IP address
                port=app.config['SERVER_PORT'],  # Port from Flask config
                properties={"version": "1.0", "description": "Test server"},  # Metadata
                server=f"{socket.gethostname()}.local.",  # Server name
            )
            
            # Register service
            mdns_zeroconf.register_service(mdns_service_info, ttl=60, allow_name_change=True)
            print(f"Registered mDNS service: {hostname}._http._tcp.local.")
            print(f"Registered mDNS: {local_ip}:{app.config['SERVER_PORT']}")
        except Exception as e:
            print(f"mDNS registration failed: {str(e)}")
    return mdns_zeroconf

def start_udp_beacon():
    """Start a UDP beacon to respond to discovery requests."""
    UDP_PORT = 53535
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(('', UDP_PORT))
        print("UDP beacon started, waiting for discovery requests...")

        while True:
            data, addr = sock.recvfrom(1024)  # Wait for UDP messages
            print(data.decode().strip())
            if data.decode().strip() == "DISCOVER_MACBOOK_SERVER":  # Check for discovery request
                print("Received discovery request from:", addr)
                response = f"{get_local_ip()}:{app.config['SERVER_PORT']}".encode()  # Respond with IP and port
                sock.sendto(response, addr)  # Send response
                print(f"Sent response: {response.decode()}")
    except OSError as e:
        print(f"Failed to start UDP beacon: {e}")
    except Exception as e:
        print(f"UDP beacon error: {e}")
    finally:
        if 'sock' in locals():
            sock.close()

# refresh the service ip on network change periodically 1 min
def mdns_refresh_loop():
    """Background thread with error handling"""
    while True:
        try:
            register_mdns()
        except Exception as e:
            print(f"Refresh loop error: {str(e)}")
        finally:
            time.sleep(mdns_refresh_interval)

def cleanup_mdns():
    """Ensure proper shutdown"""
    with mdns_lock:
        if mdns_zeroconf:
            mdns_zeroconf.unregister_all_services()
            mdns_zeroconf.close()
            print("Cleaned up mDNS services")

if __name__ == "__main__":
    atexit.register(cleanup_mdns)
    # Register mDNS service
    register_mdns()
    
    # Start UDP beacon in a background thread
    # udp_thread = threading.Thread(target=start_udp_beacon, daemon=True)
    # udp_thread.start()

    # Start background thread when initializing your app
    threading.Thread(target=mdns_refresh_loop, daemon=True).start()
    
    try:
        # Start Flask server
        print(f"""
Server running at:
- Local URL: http://{get_local_ip()}:{app.config['SERVER_PORT']}
- mDNS Name: {server_name} (port {app.config['SERVER_PORT']})
        """)
        app.run(
            host=app.config['SERVER_HOST'],
            port=app.config['SERVER_PORT'],
            debug=app.config['DEBUG_MODE'],
            use_reloader=False  # Disable Flask's reloader
        )
    except KeyboardInterrupt:
        print("Server stopped by user.")
    finally:
        # Clean up on exit
        print("Server stopped, mDNS service unregistered.")