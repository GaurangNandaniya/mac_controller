from src.server import create_app
from zeroconf import ServiceInfo, Zeroconf
import socket
import threading
from src.utils.socket import get_local_ip

app = create_app()
server_name = "maccontroller1.local"

def register_mdns():
    """Register the server using mDNS."""
    local_ip = get_local_ip()
    hostname = socket.gethostname()
    
    # Create zeroconf instance
    zeroconf = Zeroconf()

    # Service information
    service_info = ServiceInfo(
        "_http._tcp.local.",  # Service type
        f"{hostname}._http._tcp.local.",  # Service name
        addresses=[socket.inet_aton(local_ip)],  # IP address
        port=app.config['SERVER_PORT'],  # Port from Flask config
        properties={"version": "1.0", "description": "Test server"},  # Metadata
        server=f"{server_name}.",  # Server name
    )
    
    # Register service
    zeroconf.register_service(service_info, ttl=10, allow_name_change=True)
    print(f"Registered mDNS service: {hostname}._http._tcp.local.")
    return zeroconf

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

if __name__ == "__main__":
    # Register mDNS service
    zeroconf = register_mdns()
    
    # Start UDP beacon in a background thread
    udp_thread = threading.Thread(target=start_udp_beacon, daemon=True)
    udp_thread.start()
    
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
            # use_reloader=False  # Disable Flask's reloader
        )
    except KeyboardInterrupt:
        print("Server stopped by user.")
    finally:
        # Clean up on exit
        zeroconf.unregister_all_services()
        zeroconf.close()
        print("Server stopped, mDNS service unregistered.")