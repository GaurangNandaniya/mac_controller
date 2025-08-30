from flask import Blueprint, json,render_template,jsonify,request
from ..utils import setup_logger
import io
import base64
import qrcode
from src.utils.auth_manager import auth_manager
import socket
from config import SERVER_PORT
import secrets
from dotenv import load_dotenv
import os
load_dotenv()


logger = setup_logger()

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('qr')
def qr_auth_page():

    """Serve the QR code authentication page"""
    # Generate a temporary token
    temp_token = auth_manager.generate_temp_token()
    
    # Create the connection URL that will be encoded in the QR
    service_name = f"{socket.gethostname()}.local"
    port = SERVER_PORT
    connection_url = f"{os.getenv("WEB_APP_URL")}/connect?token={temp_token}&&serviceUrl=https://{service_name}:{port}"
    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(connection_url)
    qr.make(fit=True)
    
    # Create an image from the QR code
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64 for embedding in HTML
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    # Render the template with the QR code
    return render_template('qr_auth.html', 
                         qr_code=img_str,
                         connection_url=connection_url,
                         server_name=service_name)

@auth_bp.route('/connect', methods=['POST'])
def handle_qr_connection():
    """Handle connection from QR code scan"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    print(f"Received token: {token}")
    if not token:
        return jsonify({'error': 'No token provided'}), 400
    
    # Validate the temporary token
    payload, error = auth_manager.validate_temp_token(token)

    if error:
        return jsonify({'error': error}), 401
    
    # Check if we can add another device
    if not auth_manager.can_add_device():
        return jsonify({
            'error': f'Maximum devices ({auth_manager.max_devices}) already connected'
        }), 400
    
    # Mark temp token as used
    auth_manager.temp_tokens[payload['jti']]['used'] = True
    
    # Generate device ID
    device_id = secrets.token_urlsafe(8)

    requestData = json.loads(request.get_data().decode("utf-8"))

    
    # Generate permanent token
    perm_token = auth_manager.generate_permanent_token(
        device_id, requestData.get('device_name', "Unknown Device")
    )
    
    # Return a success page or redirect to the web app
    return jsonify({"status":"success","token":perm_token})