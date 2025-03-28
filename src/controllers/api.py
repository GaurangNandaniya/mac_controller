from flask import Blueprint, request
from src.utils import setup_logger

logger = setup_logger()

api_bp = Blueprint('api', __name__)

@api_bp.route('/hello', methods=['POST'])
def ping():
    print(request.get_data())

    return "Hi from mac"