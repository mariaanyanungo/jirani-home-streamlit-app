"""Report a Policy Issue: Support Agents tell the Policy Owner about policy problems."""

from __future__ import annotations

from datetime import date

import streamlit as st

from utils import access_control as ac
from utils import audit
from utils import data_manager as dm
from utils.make_integration import is_make_configured, send_policy_issue_to_make

ac.setup_page("Report Policy Issue")
ac.page_header(
    "Report a Policy Issue",
    "Tell the Policy Owner when a policy is missing, unclear, conflicting or possibly outdated.",
)

st.info(
    "Do not enter customer names, contact details or other personal data. "
    "Use the ticket/case reference only."
)

policies = dm.load_policies()
visible = dm.agent_visible_policies(policies) if not policies.empty else policies
policy_labels = {
    r.policy_id: f"{r.policy_id} — {r.title} v{r.version} ({r.category})"
    for r in visible.itertuples()
}
policy_options = [""] + list(policy_labels.keys())
user = ac.get_user()


def save_local_issue(issue_record: dict) -> None:
    dm.append_issue_row(issue_record)
    audit.log_event(
        audit.ACTION_ISSUE_SAVED_LOCALLY,
        policy_id=issue_record.get("policy_id", ""),
        issue_id=issue_record.get("issue_id", ""),
        details=(
            f"{issue_record.get('issue_type', '')} reported for ticket "
            f"{issue_record.get('ticket_reference', '')}."
        ),
    )


def display_workflow_progress() -> None:
    st.subheader("Workflow progress")
    with st.status("Issue saved locally", state="complete"):
        st.write("1. Issue saved locally")
    with st.status("Sending policy issue to Make workflow", state="running"):
        st.write("2. Sending policy issue to Make workflow")
    with st.status("Make validating policy issue", state="running"):
        st.write("3. Make validating policy issue")
    with st.status("Policy Owner review task created", state="running"):
        st.write("4. Policy Owner review task created")
    with st.status("Workflow completed successfully", state="running"):
        st.write("5. Workflow completed successfully")


with st.form("policy_issue_form"):
    related = st.selectbox(
        "Related policy (optional)",
        options=policy_options,
        format_func=lambda pid: (
            "Not known / no related policy (for example, a missing policy)"
            if pid == ""
            else policy_labels[pid]
        ),
        help="Leave this as 'Not known' if you cannot find the policy.",
    )
    issue_type = st.selectbox("Issue type", dm.ISSUE_TYPES)
    ticket_reference = st.text_input(
        "Ticket / case reference", max_chars=40, placeholder="For example: CASE-1042"
    )
    description = st.text_area(
        "Description",
        max_chars=1000,
        height=150,
        placeholder="Explain what is missing, unclear, conflicting or outdated (at least 10 characters).",
    )
    col1, col2 = st.columns(2)
    col1.text_input(
        "Reported by",
        value=user,
        disabled=True,
        help="Taken from the sidebar user name.",
    )
    reported_date = col2.date_input(
        "Reported date", value=date.today(), max_value=date.today()
    )
    submitted = st.form_submit_button("Submit issue report", type="primary")

