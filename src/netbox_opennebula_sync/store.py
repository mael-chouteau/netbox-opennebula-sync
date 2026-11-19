"""NetBox write backend protocol (ORM or REST)."""

from __future__ import annotations

from typing import Any, Protocol


class NetBoxStore(Protocol):
    """Minimal surface used by Reconciler — dict-shaped records with ``id``."""

    stats: dict[str, int]
    dry_run: bool

    def close(self) -> None: ...

    def __enter__(self) -> NetBoxStore: ...

    def __exit__(self, *args: Any) -> None: ...

    def ping(self) -> dict[str, Any]: ...

    def find_one(self, path: str, params: dict[str, Any]) -> dict[str, Any] | None: ...

    def list_all(
        self, path: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]: ...

    def ensure(
        self,
        kind: str,
        path: str,
        lookup: dict[str, Any],
        payload: dict[str, Any],
        update_fields: list[str] | None = None,
    ) -> dict[str, Any] | None: ...

    def _write(
        self,
        method: str,
        kind: str,
        path: str,
        payload: dict[str, Any],
        existing: dict[str, Any] | None,
    ) -> dict[str, Any] | None: ...

    def delete(self, path: str, obj_id: int) -> bool: ...
