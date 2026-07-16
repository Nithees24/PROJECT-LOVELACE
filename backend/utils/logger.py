import os
import logging
from logging.handlers import RotatingFileHandler

# Path to the project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

# Create logs directory if it doesn't exist
os.makedirs(LOG_DIR, exist_ok=True)

# Define file paths
ACTIVITY_LOG_PATH = os.path.join(LOG_DIR, "activity.log")
ERRORS_LOG_PATH = os.path.join(LOG_DIR, "errors.log")

# Configure logger
logger = logging.getLogger("lovelace")
logger.setLevel(logging.INFO)

# Avoid adding handlers multiple times if imported/initialized again
if not logger.handlers:
    # Formatter
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s:%(filename)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Activity file handler (logs INFO and above: INFO, WARNING, ERROR, CRITICAL)
    activity_handler = RotatingFileHandler(
        ACTIVITY_LOG_PATH, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
    )
    activity_handler.setLevel(logging.INFO)
    activity_handler.setFormatter(formatter)

    # Errors file handler (logs ERROR and CRITICAL only)
    errors_handler = RotatingFileHandler(
        ERRORS_LOG_PATH, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
    )
    errors_handler.setLevel(logging.ERROR)
    errors_handler.setFormatter(formatter)

    # Console handler (for standard output/stdout)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Add handlers to the logger
    logger.addHandler(activity_handler)
    logger.addHandler(errors_handler)
    logger.addHandler(console_handler)
