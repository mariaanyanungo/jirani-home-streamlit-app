"""Support Agent Policy Library: browse, search and verify current approved policies."""

from __future__ import annotations

import streamlit as st

from utils import access_control as ac
from utils import audit
from utils import data_manager as dm

ac.setup_page("Support Agent Library")
ac.page_header(
    "Support Agent Policy Library",
    "Find and verify the current approved policy before you respond to a customer.",
)

st.info(
    "Use only policies labelled Current approved when preparing customer-response guidance."
)

policies = dm.load_policies()
if policies.empty:
    st.warning(
        "No policies could be displayed. If a data error is shown above, please contact "
        "the Policy Owner / Administrator."
    )
    st.stop()

visible = dm.agent_visible_policies(policies)
current_total = int((policies["status"] == dm.STATUS_CURRENT).sum())
if current_total > len(visible):
    st.caption(
        f"{current_total - len(visible)} current policy record(s) are hidden because required "
        "governance metadata is incomplete. Please report this to the Policy Owner."
    )


def check_requested_policy(all_policies, visible_policies):
    """Handle a policy opened through a URL (?policy_id=...) or session-state route.

    Superseded or otherwise non-current policies are refused and the attempt is audited.
    """
    requested = st.query_params.get("policy_id") or st.session_state.get(
        "selected_policy_id"
    )
    if not requested:
        return None
    requested = str(requested).strip()
    match = all_policies[all_policies["policy_id"] == requested]
    if match.empty:
        st.warning("The requested policy ID was not found in the library.")
        return None
    row = match.iloc[0]
    if requested in set(visible_policies["policy_id"]):
        return requested
    if row["status"] in dm.SUPERSEDED_STATUSES:
        st.error(dm.RESTRICTED_SUPERSEDED_MESSAGE)
    else:
        st.error(
            "Access restricted. This policy is not a current approved policy and cannot be "
            "used for customer-response guidance."
        )
    blocked = st.session_state.setdefault("_blocked_policy_attempts", set())
    if requested not in blocked:
        blocked.add(requested)
        audit.log_event(
            audit.ACTION_ACCESS_BLOCKED,
            policy_id=requested,
            details=(
                f"Attempt to open a policy with status '{row['status']}' through a URL or "
                "state route was blocked."
            ),
        )
    return None


def field(col, label, value):
    col.caption(label)
    col.markdown(f"**{value if str(value).strip() else '—'}**")


def show_policy(row, can_record):
    with st.container(border=True):
        st.success("Current approved policy")
        st.subheader(row["title"])
        days = dm.days_until(row["next_review_date"])
        if days is not None and days <= dm.REVIEW_WINDOW_DAYS:
            label = "Review overdue" if days < 0 else "Review due soon"
            st.markdown(ac.badge(label, "amber"), unsafe_allow_html=True)

        a, b, c = st.columns(3)
        field(a, "Policy ID", row["policy_id"])
        field(b, "Category", row["category"])
        field(c, "Version", row["version"])
        a, b, c = st.columns(3)
        field(a, "Effective date", row["effective_date"])
        field(b, "Approval date", row["approval_date"])
        field(c, "Approval status", row["approval_status"])
        a, b, c = st.columns(3)
        field(a, "Status", row["status"])
        field(b, "Named owner", row["owner"])
        field(c, "Next review date", row["next_review_date"])

        st.markdown("#### Policy content")
        st.write(row["content"])

        if can_record:
            if st.button(
                "Record policy checked",
                key=f"record_{row['policy_id']}",
                type="primary",
            ):
                saved = audit.log_event(
                    audit.ACTION_POLICY_VERIFIED,
                    policy_id=row["policy_id"],
                    details=(
                        f"Checked {row['title']} v{row['version']} (status: {row['status']}; "
                        f"next review {row['next_review_date']})."
                    ),
                )
                if saved:
                    st.success("Policy check recorded in the audit log.")
        else:
            st.caption("Read-only view: only Support Agents can record a policy check.")


preselect = check_requested_policy(policies, visible)

counts = visible["category"].value_counts().to_dict()
options = ["All categories"] + dm.CATEGORIES


def category_label(option):
    if option == "All categories":
        return f"All categories ({len(visible)})"
    return f"{option} ({counts.get(option, 0)})"


category = st.radio(
    "Policy index: browse by category",
    options,
    format_func=category_label,
    horizontal=True,
)
query = st.text_input(
    "Search by policy title or keyword",
    placeholder="For example: returns, courier status, warranty",
)

results = visible
if category != "All categories":
    results = results[results["category"] == category]
results = dm.search_policies(results, query)

st.markdown(
    f"**{len(results)}** current approved polic{'y' if len(results) == 1 else 'ies'} found"
)

selected_id = None
if results.empty:
    st.info(
        "No current approved policies match your search. Try a different keyword or choose "
        "another category. If a policy seems to be missing, use the Report Policy Issue page."
    )
else:
    table = results[
        [
            "title",
            "category",
            "version",
            "effective_date",
            "status",
            "owner",
            "next_review_date",
        ]
    ].rename(
        columns={
            "title": "Title",
            "category": "Category",
            "version": "Version",
            "effective_date": "Effective date",
            "status": "Status",
            "owner": "Owner",
            "next_review_date": "Next review date",
        }
    )
    st.dataframe(table, hide_index=True)

    labels = {
        r.policy_id: f"{r.title} — v{r.version} ({r.category})"
        for r in visible.itertuples()
    }
    ids = results["policy_id"].tolist()
    default_index = ids.index(preselect) if preselect in ids else None
    selected_id = st.selectbox(
        "Open a policy to verify its details",
        options=ids,
        index=default_index,
        format_func=lambda pid: labels.get(pid, pid),
        placeholder="Select a policy",
    )

if selected_id is None and preselect:
    selected_id = preselect

if selected_id:
    chosen = visible[visible["policy_id"] == selected_id]
    if chosen.empty:
        st.error(dm.RESTRICTED_SUPERSEDED_MESSAGE)
    else:
        show_policy(chosen.iloc[0], ac.can("record_check"))
