"""Support Lead Dashboard: read-only monitoring of policy use, issues and audit events."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils import access_control as ac
from utils import audit
from utils import data_manager as dm

ac.setup_page("Support Lead Dashboard")
ac.page_header(
    "Support Lead Dashboard",
    "Read-only monitoring of policy quality, issues and audit activity.",
)
ac.require_access(
    "view_dashboard",
    "Access denied. Only a Support Lead, Policy Owner / Administrator, or General Manager "
    "can view the monitoring dashboard.",
)
st.info(
    "Read-only view. Policies, issues and statuses cannot be changed from this page."
)

policies = dm.load_policies()
issues = dm.load_issues()
audit_log = dm.load_audit()

current_n = int((policies["status"] == dm.STATUS_CURRENT).sum())
superseded_n = int(policies["status"].isin(dm.SUPERSEDED_STATUSES).sum())
open_n = int((issues["status"] == dm.ISSUE_OPEN).sum())
review_n = int((issues["status"] == dm.ISSUE_IN_REVIEW).sum())
resolved_n = int((issues["status"] == dm.ISSUE_RESOLVED).sum())
due = dm.due_for_review(policies) if not policies.empty else policies

make_completed = (
    int((issues["workflow_status"] == dm.WORKFLOW_STATUS_COMPLETED).sum())
    if not issues.empty
    else 0
)
make_failed = (
    int((issues["workflow_status"] == dm.WORKFLOW_STATUS_NOTIFICATION_FAILED).sum())
    if not issues.empty
    else 0
)
make_awaiting = (
    int(
        issues["workflow_status"]
        .isin(
            [
                dm.WORKFLOW_STATUS_SENDING,
                dm.WORKFLOW_STATUS_RETRYING,
                dm.WORKFLOW_STATUS_NOT_CONFIGURED,
                dm.WORKFLOW_STATUS_VALIDATION_FAILED,
                dm.WORKFLOW_STATUS_NOT_SENT,
            ]
        )
        .sum()
    )
    if not issues.empty
    else 0
)
retry_attempts = (
    int(issues["workflow_retry_count"].fillna(0).astype(int).sum())
    if not issues.empty
    else 0
)

st.subheader("Key counts")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Current approved policies", current_n)
k2.metric("Superseded policies", superseded_n)
k3.metric(f"Due for review ({dm.REVIEW_WINDOW_DAYS} days)", len(due))
k4.metric("Audit events", len(audit_log))
k5, k6, k7, k8 = st.columns(4)
k5.metric("Open policy issues", open_n)
k6.metric("In-review policy issues", review_n)
k7.metric("Resolved policy issues", resolved_n)
k8.metric("Make workflows completed", make_completed)

st.subheader("Make workflow delivery")
mk1, mk2, mk3, mk4 = st.columns(4)
mk1.metric("Make workflow notifications failed", make_failed)
mk2.metric("Issues awaiting workflow notification", make_awaiting)
mk3.metric("Retry attempts", retry_attempts)
mk4.metric(
    "Make workflow success rate",
    (
        f"{(make_completed / len(issues) * 100) if len(issues) else 0:.1f}%"
        if len(issues)
        else "0.0%"
    ),
)

st.subheader("Charts")
ch1, ch2 = st.columns(2)
with ch1:
    if issues.empty:
        st.info("No policy issues have been submitted yet.")
    else:
        workflow_counts = (
            issues.groupby(["issue_type", "workflow_status"])
            .size()
            .reset_index(name="Issues")
        )
        fig = px.bar(
            workflow_counts,
            x="issue_type",
            y="Issues",
            color="workflow_status",
            title="Workflow-status chart by issue type",
            barmode="stack",
        )
        st.plotly_chart(fig)
with ch2:
    if policies.empty:
        st.info("There are no policies to chart yet.")
    else:
        grouped = (
            policies.groupby(["category", "status"]).size().reset_index(name="Policies")
        )
        fig2 = px.bar(
            grouped,
            x="category",
            y="Policies",
            color="status",
            barmode="stack",
            title="Policies by category and status",
            labels={"category": "Category", "status": "Status"},
            color_discrete_map={
                dm.STATUS_CURRENT: "#1E8E3E",
                dm.STATUS_SUPERSEDED: "#C62828",
                dm.STATUS_OUTDATED: "#C62828",
                dm.STATUS_ARCHIVE_ONLY: "#78909C",
                dm.STATUS_DUPLICATE: "#8D6E63",
                dm.STATUS_CLARIFY: "#F9A825",
            },
        )
        fig2.update_yaxes(dtick=1, rangemode="tozero")
        st.plotly_chart(fig2)

st.subheader("Open and in-review policy issues")
unresolved = issues[issues["status"].isin([dm.ISSUE_OPEN, dm.ISSUE_IN_REVIEW])]
if unresolved.empty:
    st.success("There are no open or in-review policy issues.")
else:
    st.dataframe(
        unresolved[
            [
                "issue_id",
                "policy_id",
                "issue_type",
                "ticket_reference",
                "reported_by",
                "reported_date",
                "assigned_to",
                "status",
                "workflow_status",
                "workflow_tracking_id",
                "workflow_last_updated",
                "workflow_retry_count",
                "last_updated",
            ]
        ]
        .sort_values("last_updated", ascending=False)
        .rename(
            columns={
                "issue_id": "Issue ID",
                "policy_id": "Policy",
                "issue_type": "Issue type",
                "ticket_reference": "Ticket / case",
                "reported_by": "Reported by",
                "reported_date": "Reported",
                "assigned_to": "Assigned to",
                "status": "Status",
                "workflow_status": "Workflow status",
                "workflow_tracking_id": "Tracking ID",
                "workflow_last_updated": "Workflow last updated",
                "workflow_retry_count": "Retry count",
                "last_updated": "Last updated",
            }
        ),
        hide_index=True,
    )

st.subheader("Recent Make workflow failures")
failed = issues[
    issues["workflow_status"].isin(
        [
            dm.WORKFLOW_STATUS_NOTIFICATION_FAILED,
            dm.WORKFLOW_STATUS_VALIDATION_FAILED,
            dm.WORKFLOW_STATUS_NOT_CONFIGURED,
        ]
    )
]
if failed.empty:
    st.info("No recent Make workflow failures have been recorded.")
else:
    st.dataframe(
        failed[
            [
                "issue_id",
                "issue_type",
                "workflow_status",
                "workflow_message",
                "workflow_last_updated",
                "workflow_retry_count",
            ]
        ].rename(
            columns={
                "issue_id": "Issue ID",
                "issue_type": "Issue type",
                "workflow_status": "Workflow status",
                "workflow_message": "Failure reason",
                "workflow_last_updated": "Workflow last updated",
                "workflow_retry_count": "Retry count",
            }
        ),
        hide_index=True,
    )

st.caption(
    "These measures show Make workflow delivery status, not policy-resolution quality."
)

st.subheader(f"Policies due for review within {dm.REVIEW_WINDOW_DAYS} days")
if due.empty:
    st.success(
        f"No current policies are due for review within the next {dm.REVIEW_WINDOW_DAYS} days."
    )
else:
    st.warning(
        f"{len(due)} current polic{'y is' if len(due) == 1 else 'ies are'} due or overdue."
    )
    st.dataframe(
        due[
            [
                "policy_id",
                "title",
                "category",
                "version",
                "owner",
                "next_review_date",
                "days_to_review",
            ]
        ].rename(
            columns={
                "policy_id": "Policy ID",
                "title": "Title",
                "category": "Category",
                "version": "Version",
                "owner": "Owner",
                "next_review_date": "Next review date",
                "days_to_review": "Days to review",
            }
        ),
        hide_index=True,
    )

st.subheader("Audit trail preview (latest 10 events)")
if audit_log.empty:
    st.info("No audit events have been recorded yet.")
else:
    st.dataframe(
        audit_log.sort_values("timestamp", ascending=False).head(10), hide_index=True
    )

st.subheader("Pilot monitoring indicators")
checks = audit_log[
    (audit_log["role"] == ac.ROLE_AGENT)
    & (audit_log["action"] == audit.ACTION_POLICY_VERIFIED)
]
agents_checked = checks["user"].nunique() if not checks.empty else 0
blocked = int((audit_log["action"] == audit.ACTION_ACCESS_BLOCKED).sum())

indicators = pd.DataFrame(
    [
        {
            "Indicator": "Policy lookup time",
            "Target / measure": "Compare pilot lookup time with the baseline. Case evidence: lookup averaged 6 of 16 active minutes in an observed sample of return/damage tickets.",
            "Status / evidence": "Baseline to be measured",
        },
        {
            "Indicator": "Outdated-policy incidents",
            "Target / measure": "Target = zero pilot responses based on a superseded policy.",
            "Status / evidence": f"Measured through pilot sampling. Prototype shows {blocked} blocked attempt(s) to open a superseded policy.",
        },
        {
            "Indicator": "Policy-related corrections",
            "Target / measure": "Baseline and post-pilot comparison required. Baseline evidence: 6 drafts used an outdated policy, 4 were corrected before sending and 2 reached customers.",
            "Status / evidence": "Post-pilot comparison required",
        },
        {
            "Indicator": "Agent adoption",
            "Target / measure": "All six agents should receive training.",
            "Status / evidence": f"{agents_checked} of 6 agents have recorded a policy check in this prototype.",
        },
        {
            "Indicator": "Traceability",
            "Target / measure": "Target = at least 90% of sampled pilot responses linked to a current approved policy.",
            "Status / evidence": "To be measured in the pilot sample",
        },
    ]
)
st.dataframe(indicators, hide_index=True)
st.caption(
    "Indicators marked as to be measured need pilot data that this prototype does not collect."
)
