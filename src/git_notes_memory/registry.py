"""Service registry for centralized singleton management.

This module provides a ServiceRegistry class that manages service singletons
in a centralized way, replacing module-level global variables.

Key benefits:
- Centralized singleton management
- Clean reset mechanism for testing
- Type-safe service retrieval

Usage::

    from git_notes_memory.registry import ServiceRegistry
    from git_notes_memory.capture import CaptureService

    # Get or create a singleton instance
    capture = ServiceRegistry.get(CaptureService)

    # Reset all services (for testing)
    ServiceRegistry.reset()

    # Register a custom instance (for mocking)
    ServiceRegistry.register(CaptureService, mock_capture)
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar, TypeVar, cast

__all__ = ["ServiceRegistry"]

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ServiceRegistry:
    """Centralized registry for service singletons.

    Manages service instances in a class-level dictionary, providing
    a clean way to access singletons and reset them for testing.

    Example::

        # Get or create a singleton instance
        capture = ServiceRegistry.get(CaptureService)

        # Reset all services (for testing)
        ServiceRegistry.reset()

        # Register a custom instance (for mocking)
        ServiceRegistry.register(CaptureService, mock_instance)
    """

    _services: ClassVar[dict[type, Any]] = {}

    @classmethod
    def get(cls, service_type: type[T], **kwargs: Any) -> T:
        """Get or create a singleton instance of a service.

        If an instance doesn't exist, creates one using the default
        constructor with any provided kwargs.

        Args:
            service_type: The service class to get an instance of.
            **kwargs: Keyword arguments to pass to the constructor
                if creating a new instance. If an instance already exists
                for ``service_type``, providing ``kwargs`` will raise
                a :class:`ValueError`.

        Returns:
            The singleton instance of the service.

        Raises:
            ValueError: If keyword arguments are provided for a service
                type that already has a registered instance.

        Example::

            capture = ServiceRegistry.get(CaptureService)
            recall = ServiceRegistry.get(RecallService)
        """
        if service_type in cls._services:
            if kwargs:
                msg = (
                    f"Service instance for {service_type.__name__} already exists; "
                    "cannot pass constructor kwargs on subsequent get() calls."
                )
                raise ValueError(msg)
            return cast(T, cls._services[service_type])

        cls._services[service_type] = service_type(**kwargs)
        logger.debug("Created service instance: %s", service_type.__name__)
        return cast(T, cls._services[service_type])

    @classmethod
    def register(cls, service_type: type[T], instance: T) -> None:
        """Register a specific instance for a service type.

        Useful for testing when you want to inject a mock or
        pre-configured instance.

        Args:
            service_type: The service class type.
            instance: The instance to register.

        Example::

            mock_capture = Mock(spec=CaptureService)
            ServiceRegistry.register(CaptureService, mock_capture)
        """
        cls._services[service_type] = instance
        logger.debug("Registered service instance: %s", service_type.__name__)

    @classmethod
    def reset(cls) -> None:
        """Reset all service singletons.

        Clears all registered instances, forcing new instances to be
        created on next access. Used in testing to ensure clean state
        between tests.

        Example::

            @pytest.fixture(autouse=True)
            def reset_services():
                ServiceRegistry.reset()
                yield
                ServiceRegistry.reset()
        """
        cls._services.clear()
        logger.debug("Reset all service instances")
