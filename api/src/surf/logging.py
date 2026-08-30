"""Structured JSON logging.

structlog is routed through the stdlib logging module on purpose: that is what lets the
same event reach both stdout and an append-only JSONL file. The file is the record a
person -- or an agent helping debug -- reads after the fact (ADR-0007).
"""

import logging
import sys
from pathlib import Path

import structlog


def configure_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    """Emit JSON lines on stdout, and to ``log_file`` when given."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(format="%(message)s", handlers=handlers, level=level.upper(), force=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level.upper()]
        ),
        # route through stdlib so both the stream and file handlers receive events
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
