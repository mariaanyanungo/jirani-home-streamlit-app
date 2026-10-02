"""General Manager Summary: high-level success measures and risk reduction (read-only)."""

from __future__ import annotations

import streamlit as st

from utils import access_control as ac
from utils import audit
from utils import data_manager as dm

ac.setup_page("General Manager Summary")
ac.page_header(
    "General Manager Summary",
    "High-level success measures and risk reduction for the controlled policy library.",
)
ac.require_access(
    "view_gm_summary",
    "Access denied. Only the General Manager can view this summary.",
)
st.caption(
    "Read-only view. This page shows counts and measures only. Detailed policy content is not "
    "shown to the General Manager role."
)

policies = dm.load_policies()
issues = dm.load_issues()
audit_log = dm.load_audit()

current = policies[policies["status"] == dm.STATUS_CURRENT]
visible = dm.agent_visible_policies(policies) if not policies.empty else policies
archived_n = int(policies["status"].isin(dm.ARCHIVE_STATUSES).sum())
superseded_n = int(policies["status"].isin(dm.SUPERSEDED_STATUSES).sum())
open_n = int((issues["status"] == dm.ISSUE_OPEN).sum())
in_review_n = int((issues["status"] == dm.ISSUE_IN_REVIEW).sum())
due_n = len(dm.due_for_review(policies)) if not policies.empty else 0
if issues.empty:
    workflow_completed_n = 0
else:
    workflow_completed_n = int(
        (issues["workflow_status"] == dm.WORKFLOW_STATUS_COMPLETED).sum()
    )

st.subheader("Headline indicators")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Current approved policies", len(current))
k2.metric("Superseded policies isolated from operational use", superseded_n)
k3.metric(
    "Open policy issues",
    open_n,
    help=f"A further {in_review_n} issue(s) are in review.",
)
k4.metric("Policies due for review", due_n)
k5.metric("Audit events", len(audit_log))

st.subheader("Workflow delivery")
if issues.empty:
    st.info("No submitted policy issues yet.")
else:
    delivery_rate = (workflow_completed_n / len(issues)) * 100 if len(issues) else 0.0
    st.metric("Policy issues delivered to review workflow", f"{delivery_rate:.1f}%")
    st.caption(
        "This prototype measure shows whether the Make workflow delivered a policy issue to the review process. It does not prove that the policy issue was resolved or that customer-service quality improved."
    )

covered = sum(
    1 for c in dm.CATEGORIES if not visible.empty and (visible["category"] == c).any()
)
all_complete = (
    (not current.empty)
    and bool(dm.metadata_complete(current).all())
    and len(current) == len(visible)
)
leaked = (
    int(visible["status"].isin(dm.ARCHIVE_STATUSES).sum()) if not visible.empty else 0
)
agent_checks = audit_log[
    (audit_log["role"] == ac.ROLE_AGENT)
    & (audit_log["action"] == audit.ACTION_POLICY_VERIFIED)
]
agents_n = agent_checks["user"].nunique() if not agent_checks.empty else 0
blocked_n = int((audit_log["action"] == audit.ACTION_ACCESS_BLOCKED).sum())
review_dates_ok = (not current.empty) and bool(
    (current["next_review_date"].str.strip() != "").all()
)
approval_ok = (not current.empty) and bool(
    (
        (current["approval_status"].str.strip() == dm.APPROVED)
        & (current["approval_date"].str.strip() != "")
    ).all()
)

criteria = [
    {
        "text": "100% of policies for Delivery, Returns, Damaged items, Warranty, and Account queries have named owner, status, version/effective date, approval status, and review date.",
        "met": covered == len(dm.CATEGORIES) and all_complete,
        "evidence": f"{covered} of {len(dm.CATEGORIES)} categories have a current approved policy; "
        f"{'all current policies have complete metadata' if all_complete else 'some current policies have incomplete metadata or a category has no current policy'}.",
    },
    {
        "text": "100% of identified superseded policies are segregated from the active library.",
        "met": leaked == 0,
        "evidence": f"{archived_n} superseded/archived polic{'y is' if archived_n == 1 else 'ies are'} held in the archive; "
        f"{leaked} appear in the agent-facing library.",
    },
    {
        "text": "All six agents can find and verify a current policy in test scenarios.",
        "met": agents_n >= 6,
        "evidence": f"{agents_n} of 6 agents have recorded a policy check in this prototype. Final confirmation comes from the test scenarios.",
        "pending_label": "In progress",
    },
    {
        "text": "Zero pilot customer-response drafts use a superseded policy.",
        "met": None,
        "evidence": f"Measured through pilot sampling. The prototype logged {blocked_n} blocked attempt(s) to open a superseded policy.",
    },
    {
        "text": "At least 90% of sampled pilot responses can be traced to a current approved policy.",
        "met": None,
        "evidence": "Measured through pilot sampling. The prototype does not hold customer responses.",
    },
    {
        "text": "Every current policy has a next review date and documented update/approval process.",
        "met": review_dates_ok and approval_ok,
        "evidence": (
            "Review dates and approval status/date are present on every current policy, and the Publish New Version workflow requires them."
            if (review_dates_ok and approval_ok)
            else "One or more current policies are missing a review date or approval information."
        ),
    },
]

st.subheader("Success criteria")
for number, item in enumerate(criteria, start=1):
    if item["met"] is True:
        state = ac.badge("Met on current data", "green")
    elif item["met"] is False:
        state = ac.badge(item.get("pending_label", "Not yet met"), "amber")
    else:
        state = ac.badge("Pilot measurement required", "grey")
    with st.container(border=True):
        st.markdown(f"**{number}. {item['text']}**")
        st.markdown(state, unsafe_allow_html=True)
        st.caption(item["evidence"])

st.subheader("Benefits and risk reduction")
b1, b2 = st.columns(2)
with b1:
    st.markdown(
        "- **Reduces outdated-policy risk:** superseded policies are hidden from agents and kept in a controlled archive.\n"
        "- **Supports accurate customer responses:** agents see one current approved version with a named owner."
    )
with b2:
    st.markdown(
        "- **Reduces time spent searching for policy:** one searchable library replaces a mixed folder.\n"
        "- **Maintains human control:** people choose customer responses and approve every policy change."
    )
st.caption(
    "Case evidence: a quality review found 6 initial drafts used an outdated policy, 4 were corrected "
    "before sending and 2 reached customers. Policy lookup averaged 6 of 16 active minutes in an observed sample."
)

st.subheader("Out of scope")
st.markdown(
    "- AI tools\n"
    "- Automatic customer replies\n"
    "- Order, refund, courier, warehouse and CRM integration\n"
    "- Policy-content changes without separate approval\n"
    "- Ticket-routing redesign\n"
    "- Finance approval-process changes\n"
    "- Warehouse and courier process redesign"
)
