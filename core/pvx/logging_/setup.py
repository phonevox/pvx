import logging
from logging.handlers import RotatingFileHandler

from pvx import config


def get_module_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"pvx.{name}")
    if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        logs_dir = config.logs_dir()
        logs_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(logs_dir / f"{name}.log", maxBytes=1_000_000, backupCount=3)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
