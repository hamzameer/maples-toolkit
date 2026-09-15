# src/elephant/utils.py
import warnings
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import (
    Any,
    Callable,
    List,
    Optional,
    Tuple,
    TypedDict,
    TypeVar,
    Union,
)
from uuid import UUID

import requests
from pydantic import (
    AnyUrl,
    BaseModel,
    Field,
    TypeAdapter,
    ValidationError,
    computed_field,
    model_validator,
)
from typing_extensions import ParamSpec

from .exceptions import ElephantConfigError
from .models import FileTypeCode, Problem, UploadByIdBulkMeta

_NUM_ARGS_PREPARED = 1
_NUM_ARGS_META_AND_FILES = 2
MAX_MESSAGE_LENGTH = 500
T = TypeVar("T")

DEFAULT_PROBLEM_TYPE = "https://elephant.api/errors/unknown"
FsPath = Union[str, Path]
FileTypeLike = Union[str, FileTypeCode]


def normalize_email(email: Any) -> str:
    return str(email).strip().lower()


def normalize_natural_key(value: Any) -> str:
    return str(value).strip().lower()


def trim_display_value(value: Any) -> str:
    return str(value).strip()


def normalize_file_type_code(code: Union[str, FileTypeCode]) -> str:
    raw = code.value if isinstance(code, FileTypeCode) else str(code)
    return normalize_natural_key(raw)


def coerce_file_type(ft: Optional[FileTypeLike]) -> Optional[FileTypeCode]:
    """Accept str|FileTypeCode|None -> FileTypeCode|None; raise ElephantConfigError if invalid."""
    if ft is None:
        return None
    if isinstance(ft, FileTypeCode):
        return ft
    if isinstance(ft, str):
        norm = normalize_file_type_code(ft)
        try:
            # Construct by VALUE; raises ValueError if not one of the enum values
            return FileTypeCode(norm)
        except ValueError:
            allowed = ", ".join(e.value for e in FileTypeCode)
            raise ElephantConfigError(
                f"Invalid file_type={ft!r}. Allowed values: {allowed}"
            ) from None
    raise TypeError(f"file_type must be str or FileTypeCode, not {type(ft).__name__}")


def require_file_type(ft: Optional[FileTypeLike]) -> FileTypeCode:
    """Like coerce_file_type, but also errors on None / empty."""
    if ft is None:
        raise ElephantConfigError("file_type is required")
    if isinstance(ft, str) and not ft.strip():
        raise ElephantConfigError("file_type is required (got empty string)")
    ft = coerce_file_type(ft)
    if ft is None:
        raise ElephantConfigError("file_type is required")
    return ft


class RequestKwargs(TypedDict, total=False):
    timeout: float
    headers: dict[str, str]
    json: Any
    files: Any
    params: dict[str, Any]


@dataclass(frozen=True)
class PreparedBulkById:
    meta: List[UploadByIdBulkMeta]
    paths: List[FsPath]


