"""Runtime system entry points."""

from .resource import available_count, can_dispense, dispense_resource, resource_pool

__all__ = ["available_count", "can_dispense", "dispense_resource", "resource_pool"]
