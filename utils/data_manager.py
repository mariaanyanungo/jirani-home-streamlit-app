"""Data layer for the Jirani Home Controlled Policy Library prototype.

Responsibilities
- Locate, create, read, validate and safely write the three local CSV files.
- Hold shared constants (categories, statuses, column lists, fixed messages).
- Hold the small business rules several pages rely on: which policies agents may
  see, which are due for review, and publish-time validation.

Everything is local. There are no network calls and no API keys.
"""

from __future__ import annotations

import os
import re
import tempfile
import uuid
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
POLICIES_FILE = DATA_DIR / "policies.csv"
ISSUES_FILE = DATA_DIR / "policy_issues.csv"
AUDIT_FILE = DATA_DIR / "audit_log.csv"

POLICY_COLUMNS = [
    "policy_id",
    "title",
    "category",
    "version",
    "effective_date",
    "approval_date",
    "approval_status",
    "status",
    "owner",
    "next_review_date",
    "content",
    "replaces_policy_id",
    "archive_reason",
]
ISSUE_WORKFLOW_COLUMNS = [
    "workflow_status",
    "workflow_tracking_id",
    "workflow_message",
    "workflow_last_updated",
    "workflow_retry_count",
]
ISSUE_COLUMNS = [
    "issue_id",
    "policy_id",
    "issue_type",
    "ticket_reference",
    "description",
    "reported_by",
    "reported_date",
    "assigned_to",
    "status",
    "resolution_notes",
    "last_updated",
    *ISSUE_WORKFLOW_COLUMNS,
]
AUDIT_COLUMNS = [
    "event_id",
    "timestamp",
    "user",
    "role",
    "action",
    "policy_id",
    "issue_id",
    "details",
]

CATEGORIES = ["Delivery", "Returns", "Damaged items", "Warranty", "Account queries"]
STATUS_CURRENT = "Current approved"
STATUS_SUPERSEDED = "Superseded"
STATUS_OUTDATED = "Outdated"
STATUS_ARCHIVE_ONLY = "Archive-only"
STATUS_DUPLICATE = "Duplicate"
STATUS_CLARIFY = "Requires clarification"
POLICY_STATUSES = [
    STATUS_CURRENT,
    STATUS_SUPERSEDED,
    STATUS_ARCHIVE_ONLY,
    STATUS_DUPLICATE,
    STATUS_CLARIFY,
]
SUPERSEDED_STATUSES = [STATUS_SUPERSEDED, STATUS_OUTDATED]
ARCHIVE_STATUSES = [STATUS_SUPERSEDED, STATUS_OUTDATED, STATUS_ARCHIVE_ONLY]
APPROVED = "Approved"
APPROVAL_OPTIONS = [APPROVED, "Pending approval", "Draft", "Rejected"]
ISSUE_TYPES = [
    "Missing policy",
    "Unclear policy",
    "Conflicting policy",
    "Potentially outdated policy",
]
ISSUE_OPEN = "Open"
ISSUE_IN_REVIEW = "In review"
ISSUE_RESOLVED = "Resolved"
ISSUE_STATUSES = [ISSUE_OPEN, ISSUE_IN_REVIEW, ISSUE_RESOLVED]
DEFAULT_ASSIGNEE = "Relevant Policy Owner"
REVIEW_WINDOW_DAYS = 30
REQUIRED_METADATA = [
    "title",
    "category",
    "version",
    "effective_date",
    "approval_date",
    "approval_status",
    "status",
    "owner",
    "next_review_date",
]
SUPERSEDED_WARNING = "Superseded — Do not use for customer responses."
RESTRICTED_SUPERSEDED_MESSAGE = (
    "Access restricted. This policy is superseded and cannot be used for "
    "customer-response guidance."
)

WORKFLOW_STATUS_NOT_SENT = "Not sent"
WORKFLOW_STATUS_SENDING = "Sending"
WORKFLOW_STATUS_COMPLETED = "Workflow completed"
WORKFLOW_STATUS_NOTIFICATION_FAILED = "Notification failed"
WORKFLOW_STATUS_VALIDATION_FAILED = "Validation failed"
WORKFLOW_STATUS_RETRYING = "Retrying"
WORKFLOW_STATUS_NOT_CONFIGURED = "Not configured"


