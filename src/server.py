from flask import Flask
from src.controllers.media_controller import media_bp
from src.controllers.system_controller import system_bp
from src.controllers.connections import connections_bp
from src.controllers.alerts import alerts_bp
from  src.controllers.api import   api_bp

def create_app():
    app = Flask(__name__)
    
    # Load config
    app.config.from_pyfile('../config.py')
    
    # Register blueprints
    app.register_blueprint(media_bp, url_prefix='/media')
    app.register_blueprint(system_bp, url_prefix='/system')
    app.register_blueprint(connections_bp, url_prefix="/connections")
    app.register_blueprint(alerts_bp, url_prefix="/alerts")
    app.register_blueprint(api_bp, url_prefix="/api")
    
    return app