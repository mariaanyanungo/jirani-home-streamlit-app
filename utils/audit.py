"""Audit trail helper. Every governed action writes one row to data/audit_log.csv."""

from __future__ import annotations

import streamlit as st

from utils import data_manager as dm
from utils.access_control import get_role, get_user

ACTION_POLICY_VERIFIED = "Policy viewed and verified"
ACTION_ISSUE_SUBMITTED = "Policy issue submitted"
ACTION_POLICY_PUBLISHED = "Policy published"
ACTION_POLICY_UPDATED = "Policy updated"
ACTION_POLICY_SUPERSEDED = "Policy marked superseded"
ACTION_STATUS_CHANGED = "Policy status changed"
ACTION_ISSUE_RESOLVED = "Policy issue resolved"
ACTION_ISSUE_STATUS = "Policy issue status changed"
ACTION_ISSUE_UPDATED = "Policy issue updated"
ACTION_ACCESS_BLOCKED = "Restricted policy access blocked"
ACTION_ISSUE_SAVED_LOCALLY = "Policy issue saved locally"
ACTION_MAKE_SENT = "Policy issue sent to Make workflow"
ACTION_MAKE_FAILED = "Make workflow notification failed"
ACTION_MAKE_RETRIED = "Retried Make policy issue workflow"
ACTION_MAKE_NOT_CONFIGURED = "Make workflow not configured"


def log_event(
    action: str,
    policy_id: str = "",
    issue_id: str = "",
    details: str = "",
    user: str | None = None,
    role: str | None = None,
) -> bool:
    """Append an audit event. Returns True if it was saved.

    User and role default to the simulated values held in session state.
    """
    row = {
        "event_id": dm.new_event_id(),
        "timestamp": dm.now_str(),
        "user": dm.clean_text(user or get_user(), 80),
        "role": role or get_role(),
        "action": action,
        "policy_id": policy_id or "",
        "issue_id": issue_id or "",
        "details": dm.clean_text(details, 500),
    }
    try:
        dm.append_audit_row(row)
        return True
    except dm.DataError as exc:
        st.error(f"The audit event could not be recorded. {exc}")
        return False
