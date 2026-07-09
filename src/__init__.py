"""Server package.

Intentionally side-effect free: importing `src` (e.g. `from src.platform_driver
import driver` inside the standalone stream subprocesses) must NOT build the Flask
app. Entry points construct the app explicitly via `src.server.create_app()`
(mac_controller_app.py / win_controller_app.py / run.py). Nothing imports a
module-level `src.app`, so it is not created here.
"""
