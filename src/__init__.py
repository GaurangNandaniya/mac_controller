from src.server import create_app
from .utils.logger import setup_logger

app = create_app()
# Setup default logger
# logger = setup_logger()

if __name__ == "__main__":
    app.run(
        host=app.config['SERVER_HOST'],
        port=app.config['SERVER_PORT'],
        debug=app.config['DEBUG_MODE']
    )