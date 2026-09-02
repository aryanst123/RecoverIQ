import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
from dataclasses import dataclass
from domain.enums import ActionType

class ReservationError(Exception):
    pass

class DuplicateReservationError(ReservationError):
    pass

class InvalidReservationError(ReservationError):
    pass

@dataclass
class ActionReservation:
    reservation_id: str
    case_id: str
    action_type: ActionType
    idempotency_key: str
    policy_version: str
    created_at: datetime
    expires_at: datetime
    status: str = "RESERVED" # RESERVED, EXECUTING, CONFIRMED, EXPIRED, CANCELLED

class ActionReservationService:
    """
    Manages atomic action reservations.
    Guarantees that an action can only be executed if an unexpired, valid reservation exists.
    """
    def __init__(self, ttl_seconds: float = 60.0):
        self.ttl_seconds = ttl_seconds
        self._reservations: Dict[str, ActionReservation] = {}
        self._active_case_reservations: Dict[str, str] = {} # case_id -> reservation_id

    def reserve_action(
        self,
        case_id: str,
        action_type: ActionType,
        idempotency_key: str,
        policy_version: str,
        now: Optional[datetime] = None,
    ) -> ActionReservation:
        current_time = now or datetime.now(timezone.utc)

        # Check if an active unexpired reservation already exists for this case
        if case_id in self._active_case_reservations:
            existing_res_id = self._active_case_reservations[case_id]
            existing = self._reservations.get(existing_res_id)
            if existing and existing.status in ["RESERVED", "EXECUTING"] and existing.expires_at > current_time:
                raise DuplicateReservationError(
                    f"Active reservation {existing_res_id} already exists for case {case_id} (action: {existing.action_type.value})"
                )

        res_id = f"res_{uuid.uuid4().hex[:12]}"
        reservation = ActionReservation(
            reservation_id=res_id,
            case_id=case_id,
            action_type=action_type,
            idempotency_key=idempotency_key,
            policy_version=policy_version,
            created_at=current_time,
            expires_at=current_time + timedelta(seconds=self.ttl_seconds),
            status="RESERVED",
        )
        self._reservations[res_id] = reservation
        self._active_case_reservations[case_id] = res_id
        return reservation

    def validate_and_start_executing(self, reservation_id: str, now: Optional[datetime] = None) -> ActionReservation:
        current_time = now or datetime.now(timezone.utc)
        if reservation_id not in self._reservations:
            raise InvalidReservationError(f"Reservation {reservation_id} does not exist")

        res = self._reservations[reservation_id]
        if res.status != "RESERVED":
            raise InvalidReservationError(f"Reservation {reservation_id} is in status {res.status}, cannot execute")
        if res.expires_at <= current_time:
            res.status = "EXPIRED"
            raise InvalidReservationError(f"Reservation {reservation_id} has expired at {res.expires_at}")

        res.status = "EXECUTING"
        return res

    def confirm_reservation(self, reservation_id: str):
        if reservation_id in self._reservations:
            res = self._reservations[reservation_id]
            res.status = "CONFIRMED"
            if self._active_case_reservations.get(res.case_id) == reservation_id:
                del self._active_case_reservations[res.case_id]

    def release_or_cancel(self, reservation_id: str):
        if reservation_id in self._reservations:
            res = self._reservations[reservation_id]
            res.status = "CANCELLED"
            if self._active_case_reservations.get(res.case_id) == reservation_id:
                del self._active_case_reservations[res.case_id]
