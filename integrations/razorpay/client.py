import abc
import json
import base64
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from integrations.razorpay.config import RazorpayConfig
from integrations.razorpay.models import (
    RazorpayPaymentLinkResponse,
    RazorpayPaymentResponse,
)
from integrations.razorpay.errors import (
    RazorpayIntegrationError,
    RazorpayAuthError,
    RazorpayApiError,
    RazorpayTimeoutError,
    RazorpayRateLimitError,
    InvalidRequestError,
)

class RazorpayClientInterface(abc.ABC):
    """Abstract interface for Razorpay API interactions."""

    @abc.abstractmethod
    def fetch_payment(self, payment_id: str) -> RazorpayPaymentResponse:
        pass

    @abc.abstractmethod
    def create_payment_link(
        self,
        amount: float,
        reference_id: str,
        customer_phone: str,
        customer_email: Optional[str] = None,
        description: str = "Payment Recovery Link",
        currency: str = "INR",
        notes: Optional[Dict[str, str]] = None,
        expire_by: Optional[datetime] = None,
        accept_partial: bool = False,
    ) -> RazorpayPaymentLinkResponse:
        pass

    @abc.abstractmethod
    def fetch_payment_link(self, link_id: str) -> RazorpayPaymentLinkResponse:
        pass

    @abc.abstractmethod
    def cancel_payment_link(self, link_id: str) -> bool:
        pass

class MockRazorpayGateway(RazorpayClientInterface):
    """
    IN-MEMORY TEST-MODE GATEWAY MOCK.
    Provides complete offline integration testing without network or credentials.
    Simulates timeouts, errors, duplicate creations, and captures.
    """
    def __init__(self):
        self.payments: Dict[str, Dict[str, Any]] = {}
        self.payment_links: Dict[str, Dict[str, Any]] = {}
        self.idempotency_index: Dict[str, str] = {} # reference_id -> link_id
        self.simulate_timeout: bool = False
        self.simulate_rate_limit: bool = False
        self.simulate_auth_error: bool = False

    def register_test_payment(
        self,
        payment_id: str,
        amount: float,
        status: str = "failed",
        currency: str = "INR",
        error_code: Optional[str] = None,
        error_description: Optional[str] = None,
    ):
        self.payments[payment_id] = {
            "id": payment_id,
            "amount": int(round(amount * 100)),
            "currency": currency,
            "status": status,
            "error_code": error_code,
            "error_description": error_description,
            "created_at": int(datetime.now(timezone.utc).timestamp()),
        }

    def fetch_payment(self, payment_id: str) -> RazorpayPaymentResponse:
        if self.simulate_timeout:
            raise RazorpayTimeoutError("Mock request timed out")
        if self.simulate_auth_error:
            raise RazorpayAuthError("Invalid Razorpay test credentials")
        if self.simulate_rate_limit:
            raise RazorpayRateLimitError("Mock rate limit exceeded (429)")

        p = self.payments.get(payment_id)
        if not p:
            raise RazorpayApiError(404, "BAD_REQUEST_ERROR", f"Payment {payment_id} not found")

        return RazorpayPaymentResponse(
            payment_id=p["id"],
            amount=round(float(p["amount"]) / 100.0, 2),
            currency=p.get("currency", "INR"),
            status=p.get("status", "failed"),
            error_code=p.get("error_code"),
            error_description=p.get("error_description"),
            created_at=datetime.fromtimestamp(p["created_at"], tz=timezone.utc),
        )

    def create_payment_link(
        self,
        amount: float,
        reference_id: str,
        customer_phone: str,
        customer_email: Optional[str] = None,
        description: str = "Payment Recovery Link",
        currency: str = "INR",
        notes: Optional[Dict[str, str]] = None,
        expire_by: Optional[datetime] = None,
        accept_partial: bool = False,
    ) -> RazorpayPaymentLinkResponse:
        if self.simulate_timeout:
            raise RazorpayTimeoutError("Mock payment link creation timed out")
        if self.simulate_auth_error:
            raise RazorpayAuthError("Invalid Razorpay test credentials")
        if self.simulate_rate_limit:
            raise RazorpayRateLimitError("Rate limit exceeded")

        if amount <= 0:
            raise InvalidRequestError("Payment Link amount must be greater than 0")

        # Provider Idempotency via reference_id:
        if reference_id in self.idempotency_index:
            existing_id = self.idempotency_index[reference_id]
            existing = self.payment_links[existing_id]
            return RazorpayPaymentLinkResponse(
                link_id=existing["id"],
                short_url=existing["short_url"],
                amount=round(float(existing["amount"]) / 100.0, 2),
                currency=existing["currency"],
                status=existing["status"],
                reference_id=existing["reference_id"],
                created_at=datetime.fromtimestamp(existing["created_at"], tz=timezone.utc),
            )

        link_id = f"plink_mock_{reference_id}_{len(self.payment_links) + 1}"
        short_url = f"https://rzp.io/i/{link_id}"
        paise = int(round(amount * 100))

        record = {
            "id": link_id,
            "short_url": short_url,
            "amount": paise,
            "currency": currency,
            "status": "created",
            "reference_id": reference_id,
            "customer": {"contact": customer_phone, "email": customer_email},
            "description": description,
            "notes": notes or {},
            "accept_partial": accept_partial,
            "created_at": int(datetime.now(timezone.utc).timestamp()),
            "expire_by": int(expire_by.timestamp()) if expire_by else None,
        }
        self.payment_links[link_id] = record
        self.idempotency_index[reference_id] = link_id

        return RazorpayPaymentLinkResponse(
            link_id=link_id,
            short_url=short_url,
            amount=amount,
            currency=currency,
            status="created",
            reference_id=reference_id,
            created_at=datetime.now(timezone.utc),
            expire_by=expire_by,
        )

    def fetch_payment_link(self, link_id: str) -> RazorpayPaymentLinkResponse:
        pl = self.payment_links.get(link_id)
        if not pl:
            raise RazorpayApiError(404, "BAD_REQUEST_ERROR", f"Payment link {link_id} not found")

        return RazorpayPaymentLinkResponse(
            link_id=pl["id"],
            short_url=pl["short_url"],
            amount=round(float(pl["amount"]) / 100.0, 2),
            currency=pl["currency"],
            status=pl["status"],
            reference_id=pl["reference_id"],
            created_at=datetime.fromtimestamp(pl["created_at"], tz=timezone.utc),
        )

    def cancel_payment_link(self, link_id: str) -> bool:
        if link_id in self.payment_links:
            self.payment_links[link_id]["status"] = "cancelled"
            return True
        return False

