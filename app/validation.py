"""
Comprehensive input validation and sanitization for the AI MVP application.

This module provides:
- Request body validation with detailed error messages
- Query parameter validation and sanitization
- File upload validation and security checks
- SQL injection and XSS prevention
- Data format validation (emails, URLs, etc.)
- Custom validation decorators for endpoints
"""

import re
import html
import urllib.parse
from typing import Any, Dict, List, Optional, Union, Callable
from functools import wraps
from datetime import datetime

from fastapi import HTTPException, Request, status
from pydantic import BaseModel, Field, validator
from pydantic import ValidationError as PydanticValidationError

from .logging_config import get_logger, log_exception

logger = get_logger(__name__)

# Validation patterns
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
URL_PATTERN = re.compile(r'^https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:\w*))?)?$')
UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
DOI_PATTERN = re.compile(r'^10\.\d{4,}/[-._;()/:\w\[\]]+$')
PMID_PATTERN = re.compile(r'^\d{1,8}$')
# Updated to allow medical/research terms with apostrophes, quotes, ampersands, slashes
# Examples: "Huntington's disease", "ADHD", "HIV/AIDS", "Alzheimer's & dementia"
SAFE_STRING_PATTERN = re.compile(r'^[a-zA-Z0-9\s\-_.,;:()\[\]\'\"&/]+$')

# SQL injection patterns to detect
SQL_INJECTION_PATTERNS = [
    r"(?i)(union\s+select)",
    r"(?i)(insert\s+into)",
    r"(?i)(delete\s+from)",
    r"(?i)(drop\s+table)",
    r"(?i)(update\s+set)",
    r"(?i)(create\s+table)",
    r"(?i)(alter\s+table)",
    r"(?i)(exec\s*\()",
    r"(?i)(script\s*>)",
    r"['\";].*--",
    r"['\"];.*\/\*",
]

# XSS patterns to detect
XSS_PATTERNS = [
    r"(?i)<script[^>]*>.*?</script>",
    r"(?i)javascript:",
    r"(?i)vbscript:",
    r"(?i)onload\s*=",
    r"(?i)onerror\s*=",
    r"(?i)onclick\s*=",
    r"(?i)<iframe[^>]*>",
    r"(?i)<object[^>]*>",
    r"(?i)<embed[^>]*>",
]


class ValidationError(Exception):
    """Custom validation error with detailed context."""

    def __init__(self, message: str, field: str = None, value: Any = None):
        self.message = message
        self.field = field
        self.value = value
        super().__init__(message)


class InputSanitizer:
    """Sanitize and validate input data."""

    @staticmethod
    def sanitize_string(value: str, max_length: int = 1000) -> str:
        """Sanitize string input to prevent XSS and injection attacks."""
        if not isinstance(value, str):
            raise ValidationError("Value must be a string", value=value)

        # Check length
        if len(value) > max_length:
            raise ValidationError(f"String too long (max {max_length} characters)", value=len(value))

        # Check for SQL injection patterns
        for pattern in SQL_INJECTION_PATTERNS:
            if re.search(pattern, value):
                logger.warning("Potential SQL injection attempt detected", pattern=pattern, value=value[:100])
                raise ValidationError("Invalid characters in input", field="security", value="SQL_INJECTION")

        # Check for XSS patterns
        for pattern in XSS_PATTERNS:
            if re.search(pattern, value):
                logger.warning("Potential XSS attempt detected", pattern=pattern, value=value[:100])
                raise ValidationError("Invalid characters in input", field="security", value="XSS")

        # HTML escape the string
        sanitized = html.escape(value.strip())

        return sanitized

    @staticmethod
    def validate_email(email: str) -> str:
        """Validate email format."""
        email = email.strip().lower()
        if not EMAIL_PATTERN.match(email):
            raise ValidationError("Invalid email format", field="email", value=email)
        return email

    @staticmethod
    def validate_url(url: str) -> str:
        """Validate URL format and safety."""
        url = url.strip()
        if not URL_PATTERN.match(url):
            raise ValidationError("Invalid URL format", field="url", value=url)

        # Check for suspicious domains or paths
        parsed = urllib.parse.urlparse(url)
        if parsed.hostname and parsed.hostname.lower() in ['localhost', '127.0.0.1', '0.0.0.0']:
            raise ValidationError("Local URLs not allowed", field="url", value=url)

        return url

    @staticmethod
    def validate_uuid(uuid_str: str) -> str:
        """Validate UUID format."""
        uuid_str = uuid_str.strip().lower()
        if not UUID_PATTERN.match(uuid_str):
            raise ValidationError("Invalid UUID format", field="uuid", value=uuid_str)
        return uuid_str

    @staticmethod
    def validate_doi(doi: str) -> str:
        """Validate DOI format."""
        doi = doi.strip()
        if not DOI_PATTERN.match(doi):
            raise ValidationError("Invalid DOI format", field="doi", value=doi)
        return doi

    @staticmethod
    def validate_pmid(pmid: str) -> str:
        """Validate PubMed ID format."""
        pmid = pmid.strip()
        if not PMID_PATTERN.match(pmid):
            raise ValidationError("Invalid PMID format", field="pmid", value=pmid)
        return pmid

    @staticmethod
    def validate_integer(value: Any, min_val: int = None, max_val: int = None) -> int:
        """Validate integer with optional bounds."""
        try:
            int_val = int(value)
        except (ValueError, TypeError):
            raise ValidationError("Value must be an integer", value=value)

        if min_val is not None and int_val < min_val:
            raise ValidationError(f"Value must be >= {min_val}", value=int_val)

        if max_val is not None and int_val > max_val:
            raise ValidationError(f"Value must be <= {max_val}", value=int_val)

        return int_val

    @staticmethod
    def validate_float(value: Any, min_val: float = None, max_val: float = None) -> float:
        """Validate float with optional bounds."""
        try:
            float_val = float(value)
        except (ValueError, TypeError):
            raise ValidationError("Value must be a number", value=value)

        if min_val is not None and float_val < min_val:
            raise ValidationError(f"Value must be >= {min_val}", value=float_val)

        if max_val is not None and float_val > max_val:
            raise ValidationError(f"Value must be <= {max_val}", value=float_val)

        return float_val


