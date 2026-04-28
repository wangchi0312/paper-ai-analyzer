import logging

_initialized = False


def get_logger(name: str) -> logging.Logger:
    global _initialized
    if not _initialized:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        )
        _initialized = True
    return logging.getLogger(name)
