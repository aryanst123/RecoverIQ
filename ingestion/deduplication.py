from typing import Dict, Optional, Any
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

@dataclass
class IngestedEventRecord:
    event_id: str
    event_type: str
    received_at: datetime
    processed: bool
    duplicate_count: int = 0
    payload_summary: Optional[Dict[str, Any]] = None

class WebhookDeduplicationStore:
    """
    Tracks and deduplicates incoming webhook events using unique event IDs (e.g. x-razorpay-event-id).
    Ensures at-least-once delivery guarantees without duplicate business state mutations.
    """
    def __init__(self):
        self._events: Dict[str, IngestedEventRecord] = {}

    def check_and_record(
        self,
        event_id: str,
        event_type: str,
        payload_summary: Optional[Dict[str, Any]] = None,
        now: Optional[datetime] = None,
    ) -> tuple[bool, IngestedEventRecord]:
        """
        Records an incoming event ID.
        Returns (is_duplicate, event_record).
        If is_duplicate is True, the caller MUST NOT apply business mutations.
        """
        current_time = now or datetime.now(timezone.utc)

        if event_id in self._events:
            rec = self._events[event_id]
            rec.duplicate_count += 1
            return True, rec

        rec = IngestedEventRecord(
            event_id=event_id,
            event_type=event_type,
            received_at=current_time,
            processed=True,
            duplicate_count=0,
            payload_summary=payload_summary,
        )
        self._events[event_id] = rec
        return False, rec

    def is_duplicate(self, event_id: str) -> bool:
        return event_id in self._events
