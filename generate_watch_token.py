"""Mint a scoped, no-expiry Apple Watch token for use in Apple Shortcuts.

Run from the server folder:

    ./venv/bin/python generate_watch_token.py

The printed token is validated statelessly (by JWT signature), so it works against
the already-running server without a restart, and it survives "Revoke All Devices".

Scope is limited to: media (/media/*), /system/lock, /system/sleep,
/system/capture-and-lock. Anything else returns 403.

To invalidate it later, rotate AUTH_SECRET_KEY in .env (note: that also unpairs
all phones and requires re-scanning the QR).
"""
from src.utils.auth_manager import auth_manager


def main():
    token = auth_manager.generate_watch_token(device_name="Apple Watch", expiry_days=None)

    print("\nApple Watch token (no expiry):\n")
    print(token)
    print("\nUse it in Apple Shortcuts via a 'Get Contents of URL' action:")
    print("  Method:  POST")
    print("  URL:     https://<your-mac>.local:8080/media/play-pause")
    print("  Header:  Authorization: Bearer <token above>")
    print("\nAllowed endpoints:")
    print("  POST /media/*                  (play-pause, next, previous, volume-up,")
    print("                                  volume-down, volume-set/<level>, mute, arrows)")
    print("  POST /system/lock")
    print("  POST /system/sleep")
    print("  POST /system/capture-and-lock")
    print()


if __name__ == "__main__":
    main()
