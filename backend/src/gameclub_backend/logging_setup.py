import logging
import sys

_STDOUT_HANDLER_MARKER = "_gameclub_stdout_handler"


def configure_stdout_logger(name: str) -> logging.Logger:
    """Send one named application logger to container stdout at INFO level."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(getattr(handler, _STDOUT_HANDLER_MARKER, False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        setattr(handler, _STDOUT_HANDLER_MARKER, True)
        logger.addHandler(handler)
    return logger
