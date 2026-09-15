# src/elephant/client.py
import mimetypes
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from pathlib import Path
from typing import (
    IO,
    Any,
    List,
    Literal,
    Optional,
    Sequence,
    Tuple,
    Union,
)
from uuid import UUID

import requests
from pydantic import EmailStr, HttpUrl, SecretStr, TypeAdapter, ValidationError

from .exceptions import (
    ElephantAuthError,
    ElephantConfigError,
    ElephantError,
    ElephantHTTPError,
    ElephantNetworkError,
)
from .helpers import prepare_bulk_upload_by_id as _prepare_bulk_upload_by_id
from .models import (
    ApiKey,
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyRole,
    BulkLearnerUpsertItem,
    BulkLearnerUpsertRequest,
    BulkLearnerUpsertResponse,
    BulkUploadResponse,
    CohortUpsertRequest,
    CohortUpsertResponse,
    CreateEncounterRequest,
    Defaults,
    EncounterResponse,
    EncounterSearchRequest,
    EncounterSearchResponse,
    FileType,
    FileTypeCode,
    FileUploadResult,
    FileValidationRequest,
    FileValidationResponse,
    GroupedFiles,
    LearnerSummary,
    LearnerUpsertWithEffectResponse,
    PresignedUrlResponse,
    SearchFilesRequest,
    TextOverrides,
    UploadByIdBulkMeta,
    UploadByIdMeta,
)
from .utils import (
    MAX_MESSAGE_LENGTH,
    FileToUpload,
    FsPath,
    PreparedBulkById,
    RequestKwargs,
    coerce_file_type,
    coerce_uuid,
    normalize_email,
    parse_problem,
    require_file_type,
    safe_json,
    strip_or_none,
    trim_display_value,
)

DEFAULT_API_KEY_TTL = timedelta(days=90)


