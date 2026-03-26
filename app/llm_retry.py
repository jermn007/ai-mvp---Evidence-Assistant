# app/llm_retry.py
"""
Enhanced retry and backoff logic for LLM operations
Provides robust error handling, rate limiting, and circuit breaker patterns
"""
from __future__ import annotations

import time
import asyncio
import logging
from typing import Any, Callable, Optional, Type, Union, List, Dict
from functools import wraps
from dataclasses import dataclass
from enum import Enum

try:
    from tenacity import (
        retry, stop_after_attempt, wait_exponential, retry_if_exception_type,
        before_sleep_log, after_log
    )
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False

from langchain_core.exceptions import LangChainException

logger = logging.getLogger(__name__)

class RetryableError(Enum):
    """Types of retryable errors"""
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    SERVER_ERROR = "server_error"
    TEMPORARY_FAILURE = "temporary_failure"

@dataclass
class RetryConfig:
    """Configuration for retry behavior"""
    max_attempts: int = 3
    min_wait: float = 1.0
    max_wait: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on_rate_limit: bool = True
    retry_on_timeout: bool = True
    retry_on_connection_error: bool = True
    retry_on_server_error: bool = True

class CircuitBreaker:
    """Circuit breaker pattern for LLM operations"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half-open
    
    def can_execute(self) -> bool:
        """Check if operation can be executed"""
        if self.state == "closed":
            return True
        elif self.state == "open":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "half-open"
                return True
            return False
        else:  # half-open
            return True
    
    def record_success(self):
        """Record successful operation"""
        self.failure_count = 0
        self.state = "closed"
    
    def record_failure(self):
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")

class RateLimiter:
    """Rate limiter for LLM operations"""
    
    def __init__(self, requests_per_minute: int = 60, tokens_per_minute: int = 100000):
        self.requests_per_minute = requests_per_minute
        self.tokens_per_minute = tokens_per_minute
        self.request_times: List[float] = []
        self.token_usage: List[tuple[float, int]] = []  # (timestamp, tokens)
    
    def can_make_request(self, estimated_tokens: int = 1000) -> tuple[bool, float]:
        """
        Check if request can be made
        Returns (can_proceed, wait_time)
        """
        current_time = time.time()
        minute_ago = current_time - 60
        
        # Clean old entries
        self.request_times = [t for t in self.request_times if t > minute_ago]
        self.token_usage = [(t, tokens) for t, tokens in self.token_usage if t > minute_ago]
        
        # Check request rate limit
        if len(self.request_times) >= self.requests_per_minute:
            wait_time = 60 - (current_time - self.request_times[0])
            return False, wait_time
        
        # Check token rate limit
        total_tokens = sum(tokens for _, tokens in self.token_usage)
        if total_tokens + estimated_tokens > self.tokens_per_minute:
            wait_time = 60 - (current_time - self.token_usage[0][0])
            return False, wait_time
        
        return True, 0.0
    
    def record_request(self, tokens_used: int = 0):
        """Record a completed request"""
        current_time = time.time()
        self.request_times.append(current_time)
        if tokens_used > 0:
            self.token_usage.append((current_time, tokens_used))

def get_retryable_exceptions():
    """Get list of exceptions that should trigger retries"""
    exceptions = [
        ConnectionError,
        TimeoutError,
        LangChainException,
    ]
    
    # Add OpenAI specific exceptions if available
    try:
        import openai
        exceptions.extend([
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.InternalServerError,
        ])
    except ImportError:
        pass
    
    # Add requests exceptions
    try:
        import requests
        exceptions.extend([
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.RequestException,
        ])
    except ImportError:
        pass
    
    return tuple(exceptions)

def should_retry_exception(exc: Exception) -> bool:
    """Determine if an exception should trigger a retry"""
    retryable_exceptions = get_retryable_exceptions()
    
    if isinstance(exc, retryable_exceptions):
        return True
    
    # Check for specific error messages
    error_message = str(exc).lower()
    retryable_messages = [
        "rate limit",
        "timeout",
        "connection",
        "server error",
        "internal error",
        "service unavailable",
        "too many requests"
    ]
    
    return any(msg in error_message for msg in retryable_messages)

def create_retry_decorator(config: RetryConfig):
    """Create a retry decorator with the given configuration"""
    if not TENACITY_AVAILABLE:
        logger.warning("Tenacity not available - retry logic disabled")
        return lambda func: func
    
    return retry(
        stop=stop_after_attempt(config.max_attempts),
        wait=wait_exponential(
            multiplier=config.min_wait,
            max=config.max_wait,
            exp_base=config.exponential_base
        ),
        retry=retry_if_exception_type(get_retryable_exceptions()),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO)
    )

def llm_retry(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 60.0,
    exponential_base: float = 2.0
):
    """
    Decorator for adding retry logic to LLM operations
    
    Args:
        max_attempts: Maximum number of retry attempts
        min_wait: Minimum wait time between retries (seconds)
        max_wait: Maximum wait time between retries (seconds)
        exponential_base: Base for exponential backoff
    """
    def decorator(func: Callable) -> Callable:
        if not TENACITY_AVAILABLE:
            logger.warning("Tenacity not available - retry logic disabled")
            return func
        
        config = RetryConfig(
            max_attempts=max_attempts,
            min_wait=min_wait,
            max_wait=max_wait,
            exponential_base=exponential_base
        )
        
        retry_decorator = create_retry_decorator(config)
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await retry_decorator(func)(*args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return retry_decorator(func)(*args, **kwargs)
        
        # Return appropriate wrapper based on function type
        if hasattr(func, '__code__') and func.__code__.co_flags & 0x80:  # CO_COROUTINE
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

class LLMOperationManager:
    """
    Manages LLM operations with retry, rate limiting, and circuit breaking
    """
    
    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        rate_limiter: Optional[RateLimiter] = None
    ):
        self.retry_config = retry_config or RetryConfig()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.rate_limiter = rate_limiter or RateLimiter()
        
    async def execute_with_resilience(
        self,
        operation: Callable,
        *args,
        estimated_tokens: int = 1000,
        **kwargs
    ) -> Any:
        """
        Execute an LLM operation with full resilience features
        
        Args:
            operation: The LLM operation to execute
            *args: Arguments for the operation
            estimated_tokens: Estimated token usage for rate limiting
            **kwargs: Keyword arguments for the operation
        """
        # Check circuit breaker
        if not self.circuit_breaker.can_execute():
            raise Exception("Circuit breaker is open - operation not allowed")
        
        # Check rate limiter
        can_proceed, wait_time = self.rate_limiter.can_make_request(estimated_tokens)
        if not can_proceed:
            logger.info(f"Rate limit reached - waiting {wait_time:.2f} seconds")
            await asyncio.sleep(wait_time)
        
        # Execute with retry logic
        retry_decorator = create_retry_decorator(self.retry_config)
        
        try:
            start_time = time.time()
            result = await retry_decorator(operation)(*args, **kwargs)
            
            # Record success
            self.circuit_breaker.record_success()
            
            # Estimate tokens used (this could be improved with actual usage tracking)
            execution_time = time.time() - start_time
            estimated_tokens_used = max(estimated_tokens, int(execution_time * 100))
            self.rate_limiter.record_request(estimated_tokens_used)
            
            return result
            
        except Exception as e:
            # Record failure
            self.circuit_breaker.record_failure()
            logger.error(f"LLM operation failed after retries: {e}")
            raise
    
    def get_status(self) -> Dict[str, Any]:
        """Get status information for monitoring"""
        return {
            "circuit_breaker": {
                "state": self.circuit_breaker.state,
                "failure_count": self.circuit_breaker.failure_count,
                "last_failure_time": self.circuit_breaker.last_failure_time
            },
            "rate_limiter": {
                "requests_per_minute": self.rate_limiter.requests_per_minute,
                "tokens_per_minute": self.rate_limiter.tokens_per_minute,
                "current_requests": len(self.rate_limiter.request_times),
                "current_tokens": sum(tokens for _, tokens in self.rate_limiter.token_usage)
            },
            "retry_config": {
                "max_attempts": self.retry_config.max_attempts,
                "min_wait": self.retry_config.min_wait,
                "max_wait": self.retry_config.max_wait
            }
        }

# Global operation manager instance
_operation_manager: Optional[LLMOperationManager] = None

def get_operation_manager(
    retry_config: Optional[RetryConfig] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
    rate_limiter: Optional[RateLimiter] = None
) -> LLMOperationManager:
    """Get or create the global operation manager"""
    global _operation_manager
    if _operation_manager is None:
        _operation_manager = LLMOperationManager(retry_config, circuit_breaker, rate_limiter)
    return _operation_manager

# Convenience functions
async def execute_llm_operation(
    operation: Callable,
    *args,
    estimated_tokens: int = 1000,
    **kwargs
) -> Any:
    """Execute an LLM operation with default resilience features"""
    manager = get_operation_manager()
    return await manager.execute_with_resilience(operation, *args, estimated_tokens=estimated_tokens, **kwargs)