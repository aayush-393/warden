"""structlog setup. Logs go to stderr (and optionally a file): stdout belongs to the protocol."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import structlog


def configure_logging(level: str = "info", log_file: Path | None = None) -> None:
    numeric = logging.getLevelNamesMapping()[level.upper()]
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.JSONRenderer(),
    ]
    file_handle = log_file.open("a", buffering=1) if log_file else None
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        logger_factory=_TeeLoggerFactory(file_handle),
        cache_logger_on_first_use=False,
    )


class _TeeLogger:
    def __init__(self, file_handle: Any) -> None:
        self._file = file_handle

    def msg(self, message: str) -> None:
        print(message, file=sys.stderr, flush=True)
        if self._file is not None:
            print(message, file=self._file)

    log = debug = info = warning = warn = error = critical = exception = msg


class _TeeLoggerFactory:
    def __init__(self, file_handle: Any) -> None:
        self._file = file_handle

    def __call__(self, *args: Any) -> _TeeLogger:
        return _TeeLogger(self._file)


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)