if submitted:
    errors = []
    if not ticket_reference.strip():
        errors.append("Ticket / case reference is required.")
    if len(description.strip()) < 10:
        errors.append("Description is required and must be at least 10 characters.")
    if not user.strip():
        errors.append("A user name is required. Enter one in the sidebar.")

    if errors:
        st.error(
            "The report was not submitted. Please fix the following:\n\n"
            + "\n".join(f"- {e}" for e in errors)
        )
    else:
        try:
            existing = dm.read_issues()
            issue_id = dm.new_issue_id(existing["issue_id"].tolist())
            stamp = dm.now_str()
            issue_record = {
                "issue_id": issue_id,
                "policy_id": related,
                "issue_type": issue_type,
                "ticket_reference": dm.clean_text(ticket_reference, 40),
                "description": dm.clean_text(description, 1000),
                "reported_by": dm.clean_text(user, 80),
                "reported_date": reported_date.isoformat(),
                "assigned_to": dm.DEFAULT_ASSIGNEE,
                "status": dm.ISSUE_OPEN,
                "resolution_notes": "",
                "last_updated": stamp,
                "workflow_status": dm.WORKFLOW_STATUS_SENDING,
                "workflow_tracking_id": "",
                "workflow_message": "",
                "workflow_last_updated": stamp,
                "workflow_retry_count": 0,
            }
            save_local_issue(issue_record)
        except dm.DataError as exc:
            st.error(f"Your report could not be saved. {exc}")
        else:
            display_workflow_progress()
            make_result = send_policy_issue_to_make(issue_record)

            if make_result["success"]:
                dm.update_issue_record(
                    issue_id,
                    {
                        "status": dm.ISSUE_IN_REVIEW,
                        "workflow_status": make_result.get(
                            "workflow_status", dm.WORKFLOW_STATUS_COMPLETED
                        ),
                        "workflow_tracking_id": make_result.get("tracking_id", ""),
                        "workflow_message": make_result.get("message", ""),
                        "workflow_last_updated": make_result.get(
                            "received_at", dm.now_str()
                        ),
                    },
                )
                audit.log_event(
                    audit.ACTION_MAKE_SENT,
                    policy_id=related,
                    issue_id=issue_id,
                    details=f"Make workflow completed for issue {issue_id}; tracking ID {make_result.get('tracking_id', '')}.",
                )
                st.success(
                    f"Issue {issue_id} was sent successfully to the Make review workflow."
                )
                with st.container(border=True):
                    st.markdown(f"**Issue ID:** {issue_id}")
                    st.markdown(f"**Issue status:** {dm.ISSUE_IN_REVIEW}")
                    st.markdown(
                        f"**Workflow status:** {make_result.get('workflow_status', dm.WORKFLOW_STATUS_COMPLETED)}"
                    )
                    st.markdown(
                        f"**Make tracking ID:** {make_result.get('tracking_id', '')}"
                    )
                    st.markdown(f"**Message:** {make_result.get('message', '')}")
                    st.markdown(
                        f"**Timestamp:** {make_result.get('received_at', dm.now_str())}"
                    )

                audit_log = dm.load_audit(notify=False)
                recent_audit = (
                    audit_log[audit_log["issue_id"].astype(str) == str(issue_id)]
                    if not audit_log.empty
                    else audit_log
                )
                if not recent_audit.empty:
                    st.subheader("Audit trail for this issue")
                    st.dataframe(
                        recent_audit.sort_values("timestamp", ascending=False)[
                            ["timestamp", "user", "role", "action", "details"]
                        ],
                        hide_index=True,
                    )
            else:
                if make_result.get("workflow_status") == "Not configured":
                    audit.log_event(
                        audit.ACTION_MAKE_NOT_CONFIGURED,
                        policy_id=related,
                        issue_id=issue_id,
                        details="Make webhook URL is not configured. Local record kept as Open.",
                    )
                    st.warning(make_result.get("message"))
                    st.code(
                        "MAKE_POLICY_ISSUE_WEBHOOK_URL=https://hook.make.com/replace-with-your-webhook-id"
                    )
                    st.info(
                        "Configure the webhook in a local .env file to enable the review workflow."
                    )
                else:
                    dm.update_issue_record(
                        issue_id,
                        {
                            "status": dm.ISSUE_OPEN,
                            "workflow_status": dm.WORKFLOW_STATUS_NOTIFICATION_FAILED,
                            "workflow_tracking_id": "",
                            "workflow_message": make_result.get("message", ""),
                            "workflow_last_updated": make_result.get(
                                "received_at", dm.now_str()
                            ),
                        },
                    )
                    audit.log_event(
                        audit.ACTION_MAKE_FAILED,
                        policy_id=related,
                        issue_id=issue_id,
                        details=make_result.get("message", ""),
                    )
                    st.warning(
                        "The Make workflow did not complete. The issue remains saved locally as Open."
                    )
                    with st.container(border=True):
                        st.markdown(f"**Issue ID:** {issue_id}")
                        st.markdown(f"**Issue status:** {dm.ISSUE_OPEN}")
                        st.markdown(
                            f"**Workflow status:** {dm.WORKFLOW_STATUS_NOTIFICATION_FAILED}"
                        )
                        st.markdown(
                            f"**Failure reason:** {make_result.get('message', '')}"
                        )
                        st.markdown(
                            f"**Timestamp:** {make_result.get('received_at', dm.now_str())}"
                        )

                    audit_log = dm.load_audit(notify=False)
                    recent_audit = (
                        audit_log[audit_log["issue_id"].astype(str) == str(issue_id)]
                        if not audit_log.empty
                        else audit_log
                    )
                    if not recent_audit.empty:
                        st.subheader("Audit trail for this issue")
                        st.dataframe(
                            recent_audit.sort_values("timestamp", ascending=False)[
                                ["timestamp", "user", "role", "action", "details"]
                            ],
                            hide_index=True,
                        )
                    if st.button("Retry Make workflow", key=f"retry_make_{issue_id}"):
                        retry_issue = dm.read_issues()
                        retry_match = retry_issue[retry_issue["issue_id"] == issue_id]
                        if retry_match.empty:
                            st.error(
                                f"The issue {issue_id} could not be found for retry."
                            )
                        elif not is_make_configured():
                            st.warning(
                                "Local prototype mode: the Make webhook URL is not configured. The policy issue was saved locally, but the review workflow was not triggered."
                            )
                            st.code(
                                "MAKE_POLICY_ISSUE_WEBHOOK_URL=https://hook.make.com/replace-with-your-webhook-id"
                            )
                            st.info(
                                "Add the webhook URL to your local .env file before retrying."
                            )
                        else:
                            current_record = retry_match.iloc[0].to_dict()
                            current_retry_count = int(
                                current_record.get("workflow_retry_count") or 0
                            )
                            dm.update_issue_record(
                                issue_id,
                                {
                                    "workflow_status": dm.WORKFLOW_STATUS_RETRYING,
                                    "workflow_message": "Retrying Make workflow",
                                    "workflow_last_updated": dm.now_str(),
                                    "workflow_retry_count": current_retry_count + 1,
                                },
                            )
                            audit.log_event(
                                audit.ACTION_MAKE_RETRIED,
                                policy_id=current_record.get("policy_id", ""),
                                issue_id=issue_id,
                                details=f"Retry attempt {current_retry_count + 1} for Make workflow.",
                            )
                            retry_result = send_policy_issue_to_make(current_record)
                            if retry_result["success"]:
                                dm.update_issue_record(
                                    issue_id,
                                    {
                                        "status": dm.ISSUE_IN_REVIEW,
                                        "workflow_status": retry_result.get(
                                            "workflow_status",
                                            dm.WORKFLOW_STATUS_COMPLETED,
                                        ),
                                        "workflow_tracking_id": retry_result.get(
                                            "tracking_id", ""
                                        ),
                                        "workflow_message": retry_result.get(
                                            "message", ""
                                        ),
                                        "workflow_last_updated": retry_result.get(
                                            "received_at", dm.now_str()
                                        ),
                                    },
                                )
                                st.success(f"Retry successful for issue {issue_id}.")
                            else:
                                dm.update_issue_record(
                                    issue_id,
                                    {
                                        "status": dm.ISSUE_OPEN,
                                        "workflow_status": dm.WORKFLOW_STATUS_NOTIFICATION_FAILED,
                                        "workflow_tracking_id": "",
                                        "workflow_message": retry_result.get(
                                            "message", ""
                                        ),
                                        "workflow_last_updated": retry_result.get(
                                            "received_at", dm.now_str()
                                        ),
                                    },
                                )
                                st.warning(
                                    f"Retry failed for issue {issue_id}. The local record remains Open."
                                )

