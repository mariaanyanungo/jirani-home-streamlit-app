"""Policy Owner / Administrator: register, publish, issue review, archive and audit log."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from utils import access_control as ac
from utils import audit
from utils import data_manager as dm

ac.setup_page("Policy Owner Admin")
ac.page_header(
    "Policy Owner / Administrator",
    "Manage policy versions, review issue reports, and inspect the archive and audit trail.",
)
ac.require_access(
    "manage_policies",
    "Access denied. Only a Policy Owner / Administrator can manage policies.",
)


def flash(kind: str, message: str) -> None:
    st.session_state["_admin_flash"] = (kind, message)
    st.rerun()


def show_flash() -> None:
    item = st.session_state.pop("_admin_flash", None)
    if item:
        kind, message = item
        getattr(st, kind)(message)


def field(col, label, value):
    col.caption(label)
    col.markdown(f"**{value if str(value).strip() else '—'}**")


def policy_label_map(df: pd.DataFrame) -> dict:
    return {
        r.policy_id: f"{r.policy_id} — {r.title} v{r.version} [{r.status}]"
        for r in df.itertuples()
    }


def _row_style(row):
    if row["Status"] in dm.ARCHIVE_STATUSES:
        css = "background-color: #FADBD8; color: #1B2A2F"
    elif str(row["Review flag"]).startswith(("Due", "Overdue")):
        css = "background-color: #FFE8B3; color: #1B2A2F"
    else:
        css = ""
    return [css] * len(row)


def render_register() -> None:
    policies = dm.load_policies()
    if policies.empty:
        st.info(
            "The policy register is empty. Publish a policy in the next tab to get started."
        )
        return

    st.caption(
        "All policies are listed. Amber rows are current policies due for review within "
        f"{dm.REVIEW_WINDOW_DAYS} days (or overdue). Red rows are superseded or archived and "
        "must not be used for customer responses."
    )
    status_options = dm.POLICY_STATUSES + [
        s for s in sorted(policies["status"].unique()) if s not in dm.POLICY_STATUSES
    ]
    category_options = dm.CATEGORIES + [
        c for c in sorted(policies["category"].unique()) if c not in dm.CATEGORIES
    ]
    f1, f2 = st.columns(2)
    chosen_status = f1.multiselect(
        "Filter by status", status_options, default=status_options
    )
    chosen_category = f2.multiselect(
        "Filter by category", category_options, default=category_options
    )

    view = dm.register_view(policies)
    due_count = len(dm.due_for_review(policies))
    if due_count:
        st.warning(
            f"{due_count} current policy record(s) are due for review within {dm.REVIEW_WINDOW_DAYS} days or overdue."
        )
    else:
        st.success(
            f"No current policies are due for review within {dm.REVIEW_WINDOW_DAYS} days."
        )

    view = view[
        view["status"].isin(chosen_status) & view["category"].isin(chosen_category)
    ]
    if view.empty:
        st.info("No policies match the selected filters.")
    else:
        shown = view[
            [
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
                "review_flag",
                "metadata_complete",
                "replaces_policy_id",
                "archive_reason",
            ]
        ].rename(
            columns={
                "policy_id": "Policy ID",
                "title": "Title",
                "category": "Category",
                "version": "Version",
                "effective_date": "Effective date",
                "approval_date": "Approval date",
                "approval_status": "Approval status",
                "status": "Status",
                "owner": "Owner",
                "next_review_date": "Next review date",
                "review_flag": "Review flag",
                "metadata_complete": "Metadata complete",
                "replaces_policy_id": "Replaces",
                "archive_reason": "Archive reason",
            }
        )
        st.dataframe(shown.style.apply(_row_style, axis=1), hide_index=True)

    labels = policy_label_map(policies)

    with st.expander("Change policy status (supersede, archive or classify)"):
        st.caption(
            "Use this to mark a policy as Superseded, Archive-only, Duplicate or Requires "
            "clarification. A policy can only become Current approved through the Publish New "
            "Version tab, so approval checks cannot be bypassed."
        )
        with st.form("status_change_form"):
            pid = st.selectbox(
                "Policy", list(labels.keys()), format_func=lambda p: labels[p]
            )
            new_status = st.selectbox(
                "New status",
                [
                    dm.STATUS_SUPERSEDED,
                    dm.STATUS_ARCHIVE_ONLY,
                    dm.STATUS_DUPLICATE,
                    dm.STATUS_CLARIFY,
                ],
            )
            reason = st.text_area("Reason / archive note (required)", max_chars=300)
            apply_change = st.form_submit_button("Apply status change", type="primary")
        if apply_change:
            current_row = policies[policies["policy_id"] == pid].iloc[0]
            errors = []
            if not reason.strip():
                errors.append("A reason is required for every status change.")
            if current_row["status"] == new_status:
                errors.append(f"{pid} already has the status '{new_status}'.")
            if errors:
                st.error(
                    "The status was not changed:\n\n"
                    + "\n".join(f"- {e}" for e in errors)
                )
            else:
                try:
                    df = dm.read_policies()
                    idx = df.index[df["policy_id"] == pid]
                    if len(idx) != 1:
                        raise dm.DataError(
                            f"Policy {pid} could not be found. Refresh and try again."
                        )
                    old_status = df.at[idx[0], "status"]
                    df.at[idx[0], "status"] = new_status
                    df.at[idx[0], "archive_reason"] = dm.clean_text(reason, 300)
                    if new_status == dm.STATUS_SUPERSEDED:
                        df.at[idx[0], "approval_status"] = dm.STATUS_SUPERSEDED
                    dm.save_policies(df)
                except dm.DataError as exc:
                    st.error(f"The status could not be changed. {exc}")
                else:
                    action = (
                        audit.ACTION_POLICY_SUPERSEDED
                        if new_status == dm.STATUS_SUPERSEDED
                        else audit.ACTION_STATUS_CHANGED
                    )
                    logged = audit.log_event(
                        action,
                        policy_id=pid,
                        details=f"Status changed from {old_status} to {new_status}. Reason: {reason.strip()}",
                    )
                    message = f"{pid} is now '{new_status}'."
                    if old_status == dm.STATUS_CURRENT:
                        remaining = df[
                            (df["category"] == current_row["category"])
                            & (df["status"] == dm.STATUS_CURRENT)
                        ]
                        if remaining.empty:
                            message += (
                                f" Note: the {current_row['category']} category now has no current "
                                "approved policy. Publish a replacement."
                            )
                    if not logged:
                        message += " Warning: the audit event could not be saved."
                    flash("success" if logged else "warning", message)

    with st.expander("Update next review date"):
        st.caption(
            "Record a new review date after a scheduled policy review. This is logged as a policy update."
        )
        with st.form("review_date_form"):
            pid2 = st.selectbox(
                "Policy",
                list(labels.keys()),
                format_func=lambda p: labels[p],
                key="review_policy",
            )
            new_date = st.date_input(
                "New next review date", value=None, key="review_new_date"
            )
            apply_date = st.form_submit_button("Update review date", type="primary")
        if apply_date:
            row = policies[policies["policy_id"] == pid2].iloc[0]
            eff = pd.to_datetime(row["effective_date"], errors="coerce")
            if new_date is None:
                st.error("Select the new next review date.")
            elif not pd.isna(eff) and new_date <= eff.date():
                st.error(
                    "The next review date must be after the policy's effective date."
                )
            else:
                try:
                    df = dm.read_policies()
                    idx = df.index[df["policy_id"] == pid2]
                    if len(idx) != 1:
                        raise dm.DataError(
                            f"Policy {pid2} could not be found. Refresh and try again."
                        )
                    old_date = df.at[idx[0], "next_review_date"]
                    df.at[idx[0], "next_review_date"] = new_date.isoformat()
                    dm.save_policies(df)
                except dm.DataError as exc:
                    st.error(f"The review date could not be updated. {exc}")
                else:
                    logged = audit.log_event(
                        audit.ACTION_POLICY_UPDATED,
                        policy_id=pid2,
                        details=f"Next review date changed from {old_date or 'blank'} to {new_date.isoformat()}.",
                    )
                    flash(
                        "success" if logged else "warning",
                        f"Next review date for {pid2} updated to {new_date.isoformat()}.",
                    )


def render_publish() -> None:
    policies = dm.load_policies()
    current = (
        policies[policies["status"] == dm.STATUS_CURRENT]
        if not policies.empty
        else policies
    )

    st.caption(
        "Publishing creates a new Current approved policy and marks the replaced version as "
        "Superseded. Owner, version, effective date and approval status are mandatory, as are "
        "the approval date, next review date and content."
    )
    new_option = "__new__"
    labels = policy_label_map(current) if not current.empty else {}
    options = [new_option] + list(labels.keys())
    selected = st.selectbox(
        "Policy to replace / update",
        options,
        format_func=lambda o: (
            "New policy (does not replace an existing one)"
            if o == new_option
            else labels[o]
        ),
    )
    prior = (
        None
        if selected == new_option
        else current[current["policy_id"] == selected].iloc[0]
    )

    if prior is not None:
        with st.container(border=True):
            st.markdown("**Version being replaced**")
            a, b, c, d = st.columns(4)
            field(a, "Policy ID", prior["policy_id"])
            field(b, "Version", prior["version"])
            field(c, "Status", prior["status"])
            field(d, "Owner", prior["owner"])
            a, b, c, d = st.columns(4)
            field(a, "Effective date", prior["effective_date"])
            field(b, "Approval date", prior["approval_date"])
            field(c, "Approval status", prior["approval_status"])
            field(d, "Next review date", prior["next_review_date"])
            with st.expander("Show current policy content"):
                st.write(prior["content"])

    cat_index = (
        dm.CATEGORIES.index(prior["category"])
        if prior is not None and prior["category"] in dm.CATEGORIES
        else 0
    )
    with st.form(f"publish_form_{selected}"):
        c1, c2 = st.columns(2)
        title = c1.text_input(
            "Policy title",
            value=prior["title"] if prior is not None else "",
            max_chars=120,
            key=f"pub_title_{selected}",
        )
        category = c2.selectbox(
            "Category", dm.CATEGORIES, index=cat_index, key=f"pub_cat_{selected}"
        )
        version = c1.text_input(
            "New version",
            placeholder="For example: 3.1",
            max_chars=20,
            key=f"pub_version_{selected}",
        )
        owner = c2.text_input(
            "Named owner",
            value=prior["owner"] if prior is not None else "",
            max_chars=80,
            key=f"pub_owner_{selected}",
        )
        effective = c1.date_input(
            "Effective date", value=None, key=f"pub_eff_{selected}"
        )
        approval_date = c2.date_input(
            "Approval date", value=None, key=f"pub_appdate_{selected}"
        )
        approval_status = c1.selectbox(
            "Approval status",
            dm.APPROVAL_OPTIONS,
            index=None,
            placeholder="Select approval status",
            key=f"pub_appstatus_{selected}",
        )
        next_review = c2.date_input(
            "Next review date", value=None, key=f"pub_next_{selected}"
        )
        content = st.text_area(
            "Policy content",
            value=prior["content"] if prior is not None else "",
            height=200,
            max_chars=5000,
            key=f"pub_content_{selected}",
        )
        publish = st.form_submit_button("Publish as Current approved", type="primary")

    if not publish:
        return

    record = {
        "title": title,
        "category": category,
        "version": version,
        "owner": owner,
        "effective_date": effective,
        "approval_date": approval_date,
        "approval_status": approval_status,
        "next_review_date": next_review,
        "content": content,
    }
    errors = dm.validate_policy_record(
        record, previous_version=prior["version"] if prior is not None else None
    )
    if errors:
        st.error(
            "The policy was not published. Please fix the following:\n\n"
            + "\n".join(f"- {e}" for e in errors)
        )
        return

    try:
        df = dm.read_policies()
        new_id = dm.next_policy_id(df)
        clean_title = dm.clean_text(title, 120)
        clean_version = dm.clean_text(version, 20)
        new_row = {
            "policy_id": new_id,
            "title": clean_title,
            "category": category,
            "version": clean_version,
            "effective_date": effective.isoformat(),
            "approval_date": approval_date.isoformat(),
            "approval_status": dm.APPROVED,
            "status": dm.STATUS_CURRENT,
            "owner": dm.clean_text(owner, 80),
            "next_review_date": next_review.isoformat(),
            "content": dm.clean_text(content, 5000),
            "replaces_policy_id": prior["policy_id"] if prior is not None else "",
            "archive_reason": "",
        }
        if prior is not None:
            idx = df.index[df["policy_id"] == prior["policy_id"]]
            if len(idx) != 1 or df.at[idx[0], "status"] != dm.STATUS_CURRENT:
                raise dm.DataError(
                    "The policy being replaced is no longer current. Refresh the page and try again."
                )
            df.at[idx[0], "status"] = dm.STATUS_SUPERSEDED
            df.at[idx[0], "approval_status"] = dm.STATUS_SUPERSEDED
            df.at[idx[0], "archive_reason"] = (
                f"Replaced by {clean_title} v{clean_version}"
            )
        new_df = pd.DataFrame([new_row])
        df = new_df if df.empty else pd.concat([df, new_df], ignore_index=True)
        dm.save_policies(df)
    except dm.DataError as exc:
        st.error(f"The policy could not be published. {exc}")
        return

    ok_publish = audit.log_event(
        audit.ACTION_POLICY_PUBLISHED,
        policy_id=new_id,
        details=(
            f"Published {clean_title} v{clean_version} as Current approved"
            + (
                f"; replaces {prior['policy_id']}."
                if prior is not None
                else " (new policy)."
            )
        ),
    )
    ok_super = True
    if prior is not None:
        ok_super = audit.log_event(
            audit.ACTION_POLICY_SUPERSEDED,
            policy_id=prior["policy_id"],
            details=f"Superseded by {new_id} ({clean_title} v{clean_version}).",
        )
    if prior is not None:
        message = (
            f"Published {clean_title} v{clean_version} as {new_id}. It replaces {prior['policy_id']} "
            f"(v{prior['version']}), which is now Superseded and has moved to the archive."
        )
    else:
        message = f"Published {clean_title} v{clean_version} as {new_id}. No earlier version was replaced."
    if not (ok_publish and ok_super):
        message += " Warning: an audit event could not be saved."
    flash("success" if (ok_publish and ok_super) else "warning", message)


def render_issue_review() -> None:
    issues = dm.load_issues()
    if issues.empty:
        st.info("No policy issue reports have been submitted yet.")
        return

    status_filter = st.multiselect(
        "Filter the list by status", dm.ISSUE_STATUSES, default=dm.ISSUE_STATUSES
    )
    listing = issues[issues["status"].isin(status_filter)].sort_values(
        "last_updated", ascending=False
    )
    st.dataframe(
        listing.rename(
            columns={
                "issue_id": "Issue ID",
                "policy_id": "Policy",
                "issue_type": "Issue type",
                "ticket_reference": "Ticket / case",
                "description": "Description",
                "reported_by": "Reported by",
                "reported_date": "Reported",
                "assigned_to": "Assigned to",
                "status": "Status",
                "resolution_notes": "Resolution notes",
                "last_updated": "Last updated",
            }
        ),
        hide_index=True,
    )

    st.markdown("### Review an issue")
    include_resolved = st.checkbox("Include resolved issues in the selector")
    pool = issues if include_resolved else issues[issues["status"] != dm.ISSUE_RESOLVED]
    if pool.empty:
        st.success(
            "There are no open or in-review issues. Everything has been resolved."
        )
        return

    labels = {
        r.issue_id: f"{r.issue_id} — {r.issue_type} ({r.status})"
        for r in pool.itertuples()
    }
    issue_id = st.selectbox(
        "Select an issue", list(labels.keys()), format_func=lambda i: labels[i]
    )
    row = issues[issues["issue_id"] == issue_id].iloc[0]

    with st.container(border=True):
        a, b, c = st.columns(3)
        field(a, "Issue type", row["issue_type"])
        field(b, "Related policy", row["policy_id"])
        field(c, "Ticket / case", row["ticket_reference"])
        a, b, c = st.columns(3)
        field(a, "Reported by", row["reported_by"])
        field(b, "Reported date", row["reported_date"])
        field(c, "Assigned to", row["assigned_to"])
        st.caption("Description")
        st.write(row["description"])
        st.markdown(ac.status_badge(row["status"]), unsafe_allow_html=True)

    current_index = (
        dm.ISSUE_STATUSES.index(row["status"])
        if row["status"] in dm.ISSUE_STATUSES
        else 0
    )
    with st.form(f"issue_review_form_{issue_id}"):
        new_status = st.selectbox(
            "Status",
            dm.ISSUE_STATUSES,
            index=current_index,
            key=f"rev_status_{issue_id}",
        )
        notes = st.text_area(
            "Resolution notes",
            value=row["resolution_notes"],
            max_chars=1000,
            key=f"rev_notes_{issue_id}",
        )
        save = st.form_submit_button("Save review", type="primary")

    if not save:
        return
    if new_status == dm.ISSUE_RESOLVED and not notes.strip():
        st.error(
            "Resolution notes are required before an issue can be marked Resolved."
        )
        return
    if new_status == row["status"] and notes.strip() == row["resolution_notes"].strip():
        st.info("No changes to save.")
        return

    try:
        df = dm.read_issues()
        idx = df.index[df["issue_id"] == issue_id]
        if len(idx) != 1:
            raise dm.DataError(
                f"Issue {issue_id} could not be found. Refresh and try again."
            )
        old_status = df.at[idx[0], "status"]
        df.at[idx[0], "status"] = new_status
        df.at[idx[0], "resolution_notes"] = dm.clean_text(notes, 1000)
        df.at[idx[0], "last_updated"] = dm.now_str()
        dm.save_issues(df)
    except dm.DataError as exc:
        st.error(f"The issue could not be updated. {exc}")
        return

    if new_status != old_status:
        action = (
            audit.ACTION_ISSUE_RESOLVED
            if new_status == dm.ISSUE_RESOLVED
            else audit.ACTION_ISSUE_STATUS
        )
        details = f"Status changed from {old_status} to {new_status}."
    else:
        action = audit.ACTION_ISSUE_UPDATED
        details = "Resolution notes updated."
    if notes.strip():
        details += f" Notes: {notes.strip()}"
    logged = audit.log_event(
        action, policy_id=row["policy_id"], issue_id=issue_id, details=details
    )
    message = f"Issue {issue_id} saved with status '{new_status}'."
    if not logged:
        message += " Warning: the audit event could not be saved."
    flash("success" if logged else "warning", message)


def render_archive() -> None:
    ac.superseded_banner()
    st.caption(
        "Archived policies are shown for governance and audit only. They must never be used "
        "when preparing customer responses."
    )
    policies = dm.load_policies()
    archive = (
        policies[policies["status"].isin(dm.ARCHIVE_STATUSES)]
        if not policies.empty
        else policies
    )
    if archive.empty:
        st.info("There are no superseded or archived policies yet.")
        return
    st.dataframe(
        archive[
            [
                "policy_id",
                "title",
                "category",
                "version",
                "status",
                "owner",
                "effective_date",
                "archive_reason",
            ]
        ].rename(
            columns={
                "policy_id": "Policy ID",
                "title": "Title",
                "category": "Category",
                "version": "Version",
                "status": "Status",
                "owner": "Owner",
                "effective_date": "Effective date",
                "archive_reason": "Archive reason",
            }
        ),
        hide_index=True,
    )
    for r in archive.itertuples():
        with st.expander(f"{r.policy_id} — {r.title} v{r.version} ({r.status})"):
            ac.superseded_banner()
            st.write(r.content)


def render_audit() -> None:
    log = dm.load_audit()
    if log.empty:
        st.info(
            "No audit events have been recorded yet. Actions such as publishing a policy or recording a policy check will appear here."
        )
        return
    f1, f2 = st.columns(2)
    actions = f1.multiselect("Filter by action", sorted(log["action"].unique()))
    users = f2.multiselect("Filter by user", sorted(log["user"].unique()))
    f3, f4, f5 = st.columns(3)
    policy_text = f3.text_input("Policy ID contains")
    issue_text = f4.text_input("Issue ID contains")
    detail_text = f5.text_input("Details contain")

    view = log
    if actions:
        view = view[view["action"].isin(actions)]
    if users:
        view = view[view["user"].isin(users)]
    if policy_text.strip():
        view = view[
            view["policy_id"].str.contains(policy_text.strip(), case=False, regex=False)
        ]
    if issue_text.strip():
        view = view[
            view["issue_id"].str.contains(issue_text.strip(), case=False, regex=False)
        ]
    if detail_text.strip():
        view = view[
            view["details"].str.contains(detail_text.strip(), case=False, regex=False)
        ]
    view = view.sort_values("timestamp", ascending=False)

    st.markdown(f"**{len(view)}** of {len(log)} audit event(s) shown")
    if view.empty:
        st.info("No audit events match these filters.")
    else:
        st.dataframe(view, hide_index=True)


show_flash()
tab_register, tab_publish, tab_issues, tab_archive, tab_audit = st.tabs(
    [
        "Policy Register",
        "Publish New Version",
        "Policy Issue Review",
        "Superseded Archive",
        "Audit Log",
    ]
)
with tab_register:
    render_register()
with tab_publish:
    render_publish()
with tab_issues:
    render_issue_review()
with tab_archive:
    render_archive()
with tab_audit:
    render_audit()
