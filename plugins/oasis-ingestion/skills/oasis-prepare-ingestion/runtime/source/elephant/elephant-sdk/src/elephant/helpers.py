# src/elephant/helpers.py
"""High-level convenience helpers built on top of the client primitives.

These are intentionally thin and dependency-light (stdlib only). They follow a
parse-then-call pattern: they turn user-friendly inputs (e.g. CSV files) into
the typed objects the bulk endpoints expect, but they do NOT make network calls.
Pass the result straight into the matching client method.
"""

import csv
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Annotated, Callable, Dict, List, Optional, Tuple, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .exceptions import ElephantConfigError
from .models import BulkLearnerUpsertItem, FileTypeCode, UploadByIdBulkMeta
from .utils import (
    FileToUpload,
    FsPath,
    PreparedBulkById,
    coerce_uuid,
    normalize_email,
    require_file_type,
    strip_or_none,
    trim_display_value,
)

# Canonical field name -> set of accepted header variants (after normalization:
# lowercased, trimmed, non-alphanumeric runs collapsed to a single underscore).
_DEFAULT_LEARNER_COLUMNS: Dict[str, frozenset] = {
    "email": frozenset({"email", "email_address", "e_mail", "mail"}),
    "learner_name": frozenset({"learner_name", "name", "full_name", "fullname"}),
    "first_name": frozenset({"first_name", "first", "firstname", "given_name"}),
    "last_name": frozenset({"last_name", "last", "lastname", "surname", "family_name"}),
}

# Encounter-metadata CSVs carry both encounter identity and per-file fields on each
# row. When two source columns map to the same canonical field, the rightmost wins.
_DEFAULT_ENCOUNTER_COLUMNS: Dict[str, frozenset] = {
    "cohort_name": frozenset({"cohort_name", "cohort"}),
    "case_name": frozenset({"case_name", "case"}),
    "activity_name": frozenset({"activity_name", "activity", "event"}),
    "date": frozenset({"date", "recording_start", "recording_date", "encounter_date"}),
    "room": frozenset({"room"}),
    "learner_emails": frozenset({"learner_emails", "learner_email", "emails", "email"}),
    "standardized_patients": frozenset(
        {"standardized_patients", "standardized_patient", "sps", "sp"}
    ),
    "file_name": frozenset({"file_name", "filename", "file"}),
    "file_type": frozenset({"file_type", "filetype", "type"}),
    "additional_file_identifier": frozenset(
        {
            "additional_file_identifier",
            "additional_file_id",
            "additional_identifier",
            "file_identifier",
        }
    ),
}

CsvSource = Union[str, Path, Iterable[str]]


def _normalize_header(header: str) -> str:
    """Lowercase, trim, and collapse non-alphanumeric runs to single underscores."""
    out: List[str] = []
    prev_us = False
    for ch in header.strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_us = False
        elif not prev_us:
            out.append("_")
            prev_us = True
    return "".join(out).strip("_")


def _build_header_resolver(
    defaults: Mapping[str, frozenset],
    column_map: Optional[Mapping[str, str]],
) -> Callable[[str], Optional[str]]:
    """Return a function mapping a raw CSV header to a canonical field name (or None).

    `defaults` is a canonical-field -> accepted-header-variants table. Those built-in
    aliases are applied first; `column_map` (raw_header -> canonical_field) overrides
    them and is matched on the normalized header so casing/spacing in the user's
    mapping doesn't matter.
    """
    alias_to_field: Dict[str, str] = {}
    for field, variants in defaults.items():
        for variant in variants:
            alias_to_field[variant] = field
    if column_map:
        for raw, field in column_map.items():
            alias_to_field[_normalize_header(raw)] = field

    def resolve(header: str) -> Optional[str]:
        return alias_to_field.get(_normalize_header(header))

    return resolve


