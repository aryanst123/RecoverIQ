import hashlib
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
from domain.enums import ActionType

@dataclass
class IdempotencyRecord:
    idempotency_key: str
    case_id: str
    action_type: ActionType
    action_sequence: int
    created_at: datetime
    execution_id: Optional[str] = None
    status: str = "PENDING" # PENDING, SUCCESS, FAILED, UNKNOWN
    response_payload: Optional[Dict[str, Any]] = None

class MerchantIdempotencyService:
    """
    Merchant-side idempotency manager.
    Guarantees that re-submitting the same logical action produces exactly one
    downstream execution and returns the original cached result.
    """
    def __init__(self):
        self._records: Dict[str, IdempotencyRecord] = {}

    @staticmethod
    def generate_key(case_id: str, action_type: ActionType, action_sequence: int) -> str:
        """
        Generates a deterministic idempotency key for a logical recovery attempt.
        """
        raw = f"{case_id}:{action_type.value}:{action_sequence}"
        hashed = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        return f"idem_{case_id}_{action_type.value}_{action_sequence}_{hashed}"

    def register_or_get(
        self,
        idempotency_key: str,
        case_id: str,
        action_type: ActionType,
        action_sequence: int,
    ) -> tuple[IdempotencyRecord, bool]:
        """
        Attempts to register an idempotency key.
        Returns (record, is_new).
        If is_new is False, this is a duplicate request and must not re-execute!
        """
        if idempotency_key in self._records:
            return self._records[idempotency_key], False

        record = IdempotencyRecord(
            idempotency_key=idempotency_key,
            case_id=case_id,
            action_type=action_type,
            action_sequence=action_sequence,
            created_at=datetime.now(timezone.utc),
            status="PENDING",
        )
        self._records[idempotency_key] = record
        return record, True

    def mark_completed(
        self,
        idempotency_key: str,
        execution_id: str,
        status: str,
        payload: Optional[Dict[str, Any]] = None,
    ):
        if idempotency_key in self._records:
            rec = self._records[idempotency_key]
            rec.execution_id = execution_id
            rec.status = status
            rec.response_payload = payload

    def get_record(self, idempotency_key: str) -> Optional[IdempotencyRecord]:
        return self._records.get(idempotency_key)
