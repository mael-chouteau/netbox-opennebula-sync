"""REST backend: thin alias over the standalone httpx client."""

from __future__ import annotations

from .netbox import NetBoxClient as RestStore

__all__ = ["RestStore"]
