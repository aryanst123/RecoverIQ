import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

@dataclass
class StructuredAuditRecord:
    audit_id: str
    timestamp: str
    case_id: str
    actor: str
    event_type: str
    policy_version: str
    action_type: Optional[str] = None
    reservation_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    observed_payment_state: Optional[str] = None
    execution_state: Optional[str] = None
    reconciliation_result: Optional[str] = None
    final_outcome: Optional[str] = None
    rejection_reason: Optional[str] = None
    metadata: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class AuditTrailService:
    """
    Centralized audit logging service.
    Maintains an immutable in-memory or persisted ledger of all decisions,
    reconciliations, reservations, executions, and security checks.
    """
    def __init__(self):
        self._records: List[StructuredAuditRecord] = []
        self._case_index: Dict[str, List[StructuredAuditRecord]] = {}

    def log(
        self,
        case_id: str,
        actor: str,
        event_type: str,
        policy_version: str,
        action_type: Optional[str] = None,
        reservation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        observed_payment_state: Optional[str] = None,
        execution_state: Optional[str] = None,
        reconciliation_result: Optional[str] = None,
        final_outcome: Optional[str] = None,
        rejection_reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        now: Optional[datetime] = None,
    ) -> StructuredAuditRecord:
        record = StructuredAuditRecord(
            audit_id=f"aud_{uuid.uuid4().hex[:12]}",
            timestamp=(now or datetime.now(timezone.utc)).isoformat(),
            case_id=case_id,
            actor=actor,
            event_type=event_type,
            policy_version=policy_version,
            action_type=action_type,
            reservation_id=reservation_id,
            idempotency_key=idempotency_key,
            observed_payment_state=observed_payment_state,
            execution_state=execution_state,
            reconciliation_result=reconciliation_result,
            final_outcome=final_outcome,
            rejection_reason=rejection_reason,
            metadata=metadata or {},
        )
        self._records.append(record)
        if case_id not in self._case_index:
            self._case_index[case_id] = []
        self._case_index[case_id].append(record)
        return record

    def get_case_audit(self, case_id: str) -> List[StructuredAuditRecord]:
        return self._case_index.get(case_id, [])

    def get_all_records(self) -> List[StructuredAuditRecord]:
        return list(self._records)
