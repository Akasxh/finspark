"""Unit tests for the IntegrationLifecycle state machine."""

from __future__ import annotations

import pytest

from finspark.schemas.common import ConfigStatus
from finspark.services.lifecycle import (
    TRANSITIONS,
    IntegrationLifecycle,
    InvalidTransitionError,
)


class TestCanTransition:
    def test_draft_to_configured(self) -> None:
        lc = IntegrationLifecycle(state=ConfigStatus.DRAFT)
        assert lc.can_transition(ConfigStatus.CONFIGURED) is True

    def test_draft_to_active_blocked(self) -> None:
        lc = IntegrationLifecycle(state=ConfigStatus.DRAFT)
        assert lc.can_transition(ConfigStatus.ACTIVE) is False

    def test_active_to_deprecated(self) -> None:
        lc = IntegrationLifecycle(state=ConfigStatus.ACTIVE)
        assert lc.can_transition(ConfigStatus.DEPRECATED) is True

    def test_active_to_rollback(self) -> None:
        lc = IntegrationLifecycle(state=ConfigStatus.ACTIVE)
        assert lc.can_transition(ConfigStatus.ROLLBACK) is True

    def test_deprecated_to_draft(self) -> None:
        lc = IntegrationLifecycle(state=ConfigStatus.DEPRECATED)
        assert lc.can_transition(ConfigStatus.DRAFT) is True

    def test_rollback_to_configured(self) -> None:
        lc = IntegrationLifecycle(state=ConfigStatus.ROLLBACK)
        assert lc.can_transition(ConfigStatus.CONFIGURED) is True

    def test_same_state_blocked(self) -> None:
        for status in ConfigStatus:
            lc = IntegrationLifecycle(state=status)
            assert lc.can_transition(status) is False, f"Self-transition allowed for {status}"


class TestTransition:
    def test_happy_path_updates_state(self) -> None:
        lc = IntegrationLifecycle(state=ConfigStatus.DRAFT)
        entry = lc.transition(ConfigStatus.CONFIGURED, actor="tester")
        assert lc.state == ConfigStatus.CONFIGURED
        assert entry.from_state == ConfigStatus.DRAFT
        assert entry.to_state == ConfigStatus.CONFIGURED
        assert entry.actor == "tester"

    def test_audit_trail_appended(self) -> None:
        lc = IntegrationLifecycle(state=ConfigStatus.DRAFT)
        lc.transition(ConfigStatus.CONFIGURED)
        lc.transition(ConfigStatus.VALIDATING)
        assert len(lc.audit_trail) == 2
        assert lc.audit_trail[0].to_state == ConfigStatus.CONFIGURED
        assert lc.audit_trail[1].to_state == ConfigStatus.VALIDATING

    def test_invalid_transition_raises(self) -> None:
        lc = IntegrationLifecycle(state=ConfigStatus.DRAFT)
        with pytest.raises(InvalidTransitionError) as exc_info:
            lc.transition(ConfigStatus.ACTIVE)
        assert "draft" in str(exc_info.value)
        assert "active" in str(exc_info.value)
        # State must not change on failure
        assert lc.state == ConfigStatus.DRAFT

    def test_reason_stored(self) -> None:
        lc = IntegrationLifecycle(state=ConfigStatus.CONFIGURED)
        entry = lc.transition(ConfigStatus.VALIDATING, reason="ready for QA")
        assert entry.reason == "ready for QA"

    def test_timestamp_present(self) -> None:
        lc = IntegrationLifecycle(state=ConfigStatus.DRAFT)
        entry = lc.transition(ConfigStatus.CONFIGURED)
        assert entry.timestamp is not None


class TestGetAvailableTransitions:
    def test_draft_available(self) -> None:
        lc = IntegrationLifecycle(state=ConfigStatus.DRAFT)
        available = lc.get_available_transitions()
        assert ConfigStatus.CONFIGURED in available
        assert len(available) == 1

    def test_active_available(self) -> None:
        lc = IntegrationLifecycle(state=ConfigStatus.ACTIVE)
        available = lc.get_available_transitions()
        assert set(available) == {ConfigStatus.DEPRECATED, ConfigStatus.ROLLBACK}

    def test_configured_has_backward_and_forward(self) -> None:
        lc = IntegrationLifecycle(state=ConfigStatus.CONFIGURED)
        available = lc.get_available_transitions()
        assert ConfigStatus.VALIDATING in available
        assert ConfigStatus.DRAFT in available


class TestFullLifecycle:
    """Walk the full happy-path: draft -> configured -> validating -> testing -> active -> deprecated."""

    def test_full_forward_path(self) -> None:
        lc = IntegrationLifecycle(state=ConfigStatus.DRAFT)
        lc.transition(ConfigStatus.CONFIGURED)
        lc.transition(ConfigStatus.VALIDATING)
        lc.transition(ConfigStatus.TESTING)
        lc.transition(ConfigStatus.ACTIVE)
        lc.transition(ConfigStatus.DEPRECATED)
        assert lc.state == ConfigStatus.DEPRECATED
        assert len(lc.audit_trail) == 5

    def test_rollback_path(self) -> None:
        lc = IntegrationLifecycle(state=ConfigStatus.DRAFT)
        lc.transition(ConfigStatus.CONFIGURED)
        lc.transition(ConfigStatus.VALIDATING)
        lc.transition(ConfigStatus.TESTING)
        lc.transition(ConfigStatus.ACTIVE)
        lc.transition(ConfigStatus.ROLLBACK)
        lc.transition(ConfigStatus.CONFIGURED)
        assert lc.state == ConfigStatus.CONFIGURED


class TestTransitionsMapCompleteness:
    """Ensure every ConfigStatus value has an entry in the TRANSITIONS map."""

    def test_all_states_have_entries(self) -> None:
        for status in ConfigStatus:
            assert status in TRANSITIONS, f"Missing TRANSITIONS entry for {status}"
