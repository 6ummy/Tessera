"""Structured JSON logging via structlog. Routes through stdout for Cloud Run."""

from __future__ import annotations

import logging
import sys

import structlog

from tessera_worker.config import get_settings


def configure_logging() -> None:
    """Call once at process start."""
    s = get_settings()
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, s.log_level.upper(), logging.INFO),
    )
    # Silence third-party request loggers so API keys in URLs never leak to
    # stdout/Sentry. httpx by default logs every request at INFO including the
    # full query string. urllib3 and openai/anthropic have similar habits.
    for noisy in ("httpx", "httpcore", "urllib3", "openai", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, s.log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    # structlog.get_logger returns Any by design (proxy until first bind);
    # the cast documents the concrete type our configure() guarantees.
    from typing import cast
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
