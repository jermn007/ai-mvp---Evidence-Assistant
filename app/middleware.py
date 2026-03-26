"""
FastAPI middleware for logging, monitoring, and security.

This module provides:
- Request/response logging with correlation IDs
- Performance monitoring and metrics collection
- Error handling and reporting
- Security headers and rate limiting
- Health check endpoints
"""

import time
from typing import Callable, Optional
from uuid import uuid4

from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from .logging_config import (
    get_logger,
    set_correlation_id,
    clear_context,
    log_exception,
    metrics,
    get_health_status,
)
from .validation import create_validation_middleware


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request/response logging and correlation tracking."""

    def __init__(self, app: FastAPI, exclude_paths: Optional[set] = None):
        super().__init__(app)
        self.logger = get_logger("middleware.logging")
        self.exclude_paths = exclude_paths or {"/health", "/metrics", "/favicon.ico"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip logging for health checks and static assets
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Set correlation ID for this request
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())
        set_correlation_id(correlation_id)

        # Start timing
        start_time = time.time()

        # Log request details
        self.logger.info(
            "Request started",
            method=request.method,
            path=request.url.path,
            query_params=str(request.query_params),
            user_agent=request.headers.get("user-agent"),
            client_ip=request.client.host if request.client else None,
        )

        try:
            response = await call_next(request)

            # Calculate timing
            process_time = time.time() - start_time

            # Record metrics
            metrics.record_request(process_time, response.status_code)

            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Process-Time"] = str(process_time)

            # Log response
            self.logger.info(
                "Request completed",
                status_code=response.status_code,
                process_time=process_time,
                response_size=response.headers.get("content-length"),
            )

            return response

        except Exception as exc:
            # Calculate timing for failed requests
            process_time = time.time() - start_time

            # Record error metrics
            metrics.record_request(process_time, 500)

            # Log the exception
            log_exception(
                self.logger,
                exc,
                context={
                    "method": request.method,
                    "path": request.url.path,
                    "process_time": process_time,
                }
            )

            # Return structured error response
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "correlation_id": correlation_id,
                    "details": str(exc) if hasattr(exc, '__str__') else "Unknown error"
                },
                headers={"X-Correlation-ID": correlation_id}
            )

        finally:
            # Clear context for next request
            clear_context()


class SecurityMiddleware(BaseHTTPMiddleware):
    """Middleware for security headers and basic protection."""

    def __init__(self, app: FastAPI):
        super().__init__(app)
        self.logger = get_logger("middleware.security")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Add security headers
        response.headers.update({
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": "default-src 'self'",
        })

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enhanced rate limiting middleware with different limits per endpoint type."""

    def __init__(self, app: FastAPI,
                 default_requests_per_minute: int = 1000,
                 strict_requests_per_minute: int = 200):
        super().__init__(app)
        self.logger = get_logger("middleware.ratelimit")
        self.default_limit = default_requests_per_minute
        self.strict_limit = strict_requests_per_minute
        self.request_counts = {}
        self.blocked_ips = {}  # Track temporarily blocked IPs
        self.last_reset = time.time()

        # Define endpoints that need stricter rate limiting
        # Note: /runs/ endpoints (like /runs/{id}/status) use default limits for better polling
        self.strict_endpoints = {
            '/run/press', '/ai/', '/test/'
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        current_time = time.time()

        # Reset counters every minute
        if current_time - self.last_reset > 60:
            self.request_counts.clear()
            # Clean up blocked IPs that have been blocked for more than 5 minutes
            self.blocked_ips = {
                ip: block_time for ip, block_time in self.blocked_ips.items()
                if current_time - block_time < 300
            }
            self.last_reset = current_time

        # Get client identifier (prefer X-Forwarded-For if behind proxy)
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.client.host if request.client else "unknown"

        # Check if IP is temporarily blocked
        if client_ip in self.blocked_ips:
            block_time = self.blocked_ips[client_ip]
            if current_time - block_time < 300:  # 5 minute block
                self.logger.warning("Blocked IP attempted access", client_ip=client_ip)
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "IP temporarily blocked due to excessive requests",
                        "retry_after": 300 - (current_time - block_time),
                        "blocked_until": block_time + 300
                    }
                )

        # Determine rate limit based on endpoint
        path = request.url.path
        is_strict_endpoint = any(path.startswith(strict_path) for strict_path in self.strict_endpoints)
        limit = self.strict_limit if is_strict_endpoint else self.default_limit

        # Track requests by IP and endpoint type
        key = f"{client_ip}:{'strict' if is_strict_endpoint else 'default'}"
        current_count = self.request_counts.get(key, 0)

        if current_count >= limit:
            # Block IP after excessive requests
            self.blocked_ips[client_ip] = current_time

            self.logger.warning(
                "Rate limit exceeded - IP blocked",
                client_ip=client_ip,
                current_count=current_count,
                limit=limit,
                endpoint_type="strict" if is_strict_endpoint else "default",
                path=path
            )

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "limit": limit,
                    "endpoint_type": "strict" if is_strict_endpoint else "default",
                    "reset_in": 60 - (current_time - self.last_reset),
                    "ip_blocked": True,
                    "block_duration": 300
                }
            )

        # Increment counter
        self.request_counts[key] = current_count + 1

        return await call_next(request)


def add_health_endpoints(app: FastAPI) -> None:
    """Add health check and metrics endpoints."""

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return get_health_status()

    @app.get("/metrics")
    async def get_metrics():
        """Metrics endpoint for monitoring."""
        return {
            "performance": metrics.get_metrics(),
            "timestamp": time.time(),
        }

    @app.get("/health/ready")
    async def readiness_check():
        """Readiness check for container orchestration."""
        try:
            # Import here to avoid circular imports
            from .db import get_db_health

            db_health = get_db_health()
            is_db_healthy = db_health.get("status") == "healthy"

            status_code = 200 if is_db_healthy else 503

            return JSONResponse(
                status_code=status_code,
                content={
                    "status": "ready" if is_db_healthy else "not ready",
                    "timestamp": time.time(),
                    "checks": {
                        "database": db_health,
                        "dependencies": "ok",
                    }
                }
            )
        except Exception as e:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not ready",
                    "error": str(e),
                    "timestamp": time.time(),
                }
            )

    @app.get("/health/live")
    async def liveness_check():
        """Liveness check for container orchestration."""
        return {
            "status": "alive",
            "timestamp": time.time(),
        }


def setup_middleware(app: FastAPI, enable_rate_limiting: bool = True) -> None:
    """Configure all middleware for the FastAPI application."""

    # Add health endpoints first
    add_health_endpoints(app)

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:5174"],  # React dev servers
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Compression middleware
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Custom middleware (order matters - last added is first executed)
    # Add validation middleware first (will be executed last, closest to endpoints)
    validation_middleware = create_validation_middleware()
    app.middleware("http")(validation_middleware)

    if enable_rate_limiting:
        app.add_middleware(
            RateLimitMiddleware,
            default_requests_per_minute=1000,
            strict_requests_per_minute=200
        )

    app.add_middleware(SecurityMiddleware)
    app.add_middleware(LoggingMiddleware)

    # Log middleware setup
    logger = get_logger("middleware.setup")
    logger.info(
        "Middleware configured",
        rate_limiting=enable_rate_limiting,
        input_validation=True,
        cors_enabled=True,
        security_headers=True,
        compression=True,
    )# CORS update
