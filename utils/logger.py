import logging
import json
import os
from datetime import datetime
from rich.logging import RichHandler

# Set up logs directory inside the workspace
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "name": record.name,
            "filename": record.filename,
            "lineno": record.lineno,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers if already configured
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.DEBUG)
    
    # Console handler using Rich
    console_handler = RichHandler(
        rich_tracebacks=True,
        markup=True,
        show_path=False
    )
    console_handler.setLevel(logging.INFO)
    
    # File handler for JSON structured logs
    json_file_path = os.path.join(LOGS_DIR, "execution.json.log")
    file_handler = logging.FileHandler(json_file_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    
    # Plain text log file handler
    text_file_path = os.path.join(LOGS_DIR, "execution.log")
    text_handler = logging.FileHandler(text_file_path, encoding="utf-8")
    text_handler.setLevel(logging.DEBUG)
    text_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    text_handler.setFormatter(text_formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.addHandler(text_handler)
    
    return logger
