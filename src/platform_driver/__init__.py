"""
Platform isolation module. Auto-detects the operating system (`darwin` vs `win32`)
and exports the singleton `driver` instance implementing `PlatformDriver`.
"""

import sys
import logging
from .base import PlatformDriver

logger = logging.getLogger('platform_driver')

if sys.platform == "darwin":
    from .mac import MacDriver
    driver: PlatformDriver = MacDriver()
    logger.debug("Platform driver initialized: MacDriver")
elif sys.platform == "win32":
    from .win import WinDriver
    driver: PlatformDriver = WinDriver()
    logger.debug("Platform driver initialized: WinDriver")
else:
    raise RuntimeError(f"Unsupported operating system platform: {sys.platform}")

__all__ = ["driver", "PlatformDriver"]
