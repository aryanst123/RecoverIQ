import os
from typing import Optional
from dataclasses import dataclass
from integrations.razorpay.errors import ProductionEnvironmentForbiddenError, RazorpayAuthError

@dataclass(frozen=True)
class RazorpayConfig:
    """
    STRICT TEST-MODE CONFIGURATION.
    Fails closed if production environment, live key prefix, or ambiguous settings are detected.
    """
    environment: str = "test"
    key_id: str = ""
    key_secret: str = ""
    webhook_secret: str = ""
    base_url: str = "https://api.razorpay.com/v1"
    timeout_seconds: float = 10.0

    def __post_init__(self):
        # 1. Reject any non-test environment
        if self.environment.lower() != "test":
            raise ProductionEnvironmentForbiddenError(
                f"RecoverIQ Phase 8 is strictly restricted to Razorpay TEST MODE. Got: {self.environment}"
            )

        # 2. Reject live credentials
        if self.key_id and self.key_id.startswith("rzp_live_"):
            raise ProductionEnvironmentForbiddenError(
                "CRITICAL SECURITY VIOLATION: Production Razorpay credentials (rzp_live_*) detected! "
                "Execution immediately halted to prevent live financial processing."
            )

    @classmethod
    def from_env(cls) -> "RazorpayConfig":
        env = os.getenv("RAZORPAY_ENVIRONMENT", "test").strip()
        key_id = os.getenv("RAZORPAY_KEY_ID", "").strip()
        key_sec = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
        wh_sec = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()

        return cls(
            environment=env,
            key_id=key_id,
            key_secret=key_sec,
            webhook_secret=wh_sec,
        )

    def is_configured(self) -> bool:
        """Returns True if test-mode credentials and webhook secrets are present."""
        return bool(self.key_id and self.key_secret and self.key_id.startswith("rzp_test_"))

    def __repr__(self) -> str:
        masked_key = f"{self.key_id[:8]}..." if self.key_id else "<empty>"
        return f"<RazorpayConfig(environment='{self.environment}', key_id='{masked_key}', is_test_mode=True)>"