def _read_csv_rows(source: CsvSource, encoding: str) -> List[Tuple[int, Dict[str, str]]]:
    """Read a CSV path or text-line iterable into (line_number, row_dict) pairs.

    `line_number` is 1-based and counts the header, so the first data row is 2 —
    matching what a user sees in a spreadsheet/editor.
    """
    if isinstance(source, str | Path):
        with open(source, encoding=encoding, newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                raise ElephantConfigError("CSV is empty (no header row).")
            return [(i, dict(row)) for i, row in enumerate(reader, start=2)]
    reader = csv.DictReader(source)
    if reader.fieldnames is None:
        raise ElephantConfigError("CSV is empty (no header row).")
    return [(i, dict(row)) for i, row in enumerate(reader, start=2)]


def _remap_row(row: Mapping[str, str], resolve: Callable[[str], Optional[str]]) -> Dict[str, str]:
    """Map a raw CSV row onto canonical fields, dropping blanks and unknown columns.

    Blank/unknown columns are dropped, so every stored value is a non-empty string;
    callers read required fields by subscript (``mapped["x"]`` -> ``str``) and
    optional fields via ``.get()`` (-> ``str | None``).
    """
    out: Dict[str, str] = {}
    for raw_key, value in row.items():
        if raw_key is None:
            continue
        field = resolve(raw_key)
        if field is None:
            continue
        cleaned = strip_or_none(value)
        if cleaned is not None:
            out[field] = cleaned
    return out


def learners_from_csv(
    source: CsvSource,
    *,
    column_map: Optional[Mapping[str, str]] = None,
    encoding: str = "utf-8",
) -> List[BulkLearnerUpsertItem]:
    """Parse a CSV into items for `ElephantClient.upsert_learners_bulk`.

    Recognized columns (case/spacing-insensitive, common variants accepted):
    email, learner_name, first_name, last_name. `email` is required; the rest
    are optional. Use `column_map` to map non-standard headers, e.g.
    ``{"Email Address": "email", "Full Name": "learner_name"}``.

    Args:
        source: Path to a CSV file, or an iterable of text lines.
        column_map: Optional raw-header -> canonical-field overrides.
        encoding: File encoding used when `source` is a path.

    Returns:
        List of BulkLearnerUpsertItem in CSV row order.

    Raises:
        ElephantConfigError: If the CSV is empty, lacks an email column, has no
            data rows, or any row fails validation (errors are aggregated with
            their line numbers).
    """
    resolve = _build_header_resolver(_DEFAULT_LEARNER_COLUMNS, column_map)
    rows = _read_csv_rows(source, encoding)
    if not rows:
        raise ElephantConfigError("CSV has a header but no data rows.")

    items: List[BulkLearnerUpsertItem] = []
    errors: List[str] = []
    for line_no, raw_row in rows:
        mapped = _remap_row(raw_row, resolve)
        if not mapped.get("email"):
            errors.append(f"line {line_no}: missing required 'email'")
            continue
        mapped["email"] = normalize_email(mapped["email"])
        try:
            items.append(BulkLearnerUpsertItem.model_validate(mapped))
        except ValidationError as exc:
            errors.append(f"line {line_no}: {_first_validation_msg(exc)}")

    if errors:
        raise ElephantConfigError(
            "CSV could not be parsed into learners:\n  " + "\n  ".join(errors)
        )
    return items


def cohort_learners_from_csv(
    source: CsvSource,
    *,
    column_map: Optional[Mapping[str, str]] = None,
    encoding: str = "utf-8",
) -> List[str]:
    """Parse a CSV into learner emails for `ElephantClient.upsert_cohort`.

    The cohort endpoint links existing learners by email only. Use
    `learners_from_csv` with `ElephantClient.upsert_learners_bulk` when learners
    need to be created or updated first. Recognized email columns and
    `column_map` behavior are identical to `learners_from_csv`.

    Args:
        source: Path to a CSV file, or an iterable of text lines.
        column_map: Optional raw-header -> canonical-field overrides.
        encoding: File encoding used when `source` is a path.

    Returns:
        List of normalized learner emails in CSV row order.

    Raises:
        ElephantConfigError: If the CSV is empty, has no data rows, or any row is
            missing an email or has an invalid email (errors aggregated with line
            numbers).
    """
    resolve = _build_header_resolver(_DEFAULT_LEARNER_COLUMNS, column_map)
    rows = _read_csv_rows(source, encoding)
    if not rows:
        raise ElephantConfigError("CSV has a header but no data rows.")

    emails: List[str] = []
    errors: List[str] = []
    for line_no, raw_row in rows:
        mapped = _remap_row(raw_row, resolve)
        email = mapped.get("email")
        if not email:
            errors.append(f"line {line_no}: missing required 'email'")
            continue
        try:
            item = BulkLearnerUpsertItem(email=normalize_email(email))
            emails.append(str(item.email))
        except ValidationError as exc:
            errors.append(f"line {line_no}: {_first_validation_msg(exc)}")

    if errors:
        raise ElephantConfigError(
            "CSV could not be parsed into cohort learners:\n  " + "\n  ".join(errors)
        )
    return emails


def _first_validation_msg(exc: ValidationError) -> str:
    err = exc.errors()[0]
    loc = ".".join(str(p) for p in err.get("loc", ())) or "(value)"
    return f"{loc}: {err.get('msg', 'invalid')}"


def prepare_bulk_upload_by_id(
    encounter_id: Union[UUID, str], files_to_upload: list[FileToUpload]
) -> PreparedBulkById:
    """Prepare bulk upload metadata from a list of files.

    Convenience helper that converts a list of FileToUpload objects into
    the format expected by upload_files_by_id_bulk().

    Args:
        encounter_id: UUID of the encounter to upload files to.
        files_to_upload: List of FileToUpload objects describing the files.

    Returns:
        PreparedBulkById object ready to pass to upload_files_by_id_bulk().

    Raises:
        ElephantConfigError: If encounter_id is invalid or files_to_upload contains invalid items.
    """
    enc_id = coerce_uuid(encounter_id, "encounter_id")
    if enc_id is None:
        raise ElephantConfigError("encounter_id is required")

    metas: List[UploadByIdBulkMeta] = []

    for file in files_to_upload:
        if not isinstance(file, FileToUpload):
            raise ElephantConfigError("files_to_upload must be a list of FileToUpload")
        ft = require_file_type(file.file_type)
        metas.append(
            UploadByIdBulkMeta(
                encounter_id=enc_id,
                file_type=ft,
                file_name=file.file_name,
                additional_file_identifier=file.additional_file_identifier,
            )
        )
    filepaths = [file.file_path for file in files_to_upload]

    return PreparedBulkById(meta=metas, paths=filepaths)


_REQUIRED_ENCOUNTER_FIELDS = (
    "cohort_name",
    "case_name",
    "activity_name",
    "date",
    "file_name",
    "file_type",
)


class EncounterFileRow(BaseModel):
    """One row of an encounter-metadata CSV: encounter identity plus one file.

    Multiple rows that share the same `encounter_key` belong to the same encounter
    (one row per file). Feed `learner_emails` + the encounter fields to
    `ElephantClient.create_encounter`, then `to_file_upload(directory)` into
    `prepare_bulk_upload_by_id` once the encounter id is known.
    """

    model_config = ConfigDict(extra="forbid")

    cohort_name: str
    case_name: str
    activity_name: str
    date: str
    learner_emails: Annotated[List[str], Field(min_length=1)]
    file_name: str
    file_type: FileTypeCode
    room: Optional[str] = None
    standardized_patients: Optional[str] = None
    additional_file_identifier: Optional[int] = None

    @property
    def encounter_key(self) -> Tuple[str, str, str, str, Optional[str], Tuple[str, ...]]:
        """Identity tuple for grouping rows into encounters (dedup key)."""
        return (
            self.cohort_name,
            self.case_name,
            self.activity_name,
            self.date,
            self.room,
            tuple(self.learner_emails),
        )

    def to_file_upload(self, directory: Optional[FsPath] = None) -> FileToUpload:
        """Build a FileToUpload for this row, resolving the path under `directory`."""
        path = self.file_name if directory is None else str(Path(directory) / self.file_name)
        return FileToUpload(
            file_path=path,
            file_type=self.file_type,
            file_name=self.file_name,
            additional_file_identifier=self.additional_file_identifier,
        )


def _split_emails(raw: Optional[str]) -> List[str]:
    if raw is None:
        return []
    return [normalize_email(e) for e in raw.split(",") if e.strip()]


def _parse_additional_file_identifier(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"additional_file_identifier must be an integer, got {raw!r}") from None


def encounter_rows_from_csv(
    source: CsvSource,
    *,
    column_map: Optional[Mapping[str, str]] = None,
    encoding: str = "utf-8",
) -> List[EncounterFileRow]:
    """Parse an encounter-metadata CSV into typed rows (one per file).

    Recognized columns (case/spacing-insensitive, common variants accepted):
    cohort_name, case_name, activity_name, date, room, learner_emails, file_name,
    file_type, additional_file_identifier, standardized_patients. `learner_emails` accepts a
    comma-separated list within the cell. Use `column_map` to map non-standard
    headers, e.g. ``{"Event": "activity_name", "SPs": "standardized_patients"}``.

    Each returned row exposes `.encounter_key` (group rows into encounters) and
    `.to_file_upload(directory)` (build the upload spec once the encounter exists).

    Args:
        source: Path to a CSV file, or an iterable of text lines.
        column_map: Optional raw-header -> canonical-field overrides.
        encoding: File encoding used when `source` is a path.

    Returns:
        List of EncounterFileRow in CSV row order.

    Raises:
        ElephantConfigError: If the CSV is empty, has no data rows, or any row is
            missing required fields / fails validation (errors are aggregated with
            their line numbers).
    """
    resolve = _build_header_resolver(_DEFAULT_ENCOUNTER_COLUMNS, column_map)
    rows = _read_csv_rows(source, encoding)
    if not rows:
        raise ElephantConfigError("CSV has a header but no data rows.")

    out: List[EncounterFileRow] = []
    errors: List[str] = []
    for line_no, raw_row in rows:
        mapped = _remap_row(raw_row, resolve)

        missing = [f for f in _REQUIRED_ENCOUNTER_FIELDS if not mapped.get(f)]
        emails = _split_emails(mapped.get("learner_emails"))
        if not emails:
            missing.append("learner_emails")
        if missing:
            errors.append(f"line {line_no}: missing required {', '.join(repr(m) for m in missing)}")
            continue

        try:
            out.append(
                EncounterFileRow(
                    cohort_name=trim_display_value(mapped["cohort_name"]),
                    case_name=trim_display_value(mapped["case_name"]),
                    activity_name=trim_display_value(mapped["activity_name"]),
                    date=mapped["date"],
                    room=mapped.get("room"),
                    standardized_patients=mapped.get("standardized_patients"),
                    learner_emails=emails,
                    file_name=mapped["file_name"],
                    file_type=require_file_type(mapped["file_type"]),
                    additional_file_identifier=_parse_additional_file_identifier(
                        mapped.get("additional_file_identifier")
                    ),
                )
            )
        except (ValidationError, ElephantConfigError, ValueError) as exc:
            detail = _first_validation_msg(exc) if isinstance(exc, ValidationError) else str(exc)
            errors.append(f"line {line_no}: {detail}")

    if errors:
        raise ElephantConfigError(
            "CSV could not be parsed into encounter rows:\n  " + "\n  ".join(errors)
        )
    return out