class FileToUpload(BaseModel):
    file_path: FsPath
    file_type: Union[FileTypeCode, str]
    file_name: str
    additional_file_identifier: Optional[int] = Field(
        default=None, description="Optional caller-defined integer identifier."
    )
    file_type_norm: FileTypeCode = Field(default=FileTypeCode.other, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _normalize_into_hidden(cls, data: Any):
        """Populate _file_type_norm from incoming file_type without altering the raw field."""
        if not isinstance(data, dict):
            return data
        raw = data.get("file_type")

        # 1) Already our enum
        if isinstance(raw, FileTypeCode):
            data["file_type_norm"] = raw
            return data

        # 2) Foreign Enum with same value
        if isinstance(raw, Enum):
            data["file_type_norm"] = FileTypeCode(raw.value)
            return data

        # 3) String value
        if isinstance(raw, str):
            data["file_type_norm"] = FileTypeCode(
                normalize_file_type_code(raw)
            )  # raises ValueError if not allowed
            return data

        # 4) Anything else → let pydantic raise a clearer error later
        return data

    @computed_field(return_type=FileTypeCode)
    @property
    def file_type_enum(self) -> FileTypeCode:
        """Public read-only view if callers want the normalized enum."""
        return self.file_type_norm


def coerce_uuid(val: Union[str, UUID, None], field: str) -> Optional[UUID]:
    if val is None:
        return None
    if isinstance(val, UUID):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None  # treat empty string as "unset"
        try:
            return UUID(s)  # accepts dashed/undashed/case-insensitive
        except ValueError as e:
            raise ElephantConfigError(f"Invalid {field} UUID: {val!r}") from e
    raise ElephantConfigError(f"{field} must be a UUID or string, not {type(val).__name__}")


# def normalize_bulk_by_id_args(
#     args: Tuple[Any, ...],
# ) -> tuple[List[UploadByIdBulkMeta], List[str]]:
#     # A) PreparedBulkById(prepared)
#     if len(args) == _NUM_ARGS_PREPARED and isinstance(args[0], PreparedBulkById):
#         prepared = args[0]
#         return prepared.meta, prepared.paths

#     # B) (meta_seq, files_seq)
#     if len(args) == _NUM_ARGS_META_AND_FILES:
#         meta_seq, files_seq = args
#         if not isinstance(meta_seq, Sequence) or not isinstance(files_seq, Sequence):
#             raise ElephantConfigError("Expected (metadata_sequence, files_sequence).")
#         if len(meta_seq) != len(files_seq):
#             raise ElephantConfigError("metadata count must match files count")
#         adapter = TypeAdapter(List[UploadByIdBulkMeta])
#         try:
#             meta_models = adapter.validate_python(list(meta_seq))
#         except ValidationError as exc:
#             raise ElephantConfigError(f"Invalid UploadByIdBulkMeta payload: {exc}") from exc
#         return meta_models, [str(p) for p in files_seq]

#     # Unknown shape
#     raise ElephantConfigError(
#         "Usage: upload_files_by_id_bulk(prepared) or upload_files_by_id_bulk(meta_seq, files_seq)."
#     )


def _is_problem(resp: requests.Response) -> bool:
    ct = (resp.headers.get("Content-Type") or "").lower()
    return ct.startswith("application/problem+json")


def _content_type(resp: requests.Response) -> str:
    # Strip any parameters (e.g., "; charset=utf-8") and lowercase
    ct = (resp.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    return ct


def _looks_like_problem_json(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    # Minimal RFC7807 'shape'
    return any(k in data for k in ("title", "detail", "status", "type"))


def _normalize_problem_type(v: object) -> str:
    s = str(v).strip() if isinstance(v, str) else ""
    if not s or s.lower() == "about:blank":
        return DEFAULT_PROBLEM_TYPE
    return s  # leave other URLs alone


def _compose_message(title: Optional[str], detail: Optional[str], status: int) -> str:
    title = (title or "").strip()
    detail = (detail or "").strip()
    if title and detail:
        msg = f"{title}: {detail}"
    elif detail:
        msg = detail
    elif title:
        msg = title
    else:
        msg = f"HTTP {status}"
    if len(msg) > MAX_MESSAGE_LENGTH:
        msg = msg[:MAX_MESSAGE_LENGTH] + "…"
    return msg


def safe_json(resp: requests.Response) -> Optional[Any]:
    try:
        return resp.json()
    except Exception:
        return None


ProblemAdapter = TypeAdapter(Problem)


def _as_problem_url(value: Union[str, AnyUrl, None]) -> AnyUrl:
    if isinstance(value, AnyUrl):
        return value
    if value:
        return AnyUrl(value)
    return AnyUrl(DEFAULT_PROBLEM_TYPE)


def parse_problem(
    resp: requests.Response,
) -> Tuple[str, int, Problem, Optional[str], Optional[str]]:
    """
    Returns: (message, status_code, problem_model, request_id, retry_after)
    Always returns a typed `Problem` (synthesized if necessary).
    """
    req_id = resp.headers.get("X-Request-Id")
    retry_after = resp.headers.get("Retry-After")
    status = int(resp.status_code or 0)

    # Case 1: Proper problem+json
    if _is_problem(resp):
        data = safe_json(resp) or {}
        if isinstance(data, dict):
            # Normalize for your model (AnyUrl for `type`)
            data.setdefault("status", status)
            data["type"] = _normalize_problem_type(data.get("type"))
            data.setdefault("request_id", req_id)

            try:
                prob = ProblemAdapter.validate_python(data)
            except ValidationError:
                # Be resilient: synthesize with original text body
                text = (resp.text or "").strip()
                prob = Problem(
                    type=AnyUrl(DEFAULT_PROBLEM_TYPE),
                    title="HTTP error",
                    status=status,
                    detail=text[:MAX_MESSAGE_LENGTH]
                    + ("…" if len(text) > MAX_MESSAGE_LENGTH else ""),
                    request_id=req_id,
                )
            msg = _compose_message(prob.title, prob.detail, status)
            return msg, status, prob, req_id, retry_after

    # Case 2: JSON but not labeled as problem
    data = safe_json(resp)
    if isinstance(data, dict) and _looks_like_problem_json(data):
        # Normalize minimal fields into a valid Problem
        title = data.get("title") or data.get("error") or "HTTP error"
        detail = data.get("detail") or data.get("message")
        norm = {
            "type": _normalize_problem_type(data.get("type")),
            "title": title,
            "status": int(data.get("status") or status),
            "detail": detail,
            "instance": data.get("instance"),
            "request_id": data.get("request_id") or req_id,
        }
        try:
            prob = ProblemAdapter.validate_python(norm)
        except ValidationError:
            problem_type = _as_problem_url(_normalize_problem_type(data.get("type")))
            prob = Problem(
                type=problem_type,
                title=str(title),
                status=int(norm["status"]),
                detail=str(detail) if detail else None,
                request_id=req_id,
            )
        msg = _compose_message(prob.title, prob.detail, prob.status)
        return msg, prob.status, prob, req_id, retry_after

    # Case 3: Anything else (plain text, HTML, etc.)
    text = (resp.text or "").strip()
    trimmed = text[:MAX_MESSAGE_LENGTH] + ("…" if len(text) > MAX_MESSAGE_LENGTH else "")
    prob = Problem(
        type=AnyUrl(DEFAULT_PROBLEM_TYPE),
        title=f"HTTP {status}",
        status=status,
        detail=trimmed or None,
        request_id=req_id,
    )
    msg = _compose_message(prob.title, prob.detail, status)
    return msg, status, prob, req_id, retry_after


def strip_or_none(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s2 = s.strip()
    return s2 if s2 else None


P = ParamSpec("P")
R = TypeVar("R")


def deprecated(
    reason: Optional[str] = None,
    version: Optional[str] = None,
    removal_version: Optional[str] = None,
):
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            name = getattr(func, "__name__", "deprecated callable")
            message = f"Call to deprecated function '{name}'."
            if reason:
                message += f" {reason}"
            if version:
                message += f" (deprecated since v{version})"
            if removal_version:
                message += f" - will be removed in v{removal_version}"

            warnings.warn(message, category=DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)

        if wrapper.__doc__:
            wrapper.__doc__ = f"**DEPRECATED**: {wrapper.__doc__}\n\n{reason or ''}"

        return wrapper

    return decorator
