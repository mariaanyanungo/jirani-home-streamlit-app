from __future__ import annotations

import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

MAKE_POLICY_ISSUE_WEBHOOK_URL = "MAKE_POLICY_ISSUE_WEBHOOK_URL"


def is_make_configured() -> bool:
    return bool(os.getenv(MAKE_POLICY_ISSUE_WEBHOOK_URL, "").strip())


def _iso_utc(value: str | None = None) -> str:
    if value:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            try:
                dt = datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalised_failure(
    message: str, http_status: int = 0, raw_response: dict | None = None
) -> dict:
    return {
        "success": False,
        "workflow_status": "Notification failed",
        "tracking_id": "",
        "message": message,
        "received_at": _iso_utc(),
        "http_status": http_status,
        "raw_response": raw_response or {},
    }


def _normalised_success(
    payload: dict, http_status: int, raw_response: dict | None = None
) -> dict:
    tracking_id = str(payload.get("tracking_id") or "").strip()
    message = str(
        payload.get("message") or "Policy Owner review task created successfully."
    ).strip()
    workflow_status = str(payload.get("workflow_status") or "In review").strip()
    received_at = str(payload.get("received_at") or _iso_utc()).strip()
    return {
        "success": True,
        "workflow_status": workflow_status,
        "tracking_id": tracking_id,
        "message": message,
        "received_at": received_at,
        "http_status": http_status,
        "raw_response": raw_response or {},
    }


def get_recent_audit_events(issue_id: str | None = None, limit: int = 10) -> list[dict]:
    try:
        from utils import data_manager as dm

        log = dm.load_audit(notify=False)
        if log.empty:
            return []

        df = log.copy()
        issue_key = str(issue_id or "").strip()
        if issue_key:
            df = df[df["issue_id"].astype(str) == issue_key]
        if df.empty and issue_key:
            df = log.copy()

        df = df.sort_values("timestamp", ascending=False).head(limit)
        return [
            {
                "timestamp": str(row.get("timestamp", "")),
                "user": str(row.get("user", "")),
                "role": str(row.get("role", "")),
                "action": str(row.get("action", "")),
                "details": str(row.get("details", "")),
            }
            for _, row in df.iterrows()
        ]
    except Exception:
        return []


def build_policy_issue_payload(
    issue_record: dict, audit_events: list[dict] | None = None
) -> dict:
    issue_id = str(issue_record.get("issue_id") or "")
    event_list = list(audit_events or [])
    if not event_list and issue_id:
        event_list = get_recent_audit_events(issue_id)

    summary = {
        "event_count": len(event_list),
        "latest_timestamp": event_list[0]["timestamp"] if event_list else "",
        "issue_id": issue_id,
    }
    return {
        "event_type": "policy_issue_submitted",
        "issue_id": issue_id,
        "policy_id": str(issue_record.get("policy_id") or ""),
        "issue_type": str(issue_record.get("issue_type") or ""),
        "ticket_reference": str(issue_record.get("ticket_reference") or ""),
        "description": str(issue_record.get("description") or ""),
        "reported_by": str(issue_record.get("reported_by") or ""),
        "reported_date": str(issue_record.get("reported_date") or ""),
        "assigned_to": str(issue_record.get("assigned_to") or "Relevant Policy Owner"),
        "status": str(issue_record.get("status") or "Open"),
        "source_system": "Jirani Home Controlled Policy Library",
        "submitted_at": _iso_utc(
            issue_record.get("workflow_last_updated")
            or issue_record.get("last_updated")
            or _iso_utc()
        ),
        "audit_summary": summary,
        "audit_events": event_list,
    }


def send_policy_issue_to_make(issue_record: dict, timeout_seconds: int = 20) -> dict:
    webhook_url = os.getenv(MAKE_POLICY_ISSUE_WEBHOOK_URL, "").strip()
    received_at = _iso_utc()

    if not webhook_url:
        return {
            "success": False,
            "workflow_status": "Not configured",
            "tracking_id": "",
            "message": "Local prototype mode: the Make webhook URL is not configured. The policy issue was saved locally, but the review workflow was not triggered.",
            "received_at": received_at,
            "http_status": 0,
            "raw_response": {},
        }

    payload = build_policy_issue_payload(
        issue_record,
        get_recent_audit_events(issue_record.get("issue_id")),
    )

    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(
            webhook_url, json=payload, headers=headers, timeout=timeout_seconds
        )
    except requests.exceptions.Timeout:
        return _normalised_failure(
            "The Make workflow request timed out after waiting 20 seconds.", 0, {}
        )
    except requests.exceptions.ConnectionError:
        return _normalised_failure(
            "The Make webhook could not be reached. Check the webhook URL and network connection.",
            0,
            {},
        )
    except requests.exceptions.RequestException as exc:
        return _normalised_failure(f"The Make webhook request failed: {exc}", 0, {})

    try:
        response_body = response.json() if response.text else {}
    except ValueError:
        response_body = {"raw_text": response.text}

    if response.status_code in (200, 201, 202):
        if not isinstance(response_body, dict):
            return _normalised_failure(
                "Invalid JSON response from the Make webhook.",
                response.status_code,
                response_body,
            )
        tracking_id = str(response_body.get("tracking_id") or "").strip()
        message = str(
            response_body.get("message")
            or "Policy Owner review task created successfully."
        ).strip()
        if not tracking_id:
            return _normalised_failure(
                "The Make webhook response did not include a tracking ID.",
                response.status_code,
                response_body,
            )
        return _normalised_success(
            {
                "tracking_id": tracking_id,
                "message": message,
                "workflow_status": response_body.get("workflow_status") or "In review",
                "received_at": response_body.get("received_at") or received_at,
            },
            response.status_code,
            response_body,
        )

    if response.status_code == 400:
        return _normalised_failure(
            "Bad request: the Make webhook rejected the issue payload.",
            response.status_code,
            response_body,
        )
    if response.status_code == 401:
        return _normalised_failure(
            "Unauthorized: the Make webhook is not authorized to receive this request.",
            response.status_code,
            response_body,
        )
    if response.status_code == 404:
        return _normalised_failure(
            "Not found: the Make webhook URL is incorrect or the scenario is unavailable.",
            response.status_code,
            response_body,
        )
    if response.status_code == 500:
        return _normalised_failure(
            "Internal server error: the Make workflow failed while processing the policy issue.",
            response.status_code,
            response_body,
        )

    if isinstance(response_body, dict) and response_body.get("message"):
        return _normalised_failure(
            str(response_body["message"]), response.status_code, response_body
        )
    return _normalised_failure(
        f"The Make workflow returned HTTP {response.status_code}.",
        response.status_code,
        response_body,
    )
