"""Small authorization-isolated in-memory context cache."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from threading import RLock

from travelops_recovery_agent.context_engineering.models import (
    CONTEXT_CACHE_VERSION,
    ContextBuildRequest,
    ContextBuildResult,
    ContextItem,
)


class ContextCache:
    """Bounded cache whose key includes every context-governance input."""

    def __init__(self, max_entries: int = 128) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._entries: OrderedDict[str, ContextBuildResult] = OrderedDict()
        self._lock = RLock()

    @staticmethod
    def key_for(
        request: ContextBuildRequest,
        items: tuple[ContextItem, ...],
        *,
        tool_policy_version: str,
        summary_versions: tuple[str, ...] = (),
    ) -> str:
        payload = {
            "cache_version": CONTEXT_CACHE_VERSION,
            "request": request.model_dump(mode="json"),
            "items": sorted(item.fingerprint() for item in items),
            "tool_policy_version": tool_policy_version,
            "summary_versions": sorted(summary_versions),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return f"ctx-{digest}"

    def get(self, key: str) -> ContextBuildResult | None:
        with self._lock:
            result = self._entries.get(key)
            if result is None:
                return None
            self._entries.move_to_end(key)
            return result

    def put(self, key: str, value: ContextBuildResult) -> None:
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def invalidate_case(self, case_id: str) -> int:
        """Remove only entries for the named case after durable evidence changes."""

        with self._lock:
            matching = [
                key for key, value in self._entries.items() if value.case_id == case_id
            ]
            for key in matching:
                del self._entries[key]
            return len(matching)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