class QueryParameterValidator:
    """Validate and sanitize query parameters."""

    @staticmethod
    def validate_pagination(limit: Any = None, offset: Any = None) -> Dict[str, int]:
        """Validate pagination parameters."""
        sanitizer = InputSanitizer()

        validated_limit = 20  # default
        validated_offset = 0  # default

        if limit is not None:
            validated_limit = sanitizer.validate_integer(limit, min_val=1, max_val=1000)

        if offset is not None:
            validated_offset = sanitizer.validate_integer(offset, min_val=0, max_val=100000)

        return {"limit": validated_limit, "offset": validated_offset}

    @staticmethod
    def validate_search_query(query: str) -> str:
        """Validate search query parameters."""
        sanitizer = InputSanitizer()

        if not query or not query.strip():
            raise ValidationError("Search query cannot be empty", field="query")

        # Sanitize and validate
        clean_query = sanitizer.sanitize_string(query, max_length=2000)

        if len(clean_query.strip()) < 2:
            raise ValidationError("Search query too short (minimum 2 characters)", field="query")

        return clean_query

    @staticmethod
    def validate_date_range(start_date: str = None, end_date: str = None) -> Dict[str, Optional[datetime]]:
        """Validate date range parameters."""
        result = {"start_date": None, "end_date": None}

        if start_date:
            try:
                result["start_date"] = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            except ValueError:
                raise ValidationError("Invalid start_date format (use ISO format)", field="start_date", value=start_date)

        if end_date:
            try:
                result["end_date"] = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            except ValueError:
                raise ValidationError("Invalid end_date format (use ISO format)", field="end_date", value=end_date)

        if result["start_date"] and result["end_date"] and result["start_date"] > result["end_date"]:
            raise ValidationError("start_date must be before end_date", field="date_range")

        return result


# Enhanced Pydantic models with validation
class ValidatedLICO(BaseModel):
    """Validated LICO model with input sanitization."""
    learner: str = Field(..., min_length=2, max_length=500)
    intervention: str = Field(..., min_length=2, max_length=500)
    context: str = Field(..., min_length=2, max_length=500)
    outcome: str = Field(..., min_length=2, max_length=500)

    @validator('learner', 'intervention', 'context', 'outcome')
    def sanitize_fields(cls, v):
        return InputSanitizer.sanitize_string(v, max_length=500)


