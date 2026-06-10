import json
from ..utils import setup_logger
from pynput.mouse import Button, Controller as MouseController
from flask import request
from src.utils.auth_manager import auth_manager

logger = setup_logger()
_mouse = MouseController()
_BUTTONS = {"left": Button.left, "right": Button.right}


def register_mouse_ws(sock):
    """Register the /system/mouse_ws WebSocket on a flask_sock Sock instance."""

    @sock.route("/system/mouse_ws")
    def mouse_ws(ws):
        # Auth via ?token= (a browser WebSocket can't set an Authorization header).
        token = request.args.get("token", "")
        _, err = auth_manager.validate_permanent_token(token)
        if err:
            logger.info(f"mouse_ws rejected: {err}")
            return  # closes the socket

        logger.info("mouse_ws connected")
        while True:
            raw = ws.receive()
            if raw is None:
                break
            try:
                msg = json.loads(raw)
                t = msg.get("t")
                if t == "move":
                    _mouse.move(int(msg.get("dx", 0)), int(msg.get("dy", 0)))
                elif t == "click":
                    _mouse.click(_BUTTONS.get(msg.get("b"), Button.left), 1)
                elif t == "scroll":
                    _mouse.scroll(int(msg.get("dx", 0)), int(msg.get("dy", 0)))
                elif t == "down":
                    _mouse.press(_BUTTONS.get(msg.get("b"), Button.left))
                elif t == "up":
                    _mouse.release(_BUTTONS.get(msg.get("b"), Button.left))
            except Exception as e:
                logger.error(f"mouse_ws message error: {e}")
        logger.info("mouse_ws disconnected")