st.subheader("My submitted reports")
issues = dm.load_issues()
mine = (
    issues[issues["reported_by"] == dm.clean_text(user, 80)]
    if not issues.empty
    else issues
)
if mine.empty:
    st.caption("You have not submitted any policy issue reports yet.")
else:
    mine = mine.sort_values("last_updated", ascending=False)
    table = mine[
        [
            "issue_id",
            "policy_id",
            "issue_type",
            "ticket_reference",
            "reported_date",
            "status",
            "workflow_status",
            "workflow_tracking_id",
            "workflow_last_updated",
            "workflow_retry_count",
            "last_updated",
        ]
    ].rename(
        columns={
            "issue_id": "Issue ID",
            "policy_id": "Policy",
            "issue_type": "Issue type",
            "ticket_reference": "Ticket / case",
            "reported_date": "Reported",
            "status": "Status",
            "workflow_status": "Workflow status",
            "workflow_tracking_id": "Workflow tracking ID",
            "workflow_last_updated": "Workflow last updated",
            "workflow_retry_count": "Retry count",
            "last_updated": "Last updated",
        }
    )
    st.dataframe(table, hide_index=True)

st.subheader("Workflow delivery")
workflow_records = mine[
    mine["workflow_status"].isin(
        [
            dm.WORKFLOW_STATUS_SENDING,
            dm.WORKFLOW_STATUS_RETRYING,
            dm.WORKFLOW_STATUS_NOTIFICATION_FAILED,
            dm.WORKFLOW_STATUS_VALIDATION_FAILED,
            dm.WORKFLOW_STATUS_NOT_CONFIGURED,
            dm.WORKFLOW_STATUS_NOT_SENT,
        ]
    )
]
if workflow_records.empty:
    st.caption("No workflow delivery issues are currently awaiting action.")
