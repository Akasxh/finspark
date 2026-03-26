"""Integration lifecycle state machine for configuration status transitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from finspark.schemas.common import ConfigStatus

# Valid state transitions: source -> set of allowed targets
TRANSITIONS: dict[ConfigStatus, frozenset[ConfigStatus]] = {
    ConfigStatus.DRAFT: frozenset({ConfigStatus.CONFIGURED}),
    ConfigStatus.CONFIGURED: frozenset({ConfigStatus.VALIDATING, ConfigStatus.DRAFT}),
    ConfigStatus.VALIDATING: frozenset({ConfigStatus.TESTING, ConfigStatus.CONFIGURED}),
    ConfigStatus.TESTING: frozenset({ConfigStatus.ACTIVE, ConfigStatus.CONFIGURED}),
    ConfigStatus.ACTIVE: frozenset({ConfigStatus.DEPRECATED, ConfigStatus.ROLLBACK}),
    ConfigStatus.DEPRECATED: frozenset({ConfigStatus.DRAFT}),
    ConfigStatus.ROLLBACK: frozenset({ConfigStatus.CONFIGURED, ConfigStatus.DRAFT}),
}


class InvalidTransitionError(Exception):
    """Raised when a state transition is not allowed."""

    def __init__(self, current: ConfigStatus, target: ConfigStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Transition from '{current.value}' to '{target.value}' is not allowed")


@dataclass
class AuditEntry:
    """Record of a lifecycle state transition."""

    from_state: ConfigStatus
    to_state: ConfigStatus
    timestamp: datetime
    actor: str | None = None
    reason: str | None = None


@dataclass
class IntegrationLifecycle:
    """State machine governing configuration lifecycle transitions.

    Enforces the directed graph of valid status changes and maintains
    an in-memory audit trail of all transitions.
    """

    state: ConfigStatus = ConfigStatus.DRAFT
    audit_trail: list[AuditEntry] = field(default_factory=list)

    def can_transition(self, target: ConfigStatus) -> bool:
        """Check whether transitioning to *target* is allowed from the current state."""
        allowed = TRANSITIONS.get(self.state, frozenset())
        return target in allowed

    def get_available_transitions(self) -> list[ConfigStatus]:
        """Return the list of states reachable from the current state."""
        return sorted(TRANSITIONS.get(self.state, frozenset()), key=lambda s: s.value)

    def transition(
        self,
        target: ConfigStatus,
        *,
        actor: str | None = None,
        reason: str | None = None,
    ) -> AuditEntry:
        """Transition to *target* state.

        Validates the transition, updates internal state, and creates an
        audit entry.  Raises ``InvalidTransitionError`` if the transition
        is not permitted.
        """
        if not self.can_transition(target):
            raise InvalidTransitionError(self.state, target)

        entry = AuditEntry(
            from_state=self.state,
            to_state=target,
            timestamp=datetime.now(UTC),
            actor=actor,
            reason=reason,
        )
        self.state = target
        self.audit_trail.append(entry)
        return entry
