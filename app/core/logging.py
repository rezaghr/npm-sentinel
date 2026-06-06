import logging
import sys

try:
    from pythonjsonlogger.json import JsonFormatter
except ModuleNotFoundError:
    from pythonjsonlogger import jsonlogger

    JsonFormatter = jsonlogger.JsonFormatter

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    formatter = JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s %(service)s"
    )
    handler.setFormatter(formatter)

    root_logger.addHandler(handler)
    root_logger.setLevel(settings.log_level.upper())
