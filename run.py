from src.server import create_app
from src.utils.socket import get_local_ip

app = create_app()

# Legacy standalone entry point (the menu-bar app `mac_controller_app.py` is primary).
# No app-level mDNS: macOS advertises <hostname>.local natively via Bonjour. Running a
# second responder (python-zeroconf) here churned port 5353 and wedged .local resolution
# on the phone, so it was removed.

if __name__ == "__main__":
    print(f"""
Server running at:
- Local URL: http://{get_local_ip()}:{app.config['SERVER_PORT']}
- Reachable at <hostname>.local via macOS Bonjour
        """)
    try:
        app.run(
            host=app.config['SERVER_HOST'],
            port=app.config['SERVER_PORT'],
            debug=app.config['DEBUG_MODE'],
            use_reloader=False,  # Disable Flask's reloader
        )
    except KeyboardInterrupt:
        print("Server stopped by user.")
