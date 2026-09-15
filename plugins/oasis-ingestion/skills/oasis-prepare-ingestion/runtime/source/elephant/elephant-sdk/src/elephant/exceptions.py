# src/elephant/exceptions.py
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    # Avoid circular imports at runtime
    from .models import Problem


class ElephantError(Exception):
    """Base exception for the elephant-sdk package."""

    pass


class ElephantDeprecatedError(ElephantError):
    """Raised when a deprecated feature is used."""

    pass


class ElephantConfigError(ElephantError):
    """Raised for configuration-related errors."""

    pass


class ElephantNetworkError(ElephantError):
    def __init__(self, message: str, url: str):
        super().__init__(f"{message} ({url})")


class ElephantHTTPError(ElephantError):
    def __init__(
        self,
        status: int,
        message: str,
        *,
        url: Optional[str] = None,
        code: Optional[int] = None,
        request_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        problem: Optional["Problem"] = None,
        retry_after: Optional[str] = None,
    ):
        parts = [f"HTTP {status}" if status else "HTTP error", message]
        if code:
            parts.append(f"[code={code}]")
        if request_id:
            parts.append(f"[request_id={request_id}]")
        super().__init__(f"{' '.join(parts)} ({url})")
        self.status = status
        self.code = code
        self.request_id = request_id
        self.details = details or {}
        self.url = url
        self.message = message
        self.problem: Optional[Problem] = problem
        self._retry_after: Optional[str] = retry_after

    @property
    def retry_after(self) -> Optional[str]:
        # Prefer explicit field, fall back to details payload
        return self._retry_after or (
            str(self.details.get("retry_after"))
            if self.details.get("retry_after") is not None
            else None
        )

    def type(self) -> Optional[str]:
        """Return Problem.type if present."""
        return getattr(self.problem, "type", None) if self.problem else None

    def title(self) -> Optional[str]:
        return getattr(self.problem, "title", None) if self.problem else None

    def detail(self) -> Optional[str]:
        return getattr(self.problem, "detail", None) if self.problem else None

    def is_type(self, t: str) -> bool:
        """Check `problem.type` URI equality."""
        pt = self.type()
        return bool(pt and pt == t)

    def is_auth(self) -> bool:
        return self.status in (401, 403)

    def is_rate_limited(self) -> bool:
        return self.status == 429

    def __str__(self) -> str:
        rid = f", request_id={self.request_id}" if self.request_id else ""
        return (
            f"{self.status} {self.message} (url={self.url}{rid})"
            if self.url
            else f"{self.status} {self.message}{rid}"
        )

    def __repr__(self) -> str:
        return (
            f"ElephantHTTPError(status={self.status}, message={self.message!r}, "
            f"url={self.url!r}, code={self.code!r}, request_id={self.request_id!r})"
        )

    @classmethod
    def from_problem(
        cls,
        *,
        url: str,
        problem: "Problem",
        request_id: Optional[str],
        retry_after: Optional[str],
        code: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> "ElephantHTTPError":
        """
        Build an error directly from a typed Problem (used in _make_request).
        """
        msg = problem.title or f"HTTP {problem.status}"
        if getattr(problem, "detail", None):
            msg = f"{msg}: {problem.detail}"
        return cls(
            status=int(problem.status or 0),
            message=msg,
            url=url,
            code=code or int(problem.status or 0),
            request_id=request_id or getattr(problem, "request_id", None),
            details=details or problem.model_dump(mode="json", exclude_none=True),
            problem=problem,
            retry_after=retry_after,
        )


class ElephantAuthError(ElephantHTTPError):
    """Raised for authentication-related errors."""


class ElephantConfigWarning(UserWarning):
    """Base warning for things that might cause issues"""
    pass