"""Jirani Home Controlled Policy Library - main page.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from utils import access_control as ac
from utils import data_manager as dm

ac.setup_page("Home")

ac.page_header(
    "Jirani Home Controlled Policy Library",
    "A controlled, searchable source of current approved policies for customer-support staff.",
)

st.warning(ac.PROTOTYPE_WARNING)

for created_file in dm.ensure_data_files():
    st.info(
        f"The data file 'data/{created_file}' was missing or empty, so a new empty file "
        "with the correct columns was created."
    )

st.info(f"Logged in as **{ac.get_user()}** — {ac.get_role()}.")

st.subheader("Welcome")
st.write(
    "This prototype shows how Jirani Home support staff could use one controlled library of "
    "current approved policies instead of a folder that mixes current and outdated documents. "
    "Open a page from the page list based on your login role."
)

st.subheader("What each role can do")
c1, c2, c3, c4 = st.columns(4)
with c1:
    with st.container(border=True):
        st.markdown("**Support Agent**")
        st.markdown(
            "- Browse, search and filter current approved policies\n"
            "- View policy metadata\n"
            "- Record that a policy was checked\n"
            "- Submit a policy issue report\n"
            "- Cannot create, edit, publish, archive or change status\n"
            "- Never sees superseded policies in search"
        )
with c2:
    with st.container(border=True):
        st.markdown("**Policy Owner / Administrator**")
        st.markdown(
            "- View current and superseded policies\n"
            "- Publish a new current approved version\n"
            "- Mark a policy as superseded or archive-only\n"
            "- Review and resolve policy issues\n"
            "- Access the archive and audit log\n"
            "- Every change is audited"
        )
with c3:
    with st.container(border=True):
        st.markdown("**Support Lead**")
        st.markdown(
            "- Read-only access\n"
            "- View policy issues and audit events\n"
            "- See current and superseded policy counts\n"
            "- See policies due for review\n"
            "- Monitor quality indicators on simple dashboards\n"
            "- Cannot edit, publish or archive"
        )
with c4:
    with st.container(border=True):
        st.markdown("**General Manager**")
        st.markdown(
            "- Read-only access\n"
            "- High-level success-criteria dashboard\n"
            "- Risk-reduction summary\n"
            "- No detailed policy content\n"
            "- Cannot edit, publish or archive"
        )

st.subheader("Open a page")
l1, l2, l3, l4, l5 = st.columns(5)
l1.page_link("pages/1_Support_Agent_Library.py", label="Support Agent Library")
l2.page_link("pages/2_Report_Policy_Issue.py", label="Report Policy Issue")
l3.page_link("pages/3_Policy_Owner_Admin.py", label="Policy Owner Admin")
l4.page_link("pages/4_Support_Lead_Dashboard.py", label="Support Lead Dashboard")
l5.page_link("pages/5_General_Manager_Summary.py", label="General Manager Summary")

with st.expander("Requirements demonstrated"):
    st.markdown("""
**Functional requirements**
- **FR1** Central controlled library of current approved policies for Delivery, Returns, Damaged items, Warranty and Account queries
- **FR2** Policy metadata shown, and "Current approved" blocked unless owner, version, effective date and approval status are present
- **FR3** Policy classification; superseded policies hidden from agents, kept in an archive and shown with a red warning
- **FR4** Category index showing the current approved policy for each category
- **FR5** Search by title and keyword, category filter, current approved only by default, metadata verification
- **FR6** Policy issue reporting (missing, unclear, conflicting, potentially outdated) with owner review and status changes
- **FR7** Audit events for viewing/verifying, issue submission, publishing, updating, superseding, resolving and status changes

**Non-functional requirements**
- **NFR1** Usability: clear headings, tabs, status badges, captions and friendly error messages
- **NFR2** Information quality and governance: complete metadata on every current policy; publishing blocked when metadata is missing
- **NFR3** Availability simulation: local CSV files are created with correct headers if missing or empty
- **NFR4** Role-based permissions: only the Policy Owner / Administrator can publish, replace, archive or change status
- **NFR5** Audit trail and persistence to `audit_log.csv`, `policy_issues.csv` and `policies.csv` with validated, safe writes
- **NFR6** No API dependency: local files and Python packages only
- **NFR7** Basic protection through role simulation; real security is out of prototype scope
        """)