else:
    for row in workflow_records.itertuples(index=False):
        if row.workflow_status in (
            dm.WORKFLOW_STATUS_NOTIFICATION_FAILED,
            dm.WORKFLOW_STATUS_VALIDATION_FAILED,
            dm.WORKFLOW_STATUS_NOT_CONFIGURED,
        ):
            with st.container(border=True):
                st.markdown(f"**Issue ID:** {row.issue_id}")
                st.markdown(f"**Status:** {row.status}")
                st.markdown(f"**Workflow status:** {row.workflow_status}")
                st.markdown(f"**Retry count:** {row.workflow_retry_count}")
                if st.button(
                    "Retry Make workflow", key=f"delivery_retry_{row.issue_id}"
                ):
                    retry_issue = dm.read_issues()
                    match = retry_issue[retry_issue["issue_id"] == row.issue_id]
                    if match.empty:
                        st.error(f"Issue {row.issue_id} could not be found.")
                    elif not is_make_configured():
                        st.warning(
                            "Local prototype mode: the Make webhook URL is not configured. The policy issue was saved locally, but the review workflow was not triggered."
                        )
                        st.code(
                            "MAKE_POLICY_ISSUE_WEBHOOK_URL=https://hook.make.com/replace-with-your-webhook-id"
                        )
                    else:
                        current = match.iloc[0].to_dict()
                        retry_count = int(current.get("workflow_retry_count") or 0)
                        dm.update_issue_record(
                            row.issue_id,
                            {
                                "workflow_status": dm.WORKFLOW_STATUS_RETRYING,
                                "workflow_message": "Retrying Make workflow",
                                "workflow_last_updated": dm.now_str(),
                                "workflow_retry_count": retry_count + 1,
                            },
                        )
                        audit.log_event(
                            audit.ACTION_MAKE_RETRIED,
                            policy_id=current.get("policy_id", ""),
                            issue_id=row.issue_id,
                            details=f"Retry attempt {retry_count + 1} for Make workflow.",
                        )
                        retry_result = send_policy_issue_to_make(current)
                        if retry_result["success"]:
                            dm.update_issue_record(
                                row.issue_id,
                                {
                                    "status": dm.ISSUE_IN_REVIEW,
                                    "workflow_status": retry_result.get(
                                        "workflow_status", dm.WORKFLOW_STATUS_COMPLETED
                                    ),
                                    "workflow_tracking_id": retry_result.get(
                                        "tracking_id", ""
                                    ),
                                    "workflow_message": retry_result.get("message", ""),
                                    "workflow_last_updated": retry_result.get(
                                        "received_at", dm.now_str()
                                    ),
                                },
                            )
                            st.success(f"Retry successful for {row.issue_id}.")
                        else:
                            dm.update_issue_record(
                                row.issue_id,
                                {
                                    "status": dm.ISSUE_OPEN,
                                    "workflow_status": dm.WORKFLOW_STATUS_NOTIFICATION_FAILED,
                                    "workflow_tracking_id": "",
                                    "workflow_message": retry_result.get("message", ""),
                                    "workflow_last_updated": retry_result.get(
                                        "received_at", dm.now_str()
                                    ),
                                },
                            )
                            st.warning(f"Retry did not complete for {row.issue_id}.")
                    st.rerun()
