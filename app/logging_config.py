"""
Centralized logging and monitoring configuration for the AI MVP application.

This module provides:
- Structured JSON logging with correlation IDs
- Performance monitoring and metrics collection
- Error tracking with context preservation
- Health check endpoints integration
- Environment-specific logging levels
"""

import logging
import logging.config
import os
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, Optional

import structlog
from structlog.typing import FilteringBoundLogger

# Context variables for request correlation
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)


class CorrelationProcessor:
    """Add correlation ID and user context to log records."""

    def __call__(self, logger: FilteringBoundLogger, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        request_id = request_id_var.get()
        user_id = user_id_var.get()

        if request_id:
            event_dict["request_id"] = request_id
        if user_id:
            event_dict["user_id"] = user_id

        return event_dict


class PerformanceMetrics:
    """Collect and track performance metrics."""

    def __init__(self):
        self.request_count = 0
        self.error_count = 0
        self.total_response_time = 0.0
        self.start_time = time.time()

    def record_request(self, response_time: float, status_code: int):
        """Record a request with response time and status."""
        self.request_count += 1
        self.total_response_time += response_time

        if status_code >= 400:
            self.error_count += 1

    def get_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics."""
        uptime = time.time() - self.start_time
        avg_response_time = (
            self.total_response_time / self.request_count
            if self.request_count > 0 else 0
        )

        return {
            "uptime_seconds": uptime,
            "total_requests": self.request_count,
            "total_errors": self.error_count,
            "error_rate": self.error_count / max(self.request_count, 1),
            "average_response_time": avg_response_time,
        }


# Global metrics instance
metrics = PerformanceMetrics()


def setup_logging(
    level: str = "INFO",
    json_logs: bool = True,
    include_timestamp: bool = True,
) -> None:
    """
    Configure structured logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_logs: Whether to output logs in JSON format
        include_timestamp: Whether to include timestamps in logs
    """

    # Determine log level from environment or parameter
    log_level = os.getenv("LOG_LEVEL", level).upper()

    # Configure processors
    processors = [
        structlog.contextvars.merge_contextvars,
        CorrelationProcessor(),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
    ]

    if include_timestamp:
        processors.append(structlog.processors.TimeStamper(fmt="ISO"))

    # Add appropriate renderer based on format preference
    if json_logs and os.getenv("ENVIRONMENT") != "development":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(
            structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
        )

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level)
        ),
        logger_factory=structlog.WriteLoggerFactory(),
        context_class=dict,
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=getattr(logging, log_level),
    )

    # Set third-party logger levels to reduce noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> FilteringBoundLogger:
    """Get a configured logger instance."""
    return structlog.get_logger(name)


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """Set correlation ID for request tracking."""
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    request_id_var.set(correlation_id)
    return correlation_id


def set_user_context(user_id: str) -> None:
    """Set user context for logging."""
    user_id_var.set(user_id)


def clear_context() -> None:
    """Clear logging context variables."""
    request_id_var.set(None)
    user_id_var.set(None)


class LoggerMixin:
    """Mixin class to add logging capabilities to any class."""

    @property
    def logger(self) -> FilteringBoundLogger:
        """Get logger bound with class context."""
        if not hasattr(self, "_logger"):
            self._logger = get_logger(self.__class__.__module__ + "." + self.__class__.__name__)
        return self._logger


def log_exception(
    logger: FilteringBoundLogger,
    exception: Exception,
    context: Optional[Dict[str, Any]] = None,
    level: str = "error"
) -> None:
    """
    Log an exception with full context and traceback.

    Args:
        logger: Logger instance to use
        exception: Exception to log
        context: Additional context to include
        level: Log level to use
    """
    context = context or {}

    log_method = getattr(logger, level)
    log_method(
        "Exception occurred",
        exc_info=exception,
        exception_type=type(exception).__name__,
        exception_message=str(exception),
        **context
    )


def log_performance(
    logger: FilteringBoundLogger,
    operation: str,
    duration: float,
    **kwargs
) -> None:
    """Log performance metrics for an operation."""
    logger.info(
        "Performance metric",
        operation=operation,
        duration_seconds=duration,
        **kwargs
    )


class TimingContext:
    """Context manager for timing operations."""

    def __init__(self, logger: FilteringBoundLogger, operation: str, **context):
        self.logger = logger
        self.operation = operation
        self.context = context
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        self.logger.debug(f"Starting {self.operation}", **self.context)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time

        if exc_type is None:
            log_performance(self.logger, self.operation, duration, **self.context)
        else:
            self.logger.error(
                f"Failed {self.operation}",
                duration_seconds=duration,
                exception_type=exc_type.__name__ if exc_type else None,
                **self.context
            )


def get_health_status() -> Dict[str, Any]:
    """Get application health status including logging metrics."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "metrics": metrics.get_metrics(),
        "logging": {
            "level": logging.root.level,
            "handlers": len(logging.root.handlers),
        }
    }


# Initialize logging on module import
setup_logging()