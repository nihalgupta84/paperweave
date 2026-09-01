"""Centralized logging configuration for PaperWeave."""

import logging
import sys


def setup_logging(verbose: bool = False, quiet: bool = False) -> None:
    """Configure the root logger for the corpus_converter package.

    Args:
        verbose: If True, set level to DEBUG.
        quiet: If True, set level to WARNING (suppresses INFO).
    """
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING
    else:
        level = logging.INFO

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    root = logging.getLogger("corpus_converter")
    root.setLevel(level)
    # Avoid duplicate handlers on repeated calls.
    if not root.handlers:
        root.addHandler(handler)
    else:
        root.handlers[0] = handler

    # Suppress noisy third-party loggers.
    for name in ("urllib3", "PIL", "fitz"):
        logging.getLogger(name).setLevel(logging.WARNING)
