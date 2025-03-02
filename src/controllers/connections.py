from flask import Blueprint,request
from ..utils import setup_logger
from src.utils.socket import get_local_ip

logger = setup_logger()


connections_bp = Blueprint('connections', __name__)

@connections_bp.route("/ping",methods=["POST"])
def ping():
    if request.data.decode("UTF-8")=="MAC_ADDRESS_PING":
        logger.info("MAC Address ping")
        return f"{get_local_ip()}:8080"




