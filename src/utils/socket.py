import socket

def get_local_ip():
    """Get the local IP address reliably."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # Connect to Google DNS
            return s.getsockname()[0]
    except Exception:
        return socket.gethostbyname(socket.gethostname())  # Fallback to hostname lookup
