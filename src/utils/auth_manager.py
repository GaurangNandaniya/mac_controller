import jwt
import datetime
import secrets
import os
import json
from functools import wraps
from flask import request, jsonify
from dotenv import load_dotenv
load_dotenv()

# Paths a scoped Apple Watch token (type 'watch') is allowed to hit. Anything not
# matched here is denied (403) for watch tokens. Keep in sync with the controllers:
# media is the whole /media/* blueprint; lock/sleep/capture-and-lock live under /system.
WATCH_ALLOWED_EXACT = {"/system/lock", "/system/sleep", "/system/capture-and-lock"}
WATCH_ALLOWED_PREFIXES = ("/media/",)


def is_watch_path_allowed(path):
    """True if a scoped watch token may access this request path."""
    if path in WATCH_ALLOWED_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in WATCH_ALLOWED_PREFIXES)


class AuthManager:
    def __init__(self, app=None, data_file_path="auth_data.json"):
        self.app = app
        self.data_file_path = data_file_path
        
        # if app is not None:
        #     self.init_app(app)
        self.init_app(app)
    
    def init_app(self, app):
        """Initialize the auth manager with a Flask app"""
        self.app = app
        
        # Get configuration from environment variables with fallbacks
        self.secret_key = os.environ.get('AUTH_SECRET_KEY') or  secrets.token_urlsafe(32)
        self.max_devices = int(os.environ.get('MAX_DEVICES', 5))
        
        # Initialize data structures
        self.temp_tokens = {}  # Stores temp tokens with expiration and metadata
        self.permanent_tokens = {}  # Stores permanent tokens with device info
        self.connected_devices = {}  # Tracks connected devices
        
        # Load persistent data from file
        self.load_data()
    
    def load_data(self):
        """Load persistent data from JSON file"""
        try:
            if os.path.exists(self.data_file_path):
                with open(self.data_file_path, 'r') as f:
                    data = json.load(f)
                    
                    # Convert string dates back to datetime objects
                    for device_id, token_data in data.get('permanent_tokens', {}).items():
                        if 'expires' in token_data:
                            token_data['expires'] = datetime.datetime.fromisoformat(token_data['expires'])
                        if 'created_at' in token_data:
                            token_data['created_at'] = datetime.datetime.fromisoformat(token_data['created_at'])
                    
                    for device_id, device_data in data.get('connected_devices', {}).items():
                        if 'connected_at' in device_data:
                            device_data['connected_at'] = datetime.datetime.fromisoformat(device_data['connected_at'])
                        if 'last_seen' in device_data:
                            device_data['last_seen'] = datetime.datetime.fromisoformat(device_data['last_seen'])
                    
                    self.permanent_tokens = data.get('permanent_tokens', {})
                    self.connected_devices = data.get('connected_devices', {})
                    
                    # Clean up any expired tokens
                    self.cleanup_expired_tokens()
                    
        except Exception as e:
            if self.app:
                self.app.logger.error(f"Error loading auth data: {e}")
            # Initialize empty data structures if loading fails
            self.permanent_tokens = {}
            self.connected_devices = {}
    
    def save_data(self):
        """Save persistent data to JSON file"""
        try:
            # Convert datetime objects to strings for JSON serialization
            data_to_save = {
                'permanent_tokens': {},
                'connected_devices': {}
            }
            
            for device_id, token_data in self.permanent_tokens.items():
                data_to_save['permanent_tokens'][device_id] = token_data.copy()
                if 'expires' in data_to_save['permanent_tokens'][device_id]:
                    data_to_save['permanent_tokens'][device_id]['expires'] = token_data['expires'].isoformat()
                if 'created_at' in data_to_save['permanent_tokens'][device_id]:
                    data_to_save['permanent_tokens'][device_id]['created_at'] = token_data['created_at'].isoformat()
            
            for device_id, device_data in self.connected_devices.items():
                data_to_save['connected_devices'][device_id] = device_data.copy()
                if 'connected_at' in data_to_save['connected_devices'][device_id]:
                    data_to_save['connected_devices'][device_id]['connected_at'] = device_data['connected_at'].isoformat()
                if 'last_seen' in data_to_save['connected_devices'][device_id]:
                    data_to_save['connected_devices'][device_id]['last_seen'] = device_data['last_seen'].isoformat()
            
            with open(self.data_file_path, 'w') as f:
                json.dump(data_to_save, f, indent=2)
                
        except Exception as e:
            if self.app:
                self.app.logger.error(f"Error saving auth data: {e}")
    
    def generate_temp_token(self, device_name="Unknown Device"):
        """Generate a temporary JWT token for QR code authentication"""
        # Clean up expired temp tokens before adding new ones
        self.cleanup_expired_tokens()

        # Create token payload
        payload = {
            'type': 'temp',
            'device_name': device_name,
            'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10),
            'iat': datetime.datetime.now(datetime.timezone.utc),
            'jti': secrets.token_urlsafe(16)  # Unique token ID
        }
        
        # Generate token
        token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        
        # Store token for validation
        self.temp_tokens[payload['jti']] = {
            'token': token,
            'expires': payload['exp'],
            'device_name': device_name,
            'used': False
        }
        return token
    
    def validate_temp_token(self, token):
        """Validate a temporary token and return its payload if valid"""
        try:
            # Decode and verify token
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            
            # Check if token is a temp token
            if payload.get('type') != 'temp':
                return None, "Invalid token type"
                
            # Check if token exists in our store and isn't used
            if payload['jti'] not in self.temp_tokens:
                return None, "Token not found"
                
            if self.temp_tokens[payload['jti']]['used']:
                return None, "Token already used"
                
            # Check if token is expired
            if datetime.datetime.now(datetime.timezone.utc).timestamp() > payload['exp']:
                # Clean up expired token
                del self.temp_tokens[payload['jti']]
                return None, "Token expired"
                
            return payload, None
            
        except jwt.ExpiredSignatureError:
            return None, "Token expired"
        except jwt.InvalidTokenError:
            return None, "Invalid token"
    
    def generate_permanent_token(self, device_id, device_name):
        """Generate a permanent JWT token for a device"""
        # Create token payload
        payload = {
            'type': 'perm',
            'device_id': device_id,
            'device_name': device_name,
            'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30),
            'iat': datetime.datetime.now(datetime.timezone.utc)
        }
        
        # Generate token
        token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        
        # Store token and device info
        self.permanent_tokens[device_id] = {
            'token': token,
            'expires': payload['exp'],
            'device_name': device_name,
            'created_at': datetime.datetime.now(datetime.timezone.utc)
        }
        
        # Track connected device
        self.connected_devices[device_id] = {
            'name': device_name,
            'connected_at': datetime.datetime.now(datetime.timezone.utc),
            'last_seen': datetime.datetime.now(datetime.timezone.utc)
        }
        
        # Save to persistent storage
        self.save_data()

        return token

    def generate_watch_token(self, device_name="Apple Watch", expiry_days=None):
        """Generate a scoped, long-lived token for Apple Watch / Apple Shortcuts.

        - Scope is limited to media + lock/sleep/capture-and-lock (enforced in the
          middleware via is_watch_path_allowed); it cannot drive anything else.
        - expiry_days=None -> no expiry (jwt.decode won't enforce a missing 'exp').
        - Validation is *stateless* (signature + type only): the token is NOT stored
          in permanent_tokens/connected_devices, so 'Revoke All Devices' does not
          affect it. Rotating AUTH_SECRET_KEY is the way to invalidate it.
        """
        payload = {
            'type': 'watch',
            'device_id': 'apple-watch',
            'device_name': device_name,
            'iat': datetime.datetime.now(datetime.timezone.utc),
            'jti': secrets.token_urlsafe(16)
        }
        if expiry_days is not None:
            payload['exp'] = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=expiry_days)

        return jwt.encode(payload, self.secret_key, algorithm='HS256')

    def validate_permanent_token(self, token):
        """Validate a permanent token and return its payload if valid"""
        try:
            # self.load_data()
            # Decode and verify token
            # jwt.decode already validates expiry via the 'exp' claim
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])

            # Scoped Apple Watch token: validity is signature + (optional) expiry,
            # already enforced by jwt.decode above. Intentionally independent of
            # permanent_tokens/connected_devices so 'Revoke All Devices' can't kill
            # it. Endpoint scope is enforced by the caller via is_watch_path_allowed.
            if payload.get('type') == 'watch':
                return payload, None

            # Check if token is a permanent token
            if payload.get('type') != 'perm':
                return None, "Invalid token type"

            # Check if device exists
            device_id = payload.get('device_id')
            if not device_id or device_id not in self.permanent_tokens:
                return None, "Device not registered"

            # Update last seen time (in-memory only — disk saves happen on mutations)
            self.connected_devices[device_id]['last_seen'] = datetime.datetime.now(datetime.timezone.utc)
            
            return payload, None
            
        except jwt.ExpiredSignatureError:
            return None, "Token expired"
        except jwt.InvalidTokenError:
            return None, "Invalid token"

    def can_add_device(self):
        """Check if we can add a new device based on the max devices limit"""
        self.load_data()
        return len(self.connected_devices) < self.max_devices
    
    def revoke_device(self, device_id):
        """Revoke a device's access"""
        if device_id in self.permanent_tokens:
            del self.permanent_tokens[device_id]
        if device_id in self.connected_devices:
            del self.connected_devices[device_id]
        
        # Save to persistent storage
        self.save_data()

    def revoke_all_devices(self):
        """Revoke all device access"""
        self.permanent_tokens = {}
        self.connected_devices = {}
        
        # Save to persistent storage
        self.save_data()
    
    def cleanup_expired_tokens(self):
        """Clean up expired temporary tokens and permanent tokens"""
        now = datetime.datetime.now(datetime.timezone.utc)
        expired_tokens = []
        expired_devices = []
        
        # Clean up temp tokens
        for jti, token_data in self.temp_tokens.items():
            if now > token_data['expires']:
                expired_tokens.append(jti)
        
        for jti in expired_tokens:
            del self.temp_tokens[jti]
        
        # Clean up expired permanent tokens
        for device_id, token_data in self.permanent_tokens.items():
            if now > token_data['expires']:
                expired_devices.append(device_id)
        
        for device_id in expired_devices:
            self.revoke_device(device_id)
    
    def auth_required(self, f):
        """Decorator to require authentication for individual routes"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = request.headers.get('Authorization', '').replace('Bearer ', '')
            
            if not token:
                return jsonify({'error': 'Authorization token required'}), 401
                
            payload, error = self.validate_permanent_token(token)
            if error:
                return jsonify({'error': error}), 401

            # Scoped watch token: only allowed on an explicit path allowlist.
            if payload.get('type') == 'watch' and not is_watch_path_allowed(request.path):
                return jsonify({'error': 'Token not permitted for this endpoint'}), 403

            # Add device info to request context
            request.device_id = payload['device_id']
            request.device_name = payload['device_name']

            return f(*args, **kwargs)
        return decorated_function
    
    def auth_middleware(self):
        """Middleware function that can be used with blueprint.before_request"""
        def middleware():
            # Skip authentication for OPTIONS requests (preflight)
            if request.method == 'OPTIONS':
                return None
                
            # Skip authentication for auth endpoints
            if request.path.startswith('/auth/'):
                return None
                
            token = request.headers.get('Authorization', '').replace('Bearer ', '')
            
            # Fallback to query param token (needed for <img src> tags and direct browser URLs)
            if not token:
                token = request.args.get('token', '')
            
            if not token:
                return jsonify({'error': 'Authorization token required'}), 401
                
            payload, error = self.validate_permanent_token(token)
            if error:
                return jsonify({'error': error}), 401

            # Scoped watch token: only allowed on an explicit path allowlist.
            if payload.get('type') == 'watch' and not is_watch_path_allowed(request.path):
                return jsonify({'error': 'Token not permitted for this endpoint'}), 403

            # Add device info to request context
            request.device_id = payload['device_id']
            request.device_name = payload['device_name']

            return None
        
        return middleware
    
    def get_device_count(self):
        """Get the number of connected devices"""
        return len(self.connected_devices)
    
    def get_device_list(self):
        """Get a list of all connected devices"""
        devices = []
        for device_id, device_info in self.connected_devices.items():
            devices.append({
                'id': device_id,
                'name': device_info['name'],
                'connected_at': device_info['connected_at'].isoformat(),
                'last_seen': device_info['last_seen'].isoformat()
            })
        
        return devices
    


auth_manager = AuthManager()