class RazorpayTestClient(RazorpayClientInterface):
    """
    LIVE RAZORPAY TEST-MODE CLIENT.
    Only instantiated when RAZORPAY_ENVIRONMENT=test and test credentials exist.
    """
    def __init__(self, config: RazorpayConfig):
        self.config = config
        if not self.config.is_configured():
            raise RazorpayAuthError("Razorpay test credentials are not properly configured")

        auth_str = f"{self.config.key_id}:{self.config.key_secret}"
        self._auth_header = "Basic " + base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")

    def _request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.config.base_url}{endpoint}"
        req = urllib.request.Request(url, method=method)
        req.add_header("Authorization", self._auth_header)
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "RecoverIQ-Razorpay-Test-Adapter/1.0")

        req_body = json.dumps(data).encode("utf-8") if data is not None else None

        try:
            with urllib.request.urlopen(req, data=req_body, timeout=self.config.timeout_seconds) as resp:
                resp_data = resp.read().decode("utf-8")
                return json.loads(resp_data)
        except urllib.error.HTTPError as http_err:
            body = http_err.read().decode("utf-8")
            if http_err.code == 401:
                raise RazorpayAuthError("Authentication failed with Razorpay test mode")
            if http_err.code == 429:
                raise RazorpayRateLimitError("Razorpay rate limit exceeded (429)")
            try:
                err_json = json.loads(body).get("error", {})
                raise RazorpayApiError(
                    status_code=http_err.code,
                    error_code=err_json.get("code", "API_ERROR"),
                    description=err_json.get("description", str(http_err)),
                )
            except json.JSONDecodeError:
                raise RazorpayApiError(http_err.code, "RAW_ERROR", body)
        except urllib.error.URLError as url_err:
            raise RazorpayTimeoutError(f"Network error connecting to Razorpay test API: {url_err}")

    def fetch_payment(self, payment_id: str) -> RazorpayPaymentResponse:
        data = self._request("GET", f"/payments/{payment_id}")
        return RazorpayPaymentResponse(
            payment_id=data["id"],
            amount=round(float(data["amount"]) / 100.0, 2),
            currency=data.get("currency", "INR"),
            status=data.get("status", "failed"),
            order_id=data.get("order_id"),
            error_code=data.get("error_code"),
            error_description=data.get("error_description"),
        )

    def create_payment_link(
        self,
        amount: float,
        reference_id: str,
        customer_phone: str,
        customer_email: Optional[str] = None,
        description: str = "Payment Recovery Link",
        currency: str = "INR",
        notes: Optional[Dict[str, str]] = None,
        expire_by: Optional[datetime] = None,
        accept_partial: bool = False,
    ) -> RazorpayPaymentLinkResponse:
        payload = {
            "amount": int(round(amount * 100)),
            "currency": currency,
            "accept_partial": accept_partial,
            "reference_id": reference_id,
            "description": description,
            "customer": {"contact": customer_phone},
            "notify": {"sms": True, "email": bool(customer_email)},
            "reminder_enable": False,
            "notes": notes or {},
        }
        if customer_email:
            payload["customer"]["email"] = customer_email
        if expire_by:
            payload["expire_by"] = int(expire_by.timestamp())

        data = self._request("POST", "/payment_links", payload)
        return RazorpayPaymentLinkResponse(
            link_id=data["id"],
            short_url=data["short_url"],
            amount=round(float(data["amount"]) / 100.0, 2),
            currency=data.get("currency", "INR"),
            status=data.get("status", "created"),
            reference_id=data.get("reference_id", reference_id),
            created_at=datetime.fromtimestamp(data["created_at"], tz=timezone.utc),
        )

    def fetch_payment_link(self, link_id: str) -> RazorpayPaymentLinkResponse:
        data = self._request("GET", f"/payment_links/{link_id}")
        return RazorpayPaymentLinkResponse(
            link_id=data["id"],
            short_url=data["short_url"],
            amount=round(float(data["amount"]) / 100.0, 2),
            currency=data.get("currency", "INR"),
            status=data.get("status", "created"),
            reference_id=data.get("reference_id", ""),
            created_at=datetime.fromtimestamp(data["created_at"], tz=timezone.utc),
        )

    def cancel_payment_link(self, link_id: str) -> bool:
        data = self._request("POST", f"/payment_links/{link_id}/cancel")
        return data.get("status") == "cancelled"