class ElephantClient:
    """
    Client for interacting with the Elephant API.
    """

    def __init__(
        self,
        api_key: Union[str, SecretStr],
        base_url: Union[str, HttpUrl] = "https://api.elephant.com",
        timeout: float = 90.0,
        api_version: str = "v1",
    ):
        """Initialize the Elephant API client.

        Args:
            api_key: API key for authentication.
            base_url: Base URL of the Elephant API server. Defaults to "https://api.elephant.com".
            timeout: Request timeout in seconds. Defaults to 90.0.
            api_version: API version string. Defaults to "v1".

        Raises:
            ElephantError: If api_key is empty.
            ElephantConfigError: If base_url is not a valid URL.
        """
        validated_api_key = SecretStr(api_key) if isinstance(api_key, str) else api_key

        if not validated_api_key.get_secret_value():
            raise ElephantError("API key cannot be empty.")

        self.api_key: SecretStr = validated_api_key

        try:
            http_url_adapter = TypeAdapter(HttpUrl)
            validated_base_url = http_url_adapter.validate_python(base_url)

        except ValidationError as e:
            raise ElephantConfigError(f"Invalid base_url provided: {e}") from e

        self.base_url: HttpUrl = validated_base_url
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": self.api_key.get_secret_value()})
        self.timeout = timeout
        self.api_version = api_version.strip()

    def _url(self, path: str) -> str:
        return f"{str(self.base_url).rstrip('/')}/api/{self.api_version}/{path.lstrip('/')}"

    def _make_request(
        self,
        method: str,
        url: str,
        *,
        json_data: Optional[Any] = None,
        params: Optional[dict[str, Any]] = None,
        files: Optional[Any] = None,
        headers: Optional[dict] = None,
        timeout: Optional[float] = None,
        validate_with: Optional[Any] = None,
    ) -> Any:
        """
        Make an HTTP request with consistent error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL to request
            json_data: JSON data to send
            params: Query parameters to append to URL
            files: Files for multipart upload
            headers: Additional headers
            timeout: Request timeout (uses self.timeout if not specified)
            validate_with: Pydantic model or TypeAdapter to validate response
            error_mappings: Custom error messages for specific status codes
        """
        timeout = timeout or self.timeout
        headers = headers or {}

        request_kwargs: RequestKwargs = {
            "timeout": timeout,
            "headers": headers,
        }
        if json_data is not None:
            request_kwargs["json"] = json_data
        if files is not None:
            request_kwargs["files"] = files
        if params is not None:
            request_kwargs["params"] = params

        response = None
        try:
            response = self.session.request(method, url, **request_kwargs)

            if response.status_code >= HTTPStatus.BAD_REQUEST:
                _, status, problem, req_id, retry_after = parse_problem(response)
                exc_cls = ElephantAuthError if status in (401, 403) else ElephantHTTPError
                raise exc_cls.from_problem(
                    url=url,
                    problem=problem,
                    request_id=req_id,
                    retry_after=retry_after,
                    code=getattr(problem, "code", None) or status,
                )
                # Success
            if validate_with is None:
                return response

            data = safe_json(response)
            if data is None:
                raw = (response.text or "")[:MAX_MESSAGE_LENGTH]
                raw += "…" if len(response.text or "") > MAX_MESSAGE_LENGTH else ""
                raise ElephantError(f"Invalid JSON from {url}: {raw}")

                # Pydantic TypeAdapter or model:
            if hasattr(validate_with, "validate_python"):  # TypeAdapter
                return validate_with.validate_python(data)
            if hasattr(validate_with, "model_validate"):  # BaseModel subclass
                return validate_with.model_validate(data)
            return data

        except requests.Timeout as e:
            raise ElephantNetworkError(f"Timed out after {timeout}s", url=url) from e
        except requests.ConnectionError as e:
            raise ElephantNetworkError("Connection error", url=url) from e
        except requests.RequestException as e:
            # Other requests errors (e.g., invalid URL)
            raise ElephantError(f"Request error calling {url}: {e}") from e

    def get_file_types(self) -> List[FileType]:
        """Get file type definitions supported by the API.

        Returns:
            List of file type definitions, including code, display metadata, extensions,
            MIME hints, and whether each type is user-visible.
        """
        return self._make_request(
            "GET",
            self._url("file-types"),
            validate_with=TypeAdapter(List[FileType]),
        )

    def list_api_keys(self) -> List[ApiKey]:
        """List API key metadata. Requires an admin API key.

        Raw API key secrets are never returned by this endpoint.
        """
        return self._make_request(
            "GET",
            self._url("api-keys"),
            validate_with=TypeAdapter(List[ApiKey]),
        )

    def create_api_key(
        self,
        owner: str,
        role: Union[str, ApiKeyRole],
        expires_at: Optional[datetime] = None,
        never_expires: bool = False,
    ) -> ApiKeyCreateResponse:
        """Create a new API key. Requires an admin API key.

        The raw API key secret is returned once in ``response.api_key``. Store it
        securely; subsequent list/get calls return metadata only.
        """
        if never_expires and expires_at is not None:
            raise ElephantConfigError("expires_at cannot be set when never_expires is True.")
        if expires_at is None and not never_expires:
            expires_at = datetime.now(timezone.utc).replace(microsecond=0) + DEFAULT_API_KEY_TTL

        role_enum = self._coerce_api_key_role(role)
        model = ApiKeyCreateRequest(
            owner=owner,
            role=role_enum,
            expires_at=expires_at,
            never_expires=never_expires,
        )

        return self._make_request(
            "POST",
            self._url("api-keys"),
            json_data=model.model_dump(mode="json", exclude_unset=True, exclude_none=True),
            validate_with=ApiKeyCreateResponse,
        )

    def get_api_key(self, key_id: Union[str, UUID]) -> ApiKey:
        """Get API key metadata by key ID. Requires an admin API key."""
        key_uuid = self._require_api_key_uuid(key_id)
        return self._make_request(
            "GET",
            self._url(f"api-keys/{key_uuid}"),
            validate_with=ApiKey,
        )

    def revoke_api_key(self, key_id: Union[str, UUID], reason: Optional[str] = None) -> ApiKey:
        """Revoke an API key without deleting its immutable record.

        Requires an admin API key. The server rejects revoking the last active
        admin key.
        """
        key_uuid = self._require_api_key_uuid(key_id)
        params: dict[str, Any] = {}
        if reason:
            params["reason"] = reason

        return self._make_request(
            "DELETE",
            self._url(f"api-keys/{key_uuid}"),
            params=params if params else None,
            validate_with=ApiKey,
        )

    def rotate_api_key(
        self,
        key_id: Union[str, UUID],
        reason: Optional[str] = None,
    ) -> ApiKeyCreateResponse:
        """Rotate an active API key and return the replacement secret once.

        Requires an admin API key. The replacement preserves the original key's
        owner, role, and expiration.
        """
        key_uuid = self._require_api_key_uuid(key_id)
        params: dict[str, Any] = {}
        if reason:
            params["reason"] = reason

        return self._make_request(
            "POST",
            self._url(f"api-keys/{key_uuid}/rotate"),
            params=params if params else None,
            validate_with=ApiKeyCreateResponse,
        )

    def get_health(self) -> dict[str, Any]:
        """Check if the API service is running and accessible.

        Returns:
            Health check response containing status and service information.
        """
        url = self._url("health")
        return self._make_request("GET", url, validate_with=dict)

    def search_files(  # noqa: PLR0913
        self,
        learner: Optional[str] = None,
        activity_name: Optional[str] = None,
        case_name: Optional[str] = None,
        room: Optional[str] = None,
        date: Optional[str] = None,
        encounter_id: Union[str, UUID, None] = None,
        learner_id: Union[str, UUID, None] = None,
        file_type: Optional[Union[str, FileTypeCode]] = None,
        defaults: Optional[Defaults] = None,
        text_overrides: Optional[TextOverrides] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[GroupedFiles]:
        """Search for files with flexible filtering options.

        All text filters use case-insensitive substring matching by default.
        Customize matching behavior with defaults and text_overrides parameters.

        Args:
            learner: Filter by learner name.
            activity_name: Filter by activity name.
            case_name: Filter by case name.
            room: Filter by room.
            date: Filter by date.
            encounter_id: Filter by specific encounter UUID.
            learner_id: Filter by specific learner UUID.
            file_type: Filter by file type code (see get_file_types()).
            defaults: Global text matching defaults (case sensitivity, match mode).
            text_overrides: Per-field text matching overrides.
            limit: Maximum groups to return. Omit to return all matches.
            offset: Number of groups to skip for pagination (default 0).

        Returns:
            List of file groups for the requested page, or all matches when
            limit is omitted. Returns an empty list if no files match.

        Example:
            # Case-sensitive exact match for case_name
            results = client.search_files(
                case_name="Renal",
                text_overrides=TextOverrides(
                    case_name=TextFilter(value="Renal", match_mode="exact", case_mode="sensitive")
                )
            )
        """

        ft = coerce_file_type(file_type)
        model = SearchFilesRequest(
            learner=strip_or_none(learner),
            activity_name=strip_or_none(activity_name),
            case_name=strip_or_none(case_name),
            room=strip_or_none(room),
            date=strip_or_none(date),
            encounter_id=coerce_uuid(encounter_id, "encounter_id") if encounter_id else None,
            learner_id=coerce_uuid(learner_id, "learner_id") if learner_id else None,
            file_type=ft,
            defaults=defaults,
            text_overrides=text_overrides,
            limit=limit,
            offset=offset,
        )

        adapter = TypeAdapter(List[GroupedFiles])
        return self._make_request(
            "POST",
            self._url("files/search"),
            json_data=model.model_dump(mode="json", exclude_unset=True),
            validate_with=adapter,
        )

    def get_presigned_url(
        self, file_id: Union[str, UUID], scope: Literal["internal", "external"] = "external"
    ) -> PresignedUrlResponse:
        """Generate a temporary presigned URL for downloading a file.

        Args:
            file_id: UUID of the file to access.
            scope: URL scope - "external" for public download, "internal" for service-to-service.
                Defaults to "external".

        Returns:
            PresignedUrlResponse containing the temporary download URL.

        Raises:
            ElephantConfigError: If file_id is invalid.
        """
        file_uuid = coerce_uuid(file_id, "file_id")
        if not file_uuid:
            raise ElephantConfigError(f"Invalid file_id: {file_id!r}")

        return self._make_request(
            "GET",
            self._url(f"files/{file_uuid}/presign"),
            headers={"X-Presign-Scope": scope},
            validate_with=PresignedUrlResponse,
        )

    def upload_file_by_id(
        self,
        encounter_id: Union[str, UUID],
        file_path: FsPath,
        file_type: Union[str, FileTypeCode],
        additional_file_identifier: Optional[int] = None,
    ) -> FileUploadResult:
        """Upload a single file to an existing encounter by ID.

        Args:
            encounter_id: UUID of the encounter to associate with the file.
            file_path: Path to the file to upload.
            file_type: File type code (see get_file_types()).
            additional_file_identifier: Optional caller-defined integer identifier.

        Returns:
            FileUploadResult containing the uploaded file's ID and status.

        Raises:
            ElephantConfigError: If encounter_id is invalid or file not found.
            ElephantError: If server fails to return a file_id.
        """

        ft = require_file_type(file_type)

        encounter_uuid = coerce_uuid(encounter_id, "encounter_id")
        if not encounter_uuid:
            raise ElephantConfigError(f"Invalid encounter_id: {encounter_id!r}")

        meta = UploadByIdMeta(
            encounter_id=encounter_uuid,
            file_type=ft,
            additional_file_identifier=additional_file_identifier,
        )
        path_obj = Path(file_path)
        if not path_obj.exists():
            raise ElephantConfigError(f"File not found at path: {file_path}")
        meta_json = meta.model_dump_json(exclude_none=True)
        mime_type = mimetypes.guess_type(path_obj.name)[0] or "application/octet-stream"
        multipart_form_data: List[Tuple[str, Tuple[str, Union[IO[bytes], str], str]]] = []

        with path_obj.open("rb") as fh:
            multipart_form_data.extend(
                [
                    ("form", ("form", meta_json, "application/json")),
                    ("file", (path_obj.name, fh, mime_type)),
                ]
            )
            result = self._make_request(
                "POST",
                self._url("upload-by-id"),
                files=multipart_form_data,
                timeout=300,
                validate_with=FileUploadResult,
            )

            if not result.file_id:
                raise ElephantError("Server did not return a file_id.")
            return result

    def validate_files(
        self,
        case_name: str,
        activity_name: str,
        file_type: Union[str, FileTypeCode],
        expected_count: int,
        *,
        learner_emails: Optional[List[str]] = None,
        learners: Optional[List[str]] = None,
    ) -> FileValidationResponse:
        """Validate that encounters have the expected number of files.

        Finds all encounters matching the case, activity, and participant
        selector, then checks if each has the expected number of files of the
        specified type. Matching is broad by design: an encounter matches when
        any participant is in the provided selector.

        Args:
            case_name: Case name to match.
            activity_name: Activity name to match.
            file_type: Type of files to count (see get_file_types()).
            expected_count: Expected number of files per encounter.
            learner_emails: Preferred list of learner emails to match by stable
                learner identity. If provided, the server uses this selector
                instead of legacy learner display names.
            learners: Deprecated list of learner display names to match. Kept
                for backwards compatibility; prefer learner_emails because
                display names are not stable identifiers.

        Returns:
            Validation summary with total encounters found, how many are valid,
            and details for any encounters with mismatched file counts.
        """

        if not learner_emails and not learners:
            raise ElephantConfigError("learner_emails or learners is required")

        ft = require_file_type(file_type)
        validation_request_model = FileValidationRequest(
            case_name=trim_display_value(case_name),
            activity_name=trim_display_value(activity_name),
            learner_emails=(
                [normalize_email(email) for email in learner_emails] if learner_emails else None
            ),
            learners=([str(learner).strip() for learner in learners] if learners else None),
            file_type=ft,
            expected_count=expected_count,
        )

        url = self._url("files/validate")

        return self._make_request(
            "POST",
            url,
            json_data=validation_request_model.model_dump(
                mode="json",
                exclude_unset=True,
                exclude_none=True,
            ),
            validate_with=FileValidationResponse,
        )

    def delete_file(
        self,
        file_id: Union[str, UUID],
        *,
        hard_delete: bool = False,
        reason: Optional[str] = None,
    ) -> None:
        """Delete a file by ID. Must have at least read write delete permissions.

        Args:
            file_id: UUID or string identifier of the file.
            hard_delete: Permanently removes the file when True.
            reason: Optional audit trail reason.
        """
        file_uuid = coerce_uuid(file_id, "file_id")
        if file_uuid is None:
            raise ElephantConfigError("file_id is required")

        params: dict[str, Any] = {}
        if hard_delete:
            params["hard_delete"] = "true"
        if reason:
            params["reason"] = reason

        url = self._url(f"files/{file_uuid}")
        self._make_request(
            "DELETE",
            url,
            json_data=None,
            validate_with=None,
            params=params if params else None,
        )

    def prepare_bulk_upload_by_id(
        self, encounter_id: Union[UUID, str], files_to_upload: list[FileToUpload]
    ) -> PreparedBulkById:
        """Prepare bulk upload metadata from a list of files.

        Convenience helper that converts a list of FileToUpload objects into
        the format expected by upload_files_by_id_bulk().

        .. note::
            The implementation now lives in :func:`elephant.helpers.prepare_bulk_upload_by_id`.
            This method is retained as a thin, behavior-identical wrapper so existing
            ``client.prepare_bulk_upload_by_id(...)`` calls keep working.

        Args:
            encounter_id: UUID of the encounter to upload files to.
            files_to_upload: List of FileToUpload objects describing the files.

        Returns:
            PreparedBulkById object ready to pass to upload_files_by_id_bulk().

        Raises:
            ElephantConfigError: If encounter_id is invalid or files_to_upload contains invalid items.
        """
        return _prepare_bulk_upload_by_id(encounter_id, files_to_upload)

    def upload_files_by_id_bulk(
        self, bulk_meta_list: list[UploadByIdBulkMeta], files_to_upload: Sequence[FsPath]
    ) -> BulkUploadResponse:
        """Upload multiple files to an encounter in a single request.

        Returns HTTP 207 (Multi-Status) with individual results for each file.
        Some files may succeed while others fail - check the response summary
        and per-file results to determine overall success.

        The metadata list and file paths must correspond by position - the first
        metadata entry describes the first file, and so on. All files are typically
        uploaded to the same encounter.

        Args:
            bulk_meta_list: List of metadata objects, one per file.
            files_to_upload: List of file paths in the same order as bulk_meta_list.

        Returns:
            BulkUploadResponse with summary statistics (total, created, duplicates, errors)
            and individual FileUploadResult for each file.

        Raises:
            ElephantConfigError: If lists have different lengths, file not found,
                or file names don't match between metadata and actual files.
            ElephantError: If the bulk upload request fails entirely.
        """

        # They need to match up in length and order
        if len(bulk_meta_list) != len(files_to_upload):
            raise ElephantConfigError(
                "The number of metadata entries must match the number of files to upload."
            )
        for meta, file in zip(bulk_meta_list, files_to_upload, strict=False):
            if meta.file_name != Path(file).name:
                raise ElephantConfigError(
                    f"File name mismatch: {meta.file_name} != {Path(file).name}"
                )

        adapter = TypeAdapter(List[UploadByIdBulkMeta])

        meta_json: str = adapter.dump_json(bulk_meta_list, exclude_none=True).decode("utf-8")

        multipart: List[Tuple[str, Tuple[str, Any, str]]] = [
            ("meta", ("meta", meta_json, "application/json"))
        ]

        url = self._url("upload-by-id-bulk")

        with ExitStack() as stack:
            for meta, file_path in zip(bulk_meta_list, files_to_upload, strict=True):
                path_obj = Path(file_path)
                if not path_obj.exists():
                    raise ElephantConfigError(f"File not found at path: {file_path}")

                mime_type = mimetypes.guess_type(path_obj.name)[0] or "application/octet-stream"
                fh = stack.enter_context(path_obj.open("rb"))
                filename = meta.file_name or path_obj.name
                multipart.append(("files", (filename, fh, mime_type)))

            try:
                # This might help with large uploads by keeping the stack open until the request is done
                resp = self._make_request(
                    "POST",
                    url,
                    files=multipart,
                    timeout=300,
                    validate_with=BulkUploadResponse,
                )
                return resp
            except ElephantError as e:
                raise ElephantError(f"Bulk upload failed: {e}") from e

    def create_encounter(
        self,
        case_name: str,
        activity_name: str,
        date: str,  # existing models use string for malformed dates
        cohort_name: str,
        learner_emails: List[str],
        room: Optional[str] = None,
        standardized_patients: Optional[str] = None,
        additional_encounter_details: Optional[dict[str, Any]] = None,
    ) -> EncounterResponse:
        """Create a new encounter or return existing one if already created.

        This operation is idempotent - repeated calls with the same parameters
        return the same encounter (HTTP 200). New encounters return HTTP 201.
        The cohort and all learner emails must already exist in the system.

        Args:
            case_name: Name of the case.
            activity_name: Name of the activity.
            date: Date string in "MM/DD/YYYY hh:mm a" format.
            cohort_name: Name of an existing cohort.
            learner_emails: List of existing learner email addresses (minimum 1).
            room: Room identifier (optional).
            standardized_patients: Standardized patient names (optional).
            additional_encounter_details: Custom metadata as a dictionary (optional).

        Returns:
            EncounterResponse with encounter details and status flags indicating
            whether the encounter, case, and activity were created or reused.

        Raises:
            ElephantHTTPError: If cohort doesn't exist or any learner email not found (404).
        """
        # Construct the CreateEncounterRequest internally
        model = CreateEncounterRequest(
            case_name=trim_display_value(case_name),
            activity_name=trim_display_value(activity_name),
            date=date,
            cohort_name=trim_display_value(cohort_name),
            learner_emails=[normalize_email(email) for email in learner_emails],
            room=room,
            standardized_patients=standardized_patients,
            additional_encounter_details=additional_encounter_details,
        )

        url = self._url("encounters")

        return self._make_request(
            "POST",
            url,
            json_data=model.model_dump(mode="json", exclude_unset=True),
            validate_with=EncounterResponse,
        )

    def search_encounters(
        self,
        learner: Optional[str] = None,
        cohort: Optional[str] = None,
        case_name: Optional[str] = None,
        activity_name: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[str] = None,
        require_unique: Optional[bool] = None,
    ) -> EncounterSearchResponse:
        """Search for encounters with filtering and pagination.

        All text filters use case-insensitive substring matching by default.
        Returns paginated results with total count.

        Args:
            learner: Filter by learner name.
            cohort: Filter by cohort name.
            case_name: Filter by case name.
            activity_name: Filter by activity name.
            limit: Maximum results to return (default 50).
            offset: Number of results to skip for pagination (default 0).
            order_by: Sort order - "date_desc", "date_asc", "case_name", or "activity_name" (default "date_desc").
            require_unique: If True, raises error when multiple encounters match (default False).

        Returns:
            EncounterSearchResponse with total count and list of matching encounters.

        Raises:
            ElephantHTTPError: If require_unique=True and multiple encounters found (422).
        """
        # order_by_
        model = EncounterSearchRequest(
            learner=strip_or_none(learner),
            cohort=strip_or_none(cohort),
            case_name=strip_or_none(case_name),
            activity_name=strip_or_none(activity_name),
            limit=limit,
            offset=offset,
            require_unique=require_unique,
        )
        payload = model.model_dump(mode="json", exclude_unset=True, exclude_none=True)

        url = self._url("encounters/search")

        return self._make_request(
            "POST",
            url,
            json_data=payload,
            validate_with=EncounterSearchResponse,
        )

    def search_cohort_learners(self, cohort: str) -> List[LearnerSummary]:
        """Get all learners in a cohort by exact cohort name.

        Args:
            cohort: Exact cohort name to search (case-insensitive, whitespace trimmed).

        Returns:
            List of LearnerSummary objects. Returns empty list if cohort exists but has no learners.

        Raises:
            ElephantConfigError: If cohort is empty string.
            ElephantHTTPError: If cohort does not exist (404).
        """

        cohort_name = trim_display_value(cohort)
        if not cohort_name:
            raise ElephantConfigError("cohort must be a non-empty string")

        url = self._url("cohorts/search")
        return self._make_request(
            "POST",
            url,
            json_data={"cohort": cohort_name},
            validate_with=TypeAdapter(List[LearnerSummary]),
        )

    def upsert_cohort(
        self,
        cohort_name: str,
        learner_emails: Sequence[Union[str, EmailStr]],
    ) -> CohortUpsertResponse:
        """Create or update a cohort and link existing learners to it.

        This operation is idempotent. Cohort matching is case-insensitive with
        whitespace trimming. Learners are identified by email and must already
        exist; create or update learners first with `upsert_learner` or
        `upsert_learners_bulk`.

        Args:
            cohort_name: Name of the cohort to create or update.
            learner_emails: Existing learner emails to link to the cohort (minimum 1).

        Returns:
            CohortUpsertResponse with cohort details, summary counts, ordered
            per-email results with status/message, and per-row errors when a
            learner is missing or duplicated.

        Raises:
            ElephantConfigError: If cohort_name or learner_emails are invalid.
        """

        cohort_name_clean = trim_display_value(cohort_name)
        if cohort_name is None or not cohort_name_clean:
            raise ElephantConfigError("cohort_name must be a non-empty string")
        if learner_emails is None or isinstance(learner_emails, (str, bytes)):
            raise ElephantConfigError("learner_emails must be a non-empty sequence")

        email_list = list(learner_emails)
        if not email_list:
            raise ElephantConfigError("learner_emails must contain at least one email")

        try:
            model = CohortUpsertRequest(
                cohort_name=cohort_name_clean,
                learner_emails=[normalize_email(email) for email in email_list],
            )
        except ValidationError as e:
            raise ElephantConfigError(f"Invalid cohort upsert request: {e}") from e

        url = self._url("cohorts")
        return self._make_request(
            "POST",
            url,
            json_data=model.model_dump(mode="json", exclude_unset=True),
            validate_with=CohortUpsertResponse,
        )

    def upsert_learner(
        self,
        email: Union[str, EmailStr],
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        learner_name: Optional[str] = None,
    ) -> LearnerUpsertWithEffectResponse:
        """Create or update a learner by email.

        Email is the unique identifier. For new learners, at least one name field
        must be provided. For existing learners, only non-empty fields are updated.

        Args:
            email: Learner email address (required, used as unique identifier).
            first_name: First name (optional, updates existing if provided).
            last_name: Last name (optional, updates existing if provided).
            learner_name: Full display name (optional, updates existing if provided).

        Returns:
            LearnerUpsertWithEffectResponse with learner details and status indicating
            whether the learner was "created", "updated", or "reused".

        Raises:
            ElephantConfigError: If email is empty or all name fields are empty.
        """

        # If all of first_name, last_name, learner_name are None or empty, raise error
        if not email or not email.strip():
            raise ElephantConfigError("email is required and must be a non-empty string")
        if (not first_name and not last_name and not learner_name) or all(
            not s or not s.strip() for s in (first_name, last_name, learner_name)
        ):
            raise ElephantConfigError(
                "At least one of first_name, last_name, or learner_name must be provided and non-empty"
            )

        else:
            payload = {
                "email": normalize_email(email),
                "first_name": strip_or_none(first_name),
                "last_name": strip_or_none(last_name),
                "learner_name": strip_or_none(learner_name),
            }

        url = self._url("learners")
        return self._make_request(
            "POST",
            url,
            json_data=payload,
            validate_with=LearnerUpsertWithEffectResponse,
        )

    def upsert_learners_bulk(
        self,
        items: Sequence[Union[BulkLearnerUpsertItem, dict[str, Any]]],
    ) -> BulkLearnerUpsertResponse:
        """Create or update learners in bulk and return per-item outcomes.

        Args:
            items: Learners to upsert. Each item must include email and either
                learner_name or both first_name and last_name.

        Returns:
            BulkLearnerUpsertResponse with summary counts and ordered per-item
            status/message results.
        """

        item_list = list(items)
        if not item_list:
            raise ElephantConfigError("items must contain at least one learner")

        # validate each item and coerce dicts to BulkLearnerUpsertItem
        validated_items: List[BulkLearnerUpsertItem] = []
        for idx, item in enumerate(item_list):
            if isinstance(item, dict):
                try:
                    validated = BulkLearnerUpsertItem.model_validate(item)
                    validated_items.append(validated)
                except ValidationError as e:
                    raise ElephantConfigError(f"Invalid item at index {idx}: {e}") from e
            elif isinstance(item, BulkLearnerUpsertItem):
                validated_items.append(item)
            else:
                raise ElephantConfigError(
                    f"Invalid item at index {idx}: must be BulkLearnerUpsertItem or dict"
                )

        normalized_items = [
            item.model_copy(update={"email": normalize_email(item.email)})
            for item in validated_items
        ]
        model = BulkLearnerUpsertRequest(items=normalized_items)
        url = self._url("learners/bulk")
        return self._make_request(
            "POST",
            url,
            json_data=model.model_dump(mode="json", exclude_unset=True),
            validate_with=BulkLearnerUpsertResponse,
        )

    @staticmethod
    def _coerce_api_key_role(role: Union[str, ApiKeyRole]) -> ApiKeyRole:
        if isinstance(role, ApiKeyRole):
            return role
        if isinstance(role, str):
            normalized = role.strip()
            if not normalized:
                raise ElephantConfigError("role is required")
            try:
                return ApiKeyRole(normalized)
            except ValueError:
                allowed = ", ".join(item.value for item in ApiKeyRole)
                raise ElephantConfigError(
                    f"Invalid API key role {role!r}. Allowed values: {allowed}"
                ) from None
        raise ElephantConfigError(f"role must be a string or ApiKeyRole, not {type(role).__name__}")

    @staticmethod
    def _require_api_key_uuid(key_id: Union[str, UUID]) -> UUID:
        key_uuid = coerce_uuid(key_id, "key_id")
        if key_uuid is None:
            raise ElephantConfigError("key_id is required")
        return key_uuid