class DataError(Exception):
    """Raised when a CSV file cannot be created, read, validated or saved."""


def _write_empty(path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=columns).to_csv(path, index=False, encoding="utf-8")


def ensure_file(path: Path, columns: list[str]) -> bool:
    try:
        if not path.exists() or path.stat().st_size == 0:
            _write_empty(path, columns)
            return True
    except OSError as exc:
        raise DataError(f"Could not create 'data/{path.name}': {exc}") from exc
    return False


def ensure_issue_workflow_columns(df: pd.DataFrame) -> pd.DataFrame:
    defaults = {
        "workflow_status": WORKFLOW_STATUS_NOT_SENT,
        "workflow_tracking_id": "",
        "workflow_message": "",
        "workflow_last_updated": "",
        "workflow_retry_count": 0,
    }
    for column, default_value in defaults.items():
        if column not in df.columns:
            df[column] = default_value
    return df


def _read(
    path: Path, columns: list[str], create: bool = True
) -> tuple[pd.DataFrame, bool]:
    created = False
    if create:
        created = ensure_file(path, columns)
    elif not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=columns), False

    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise DataError(
            f"'data/{path.name}' is not a valid UTF-8 CSV file ({exc})."
        ) from exc
    except OSError as exc:
        raise DataError(f"'data/{path.name}' could not be opened: {exc}") from exc

    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in columns if c not in df.columns]
    if missing:
        if path == ISSUES_FILE:
            df = df.reindex(columns=df.columns.tolist() + missing)
            default_values = {
                "workflow_status": WORKFLOW_STATUS_NOT_SENT,
                "workflow_tracking_id": "",
                "workflow_message": "",
                "workflow_last_updated": "",
                "workflow_retry_count": 0,
            }
            for column in missing:
                df[column] = default_values.get(column, "")
            return df, False
        raise DataError(
            f"'data/{path.name}' is missing required column(s): {', '.join(missing)}. "
            "Correct the header row so it matches the expected columns."
        )
    if path == ISSUES_FILE:
        df = ensure_issue_workflow_columns(df)
    return df, created


def _save(df: pd.DataFrame, path: Path, columns: list[str]) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise DataError(
            f"Refusing to save 'data/{path.name}': missing column(s) {', '.join(missing)}."
        )

    if path.exists() and path.stat().st_size > 0:
        try:
            pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        except (
            pd.errors.ParserError,
            pd.errors.EmptyDataError,
            UnicodeDecodeError,
        ) as exc:
            raise DataError(
                f"Refusing to overwrite the existing file. 'data/{path.name}' is not a valid UTF-8 CSV file ({exc})."
            ) from exc
        except OSError as exc:
            raise DataError(
                f"Refusing to overwrite the existing file. 'data/{path.name}' could not be opened: {exc}"
            ) from exc

    extras = [c for c in df.columns if c not in columns]
    out = df[columns + extras].fillna("")
    if path == ISSUES_FILE:
        out = ensure_issue_workflow_columns(out)

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=f"{path.stem}_", suffix=".tmp"
        )
    except OSError as exc:
        raise DataError(f"Could not write to 'data/': {exc}") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            out.to_csv(handle, index=False)
        os.replace(tmp_name, path)
    except (OSError, ValueError) as exc:
        try:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
        except OSError:
            pass
        raise DataError(f"Could not save 'data/{path.name}': {exc}") from exc


def append_row(path: Path, columns: list[str], row: dict) -> None:
    df, _ = _read(path, columns)
    new = pd.DataFrame([{c: str(row.get(c, "")) for c in columns}])
    df = new if df.empty else pd.concat([df, new], ignore_index=True)
    _save(df, path, columns)


