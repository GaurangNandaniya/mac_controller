import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logger(name='mac_controller'):
    """
    Basic logger setup karta hai
    Args:
        name: Logger ka naam
    Returns:
        Logger instance
    """
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # File handler (rotating log files)
    file_handler = RotatingFileHandler(
        'logs/mac_controller.log',
        maxBytes=1024 * 1024,  # 1MB
        backupCount=3
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger