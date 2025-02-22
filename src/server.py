from flask import Flask
from src.controllers.media_controller import media_bp
from src.controllers.system_controller import system_bp

def create_app():
    app = Flask(__name__)
    
    # Load config
    app.config.from_pyfile('../config.py')
    
    # Register blueprints
    app.register_blueprint(media_bp, url_prefix='/media')
    app.register_blueprint(system_bp, url_prefix='/system')
    
    return app