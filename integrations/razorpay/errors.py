class RazorpayIntegrationError(Exception):
    """Base exception for all Razorpay test-mode integration errors."""
    pass

class ProductionEnvironmentForbiddenError(RazorpayIntegrationError):
    """Raised when production environment or live credentials are detected."""
    pass

class RazorpayAuthError(RazorpayIntegrationError):
    """Raised when authentication with Razorpay test mode fails."""
    pass

class RazorpayApiError(RazorpayIntegrationError):
    """Raised when Razorpay returns a non-2xx response."""
    def __init__(self, status_code: int, error_code: str, description: str):
        super().__init__(f"Razorpay API Error ({status_code}) [{error_code}]: {description}")
        self.status_code = status_code
        self.error_code = error_code
        self.description = description

class RazorpayTimeoutError(RazorpayIntegrationError):
    """Raised when an HTTP request to Razorpay times out."""
    pass

class RazorpayRateLimitError(RazorpayIntegrationError):
    """Raised when Razorpay returns 429 Too Many Requests."""
    pass

class AmbiguousExecutionError(RazorpayIntegrationError):
    """Raised when network or gateway state is unresolved and needs reconciliation."""
    pass

class InvalidRequestError(RazorpayIntegrationError):
    """Raised when invalid request parameters or unsupported partial-payment modes are supplied."""
    pass

class WebhookVerificationError(RazorpayIntegrationError):
    """Raised when webhook signature verification fails."""
    pass