class ValidatedRunRequest(BaseModel):
    """Validated run request with comprehensive input validation."""
    query: str = Field(..., min_length=2, max_length=2000)
    thread_id: Optional[str] = Field(None, pattern=r'^[a-f0-9-]{36}$')
    max_records: Optional[int] = Field(50, ge=1, le=1000)
    sources: Optional[List[str]] = Field(None)

    @validator('query')
    def sanitize_query(cls, v):
        return QueryParameterValidator.validate_search_query(v)

    @validator('thread_id')
    def validate_thread_id(cls, v):
        if v is not None:
            return InputSanitizer.validate_uuid(v)
        return v

    @validator('sources')
    def validate_sources(cls, v):
        if v is not None:
            valid_sources = {'PubMed', 'Crossref', 'arXiv', 'ERIC', 'SemanticScholar', 'GoogleScholar'}
            for source in v:
                if source not in valid_sources:
                    raise ValueError(f"Invalid source: {source}")
        return v


def validate_request_body(model_class: BaseModel):
    """Decorator to validate request body against a Pydantic model."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except ValidationError as e:
                logger.warning("Request validation failed",
                             error=str(e),
                             field=getattr(e, 'field', None),
                             value=getattr(e, 'value', None))
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "error": "Validation failed",
                        "message": str(e),
                        "field": getattr(e, 'field', None)
                    }
                )
            except ValueError as e:
                logger.warning("Request value error", error=str(e))
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"error": "Invalid input", "message": str(e)}
                )
        return wrapper
    return decorator


def validate_query_params(**param_validators):
    """Decorator to validate query parameters."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            try:
                # Extract and validate query parameters
                for param_name, validator_func in param_validators.items():
                    param_value = request.query_params.get(param_name)
                    if param_value is not None:
                        kwargs[param_name] = validator_func(param_value)

                return await func(*args, **kwargs)

            except ValidationError as e:
                logger.warning("Query parameter validation failed",
                             error=str(e),
                             field=getattr(e, 'field', None),
                             value=getattr(e, 'value', None))
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "Invalid query parameter",
                        "message": str(e),
                        "field": getattr(e, 'field', None)
                    }
                )
        return wrapper
    return decorator


def sanitize_response_data(data: Any) -> Any:
    """Sanitize response data to prevent information leakage."""
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            # Remove sensitive fields from responses
            if key.lower() in ['password', 'secret', 'token', 'key', 'api_key']:
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = sanitize_response_data(value)
        return sanitized

    elif isinstance(data, list):
        return [sanitize_response_data(item) for item in data]

    elif isinstance(data, str):
        # Ensure response strings are safe
        return html.escape(data) if len(data) < 10000 else data[:10000] + "... [TRUNCATED]"

    else:
        return data


class FileValidator:
    """Validate file uploads for security."""

    ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.csv', '.json', '.xml'}
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

    @classmethod
    def validate_file(cls, filename: str, content: bytes) -> None:
        """Validate uploaded file."""
        # Check filename
        if not filename or '..' in filename or '/' in filename or '\\' in filename:
            raise ValidationError("Invalid filename", field="filename", value=filename)

        # Check extension
        ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
        if ext not in cls.ALLOWED_EXTENSIONS:
            raise ValidationError(f"File type not allowed. Allowed: {', '.join(cls.ALLOWED_EXTENSIONS)}",
                                field="file_type", value=ext)

        # Check file size
        if len(content) > cls.MAX_FILE_SIZE:
            raise ValidationError(f"File too large (max {cls.MAX_FILE_SIZE // 1024 // 1024}MB)",
                                field="file_size", value=len(content))

        # Check for malicious content in headers
        header = content[:1024].decode('utf-8', errors='ignore').lower()
        malicious_patterns = ['<script', 'javascript:', 'vbscript:', '<?php', '<%']
        for pattern in malicious_patterns:
            if pattern in header:
                raise ValidationError("Potentially malicious file content detected",
                                    field="file_security", value=pattern)


def create_validation_middleware():
    """Create middleware for global request validation."""

    async def validation_middleware(request: Request, call_next):
        """Global validation middleware."""
        try:
            # Check request size
            if hasattr(request, 'content_length') and request.content_length:
                if request.content_length > 100 * 1024 * 1024:  # 100MB limit
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Request too large"
                    )

            # Validate common headers
            user_agent = request.headers.get('user-agent', '')
            if len(user_agent) > 500:
                logger.warning("Suspicious user agent", user_agent=user_agent[:100])

            response = await call_next(request)
            return response

        except ValidationError as e:
            log_exception(logger, e, context={"request_path": request.url.path})
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "Validation failed", "message": str(e)}
            )

    return validation_middleware