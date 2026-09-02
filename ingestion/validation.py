import hmac
import hashlib
from typing import Union

class InvalidSignatureError(Exception):
    pass

class WebhookSignatureValidator:
    """
    Razorpay-compatible webhook signature validator.
    Computes HMAC-SHA256 over raw request body bytes and compares
    against x-razorpay-signature using constant-time comparison.
    """
    def __init__(self, secret: str = "rzp_wh_secret_test_2026"):
        self.secret = secret

    def compute_signature(self, raw_body: Union[str, bytes]) -> str:
        body_bytes = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
        secret_bytes = self.secret.encode("utf-8")
        return hmac.new(secret_bytes, body_bytes, hashlib.sha256).hexdigest()

    def verify_signature(self, raw_body: Union[str, bytes], signature: str) -> bool:
        if not signature or not isinstance(signature, str):
            return False
        expected_sig = self.compute_signature(raw_body)
        # Constant-time comparison prevents timing side-channel attacks
        return hmac.compare_digest(expected_sig, signature)

    def validate_or_raise(self, raw_body: Union[str, bytes], signature: str):
        if not self.verify_signature(raw_body, signature):
            raise InvalidSignatureError("Webhook signature verification failed (HMAC-SHA256 mismatch)")