def ensure_data_files() -> list[str]:
    created = []
    for path, cols in (
        (POLICIES_FILE, POLICY_COLUMNS),
        (ISSUES_FILE, ISSUE_COLUMNS),
        (AUDIT_FILE, AUDIT_COLUMNS),
    ):
        try:
            if ensure_file(path, cols):
                created.append(path.name)
        except DataError as exc:
            st.error(str(exc))
    return created


def _load(path: Path, columns: list[str], label: str, notify: bool) -> pd.DataFrame:
    try:
        df, created = _read(path, columns)
    except DataError as exc:
        if notify:
            st.error(f"The {label} could not be loaded. {exc}")
        return pd.DataFrame(columns=columns)
    if created and notify:
        st.info(
            f"The {label} file was missing or empty, so a new empty file with the correct "
            f"columns was created at 'data/{path.name}'."
        )
    return df


def load_policies(notify: bool = True) -> pd.DataFrame:
    return _load(POLICIES_FILE, POLICY_COLUMNS, "policy register", notify)


def load_issues(notify: bool = True) -> pd.DataFrame:
    return _load(ISSUES_FILE, ISSUE_COLUMNS, "policy issue list", notify)


def load_audit(notify: bool = True) -> pd.DataFrame:
    return _load(AUDIT_FILE, AUDIT_COLUMNS, "audit log", notify)


def read_policies() -> pd.DataFrame:
    return _read(POLICIES_FILE, POLICY_COLUMNS)[0]


def read_issues() -> pd.DataFrame:
    return _read(ISSUES_FILE, ISSUE_COLUMNS)[0]


def save_policies(df: pd.DataFrame) -> None:
    _save(df, POLICIES_FILE, POLICY_COLUMNS)


def save_issues(df: pd.DataFrame) -> None:
    _save(df, ISSUES_FILE, ISSUE_COLUMNS)


def append_issue_row(row: dict) -> None:
    append_row(ISSUES_FILE, ISSUE_COLUMNS, row)


def append_audit_row(row: dict) -> None:
    append_row(AUDIT_FILE, AUDIT_COLUMNS, row)


def get_summary_counts() -> dict:
    try:
        policies, _ = _read(POLICIES_FILE, POLICY_COLUMNS, create=False)
        issues, _ = _read(ISSUES_FILE, ISSUE_COLUMNS, create=False)
    except DataError:
        return {"current": None, "superseded": None, "open_issues": None}
    return {
        "current": int((policies["status"] == STATUS_CURRENT).sum()),
        "superseded": int(policies["status"].isin(SUPERSEDED_STATUSES).sum()),
        "open_issues": int((issues["status"] == ISSUE_OPEN).sum()),
    }


def clean_text(value, max_len: int = 1000) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()[:max_len]
    if text[:1] in ("=", "+", "-", "@", "\t"):
        text = "'" + text
    return text


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_event_id() -> str:
    return f"EVT-{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6].upper()}"


def new_issue_id(existing_ids) -> str:
    existing = {str(i) for i in existing_ids}
    while True:
        candidate = f"ISS-{date.today():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
        if candidate not in existing:
            return candidate


def next_policy_id(df: pd.DataFrame) -> str:
    numbers = []
    for pid in df["policy_id"]:
        match = re.fullmatch(r"P(\d+)", str(pid).strip())
        if match:
            numbers.append(int(match.group(1)))
    return f"P{(max(numbers) if numbers else 0) + 1:03d}"


def days_until(value, today: date | None = None):
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return (ts.date() - (today or date.today())).days


