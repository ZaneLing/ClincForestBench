from __future__ import annotations

from typing import Dict, List

from .temporal import (
    CanonicalTemporalEvent,
    PendingAction,
    PendingStatus,
    TemporalCase,
    TemporalReplayMode,
    TemporalState,
)


class TemporalReplayEnvironment:
    """Deterministic information-acquisition replay for Temporal Forest v2.

    Results always come from an observed source event. Moving an order earlier
    shifts only that event's real turnaround time. An action without a recorded
    event is retained as UNOBSERVED and never receives a synthesized result.
    """

    def __init__(self, case: TemporalCase):
        self.case = case
        self._events_by_action: Dict[str, List[CanonicalTemporalEvent]] = {}
        for event in case.timeline_events:
            if event.action_id:
                self._events_by_action.setdefault(event.action_id, []).append(event)
        for events in self._events_by_action.values():
            events.sort(key=lambda item: (item.order_min(), item.event_id))
        self.state = TemporalState(case_id=case.case_id).refreshed()
        self.event_log: List[dict] = []

    def order(self, action_id: str) -> PendingAction:
        if any(item.action_id == action_id for item in self.state.pending_actions):
            raise ValueError(f"Action already ordered: {action_id}")
        already_used = set(self.state.revealed_event_ids)
        source = next(
            (
                item
                for item in self._events_by_action.get(action_id, [])
                if item.event_id not in already_used and item.arena.arena_eligible
            ),
            None,
        )
        before = self.state.state_hash
        if source is None:
            pending = PendingAction(
                pending_id=f"P::{len(self.state.pending_actions) + 1}",
                action_id=action_id,
                ordered_game_time=self.state.current_time_min,
                expected_available_game_time=None,
                source_event_id=None,
                temporal_replay_mode=TemporalReplayMode.UNOBSERVED,
                status=PendingStatus.UNOBSERVED,
            )
        else:
            latency = max(0.0, source.available_min() - source.order_min())
            pending = PendingAction(
                pending_id=f"P::{source.event_id}",
                action_id=action_id,
                ordered_game_time=self.state.current_time_min,
                expected_available_game_time=self.state.current_time_min + latency,
                source_event_id=source.event_id,
                temporal_replay_mode=(
                    TemporalReplayMode.OBSERVED_FIXED_TIME
                    if source.arena.temporal_replay_mode
                    == TemporalReplayMode.OBSERVED_FIXED_TIME
                    else TemporalReplayMode.OBSERVED_RESULT_WITH_SHIFTED_TAT
                ),
                status=PendingStatus.PENDING,
            )
        self.state.pending_actions.append(pending)
        self.state = self.state.refreshed()
        self.event_log.append(
            {
                "event_type": "ORDER_ACTION",
                "action_id": action_id,
                "game_time_before_min": self.state.current_time_min,
                "game_time_after_min": self.state.current_time_min,
                "pending": pending.model_dump(mode="json"),
                "state_before_hash": before,
                "state_after_hash": self.state.state_hash,
            }
        )
        return pending.model_copy(deep=True)

    def wait_for_next_result(self) -> List[CanonicalTemporalEvent]:
        waiting = [
            item
            for item in self.state.pending_actions
            if item.status == PendingStatus.PENDING
            and item.expected_available_game_time is not None
        ]
        if not waiting:
            return []
        before = self.state.state_hash
        next_time = min(item.expected_available_game_time for item in waiting)
        self.state.current_time_min = float(next_time)
        resolved: List[CanonicalTemporalEvent] = []
        by_id = {item.event_id: item for item in self.case.timeline_events}
        for pending in self.state.pending_actions:
            if (
                pending.status == PendingStatus.PENDING
                and pending.expected_available_game_time is not None
                and pending.expected_available_game_time <= next_time
            ):
                pending.status = PendingStatus.AVAILABLE
                if pending.source_event_id:
                    self.state.revealed_event_ids.append(pending.source_event_id)
                    resolved.append(by_id[pending.source_event_id])
        self.state = self.state.refreshed()
        self.event_log.append(
            {
                "event_type": "WAIT_FOR_NEXT_RESULT",
                "game_time_before_min": self.event_log[-1]["game_time_after_min"]
                if self.event_log
                else 0,
                "game_time_after_min": next_time,
                "resolved_event_ids": [item.event_id for item in resolved],
                "state_before_hash": before,
                "state_after_hash": self.state.state_hash,
            }
        )
        return resolved

    def review_result(self, event_id: str) -> CanonicalTemporalEvent:
        for pending in self.state.pending_actions:
            if pending.source_event_id == event_id:
                if pending.status != PendingStatus.AVAILABLE:
                    raise ValueError(f"Result is not available: {event_id}")
                pending.status = PendingStatus.REVIEWED
                self.state = self.state.refreshed()
                return next(
                    item for item in self.case.timeline_events if item.event_id == event_id
                )
        raise KeyError(event_id)
