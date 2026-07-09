"""
Universal Cross-Platform Entry Point for Mac/Win Controller (`app.py`).
Detects the OS at runtime (`darwin` vs `win32`) and launches the appropriate menu/tray runner.
"""

import sys
import multiprocessing
from dotenv import load_dotenv

load_dotenv()


def main():
    if sys.platform == "darwin":
        print("macOS detected (`darwin`). Launching MacPyCtrl menu bar app...")
        from mac_controller_app import MacPyCtrlMenuBar
        MacPyCtrlMenuBar().run()
    elif sys.platform == "win32":
        print("Windows detected (`win32`). Launching WinPyCtrl system tray app...")
        from win_controller_app import WinPyCtrlSystemTray
        WinPyCtrlSystemTray().run()
    else:
        print(f"Unsupported platform: {sys.platform}. Only macOS ('darwin') and Windows ('win32') are supported.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
