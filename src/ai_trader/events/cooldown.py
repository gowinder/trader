"""Cooldown manager to prevent excessive LLM triggering."""

from __future__ import annotations

import time


class CooldownManager:
    """Manages global and per-event cooldowns for event triggering.

    Args:
        global_cooldown: Seconds after any event trigger during which ALL events are blocked.
        per_event_cooldown: Seconds after a specific event trigger during which THAT event is blocked.
    """

    def __init__(
        self,
        global_cooldown: int = 300,
        per_event_cooldown: int = 600,
    ) -> None:
        self.global_cooldown = global_cooldown
        self.per_event_cooldown = per_event_cooldown
        self._last_global_trigger: float | None = None
        self._last_per_event: dict[str, float] = {}

    def can_trigger(self, event_type: str) -> bool:
        """Check whether *event_type* is allowed to fire right now.

        Checks global cooldown first, then per-event cooldown.
        """
        now = time.monotonic()

        # Global cooldown check
        if self._last_global_trigger is not None:
            if now - self._last_global_trigger < self.global_cooldown:
                return False

        # Per-event cooldown check
        last = self._last_per_event.get(event_type)
        if last is not None:
            if now - last < self.per_event_cooldown:
                return False

        return True

    def record_trigger(self, event_type: str) -> None:
        """Record that *event_type* has just been triggered."""
        now = time.monotonic()
        self._last_global_trigger = now
        self._last_per_event[event_type] = now

    def reset(self) -> None:
        """Clear all cooldown state."""
        self._last_global_trigger = None
        self._last_per_event.clear()
