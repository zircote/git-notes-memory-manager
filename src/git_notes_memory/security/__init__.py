"""Security module for secrets detection and filtering.

This module provides comprehensive secrets detection and filtering to prevent
sensitive data from being captured in memories. It integrates detect-secrets
for pattern-based detection and custom PII detection.

Example usage::

    from git_notes_memory.security import get_secrets_filtering_service

    # Filter content before storage
    service = get_secrets_filtering_service()
    result = service.filter(content, source="memory_content", namespace="decisions")

    if result.action == FilterAction.BLOCKED:
        raise BlockedContentError(result.detections)

    filtered_content = result.content  # Secrets redacted
"""

from __future__ import annotations

__all__ = [
    # Factory functions (lazy-loaded)
    "get_secrets_filtering_service",
    "get_redactor",
    "get_allowlist_manager",
    "get_audit_logger",
    # Enums
    "SecretType",
    "FilterStrategy",
    "FilterAction",
    # Models
    "SecretDetection",
    "FilterResult",
    "AllowlistEntry",
    "AuditEntry",
    # Exceptions
    "SecretsFilteringError",
    "BlockedContentError",
    "AllowlistError",
    "AuditLogError",
]


def __getattr__(name: str) -> object:
    """Lazy loading of service factories, models, and exceptions.

    This prevents the detect-secrets library from being loaded at import time.
    """
    # Factory functions - load service lazily
    if name == "get_secrets_filtering_service":
        from git_notes_memory.security.service import (
            get_default_service as get_secrets_filtering_service,
        )

        return get_secrets_filtering_service

    if name == "get_redactor":
        from git_notes_memory.security.redactor import (
            get_default_redactor as get_redactor,
        )

        return get_redactor

    if name == "get_allowlist_manager":
        from git_notes_memory.security.allowlist import (
            get_default_allowlist_manager as get_allowlist_manager,
        )

        return get_allowlist_manager

    if name == "get_audit_logger":
        from git_notes_memory.security.audit import (
            get_default_audit_logger as get_audit_logger,
        )

        return get_audit_logger

    # Enums - lightweight, import directly
    if name in {"SecretType", "FilterStrategy", "FilterAction"}:
        from git_notes_memory.security import models

        return getattr(models, name)

    # Models - lightweight, import directly
    if name in {"SecretDetection", "FilterResult", "AllowlistEntry"}:
        from git_notes_memory.security import models

        return getattr(models, name)

    if name == "AuditEntry":
        from git_notes_memory.security.audit import AuditEntry

        return AuditEntry

    # Exceptions
    if name in {
        "SecretsFilteringError",
        "BlockedContentError",
        "AllowlistError",
        "AuditLogError",
    }:
        from git_notes_memory.security import exceptions

        return getattr(exceptions, name)

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