def metadata_complete(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    return (
        df[REQUIRED_METADATA]
        .apply(lambda col: col.astype(str).str.strip() != "")
        .all(axis=1)
    )


def agent_visible_policies(df: pd.DataFrame) -> pd.DataFrame:
    current = df[df["status"] == STATUS_CURRENT]
    if current.empty:
        return current
    ok = metadata_complete(current) & (
        current["approval_status"].str.strip() == APPROVED
    )
    return current[ok]


def search_policies(df: pd.DataFrame, query: str) -> pd.DataFrame:
    terms = [t for t in re.split(r"\s+", (query or "").strip().lower()) if t]
    if not terms or df.empty:
        return df
    haystack = (
        df["policy_id"]
        + " "
        + df["title"]
        + " "
        + df["category"]
        + " "
        + df["owner"]
        + " "
        + df["content"]
    ).str.lower()
    mask = pd.Series(True, index=df.index)
    for term in terms:
        mask &= haystack.str.contains(term, regex=False)
    return df[mask]


def due_for_review(df: pd.DataFrame, days: int = REVIEW_WINDOW_DAYS) -> pd.DataFrame:
    current = df[df["status"] == STATUS_CURRENT].copy()
    if current.empty:
        current["days_to_review"] = pd.Series(dtype=float)
        return current
    current["days_to_review"] = pd.to_numeric(
        current["next_review_date"].apply(days_until), errors="coerce"
    )
    return current[current["days_to_review"] <= days]


def review_flag(status: str, days) -> str:
    if status != STATUS_CURRENT:
        return ""
    if days is None or pd.isna(days):
        return "No review date"
    if days < 0:
        return f"Overdue by {abs(int(days))} day(s)"
    if days <= REVIEW_WINDOW_DAYS:
        return f"Due in {int(days)} day(s)"
    return "On schedule"


def register_view(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["review_flag"] = ""
    out["metadata_complete"] = ""
    if out.empty:
        return out
    days = out["next_review_date"].apply(days_until)
    out["review_flag"] = [review_flag(s, d) for s, d in zip(out["status"], days)]
    out["metadata_complete"] = metadata_complete(out).map({True: "Yes", False: "No"})
    return out


def version_key(version: str) -> tuple:
    return tuple(int(part) for part in str(version).strip().split("."))


def validate_policy_record(
    record: dict, previous_version: str | None = None
) -> list[str]:
    errors: list[str] = []

    if not str(record.get("title") or "").strip():
        errors.append("Policy title is required.")
    if record.get("category") not in CATEGORIES:
        errors.append("Select a valid policy category.")

    version = str(record.get("version") or "").strip()
    if not version:
        errors.append("Version is required (for example 3.1).")
    elif not re.fullmatch(r"\d+(\.\d+)*", version):
        errors.append("Version must be numeric, such as 2.0 or 1.2.1.")
    elif previous_version and re.fullmatch(
        r"\d+(\.\d+)*", str(previous_version).strip()
    ):
        if version_key(version) <= version_key(previous_version):
            errors.append(
                f"The new version ({version}) must be higher than the version being replaced ({previous_version})."
            )

    if not str(record.get("owner") or "").strip():
        errors.append("Named owner is required.")

    approval_status = str(record.get("approval_status") or "").strip()
    if not approval_status:
        errors.append("Approval status is required.")
    elif approval_status != APPROVED:
        errors.append(
            "Approval status must be 'Approved' before a policy can be published as Current approved."
        )

    effective = record.get("effective_date")
    approval_date = record.get("approval_date")
    next_review = record.get("next_review_date")
    if not effective:
        errors.append("Effective date is required.")
    if not approval_date:
        errors.append("Approval date is required.")
    if not next_review:
        errors.append("Next review date is required.")
    if effective and approval_date and approval_date > effective:
        errors.append("Approval date must be on or before the effective date.")
    if effective and next_review and next_review <= effective:
        errors.append("Next review date must be after the effective date.")

    if not str(record.get("content") or "").strip():
        errors.append("Policy content is required.")
    return errors


def update_issue_record(issue_id: str, changes: dict) -> None:
    df = read_issues()
    matches = df[df["issue_id"].astype(str) == str(issue_id)]
    if len(matches) == 0:
        raise DataError(f"Issue {issue_id} does not exist.")
    if len(matches) > 1:
        raise DataError(f"Duplicate issue IDs found for {issue_id}.")

    idx = matches.index[0]
    for key, value in changes.items():
        if key not in df.columns:
            df[key] = ""
        df.at[idx, key] = value
    df.at[idx, "last_updated"] = now_str()
    save_issues(df)
