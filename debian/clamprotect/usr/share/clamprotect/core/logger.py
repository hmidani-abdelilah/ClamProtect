import logging
import logging.handlers
import queue
from pathlib import Path

LOG_DIR = Path.home() / ".local" / "share" / "ClamProtect" / "logs"
LOG_PATH = LOG_DIR / "clamprotect.log"


class Logger:
    _instance = None

    def __new__(cls, name="clamprotect"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, name="clamprotect"):
        if self._initialized:
            return
        self._initialized = True
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()

        file_handler = logging.handlers.RotatingFileHandler(
            str(LOG_PATH), maxBytes=5 * 1024 * 1024, backupCount=3
        )
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s"
        ))
        file_handler.setLevel(logging.DEBUG)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        stream_handler.setLevel(logging.INFO)

        log_queue = queue.Queue(-1)
        queue_handler = logging.handlers.QueueHandler(log_queue)
        self.logger.addHandler(queue_handler)

        self._listener = logging.handlers.QueueListener(
            log_queue, file_handler, stream_handler
        )
        self._listener.start()

    def get(self):
        return self.logger

    def debug(self, msg):
        self.logger.debug(msg)

    def info(self, msg):
        self.logger.info(msg)

    def warning(self, msg):
        self.logger.warning(msg)

    def error(self, msg):
        self.logger.error(msg)

    def stop(self):
        self._listener.stop()


def get_logger():
    return Logger().get()
