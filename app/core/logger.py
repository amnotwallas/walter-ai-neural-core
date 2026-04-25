import sys
import logging
from logging.handlers import RotatingFileHandler

class ColoredFormatter(logging.Formatter):
    """Custom formatter for colored and concise console output."""
    
    GREY = "\x1b[38;20m"
    BLUE = "\x1b[34;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"
    
    FORMAT = "[%(levelname)s] %(name)s: %(message)s"

    LEVEL_COLORS = {
        logging.DEBUG: GREY,
        logging.INFO: BLUE,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: BOLD_RED
    }

    def format(self, record):
        log_fmt = self.LEVEL_COLORS.get(record.levelno) + self.FORMAT + self.RESET
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

class ServerLogger:
    """Global logging configuration for the server."""
    _initialized = False
    
    @classmethod
    def setup(cls, log_level=logging.INFO, log_file='server.log'):
        if cls._initialized:
            return
            
        logger = logging.getLogger()
        logger.setLevel(log_level)

        if logger.hasHandlers():
            logger.handlers.clear()

        # Silence noisy external libraries
        noisy_loggers = ["httpx", "urllib3", "requests", "uvicorn.access", "uvicorn.error", "groq"]
        for logger_name in noisy_loggers:
            logging.getLogger(logger_name).setLevel(logging.WARNING)

        # Console Handler with ColoredFormatter
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(ColoredFormatter())
        logger.addHandler(console_handler)

        # File Handler - Disabled on Vercel
        import os
        if log_file and os.getenv("VERCEL") != "1":
            try:
                file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
                file_handler.setFormatter(file_formatter)
                logger.addHandler(file_handler)
            except Exception as e:
                # Fallback if file system is still read-only for any reason
                logging.warning(f"Could not initialize file logger: {e}")

        cls._initialized = True
        logging.info("Logging system initialized successfully.")

def get_logger(name: str):
    return logging.getLogger(name)
