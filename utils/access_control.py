"""Prototype role simulation, shared page setup and small UI helpers.

IMPORTANT: this is a simulation for requirements validation. The role is chosen
from a sidebar drop-down. There is no login, no identity provider and no real
security. Production authentication is out of scope.
"""

from __future__ import annotations

import html

import streamlit as st

from utils import data_manager as dm

ROLE_AGENT = "Support Agent"
ROLE_OWNER = "Policy Owner / Administrator"
ROLE_LEAD = "Support Lead"
ROLE_GM = "General Manager"
ROLES = [ROLE_AGENT, ROLE_OWNER, ROLE_LEAD, ROLE_GM]

SESSION_ROLE = "role"
SESSION_USER = "user_name"
SESSION_LOGIN_NAME = "login_name"
SESSION_AUTHENTICATED = "authenticated"
DEFAULT_USER = "Demo User"
LOGIN_PASSWORD = "Jirani123"
LOGIN_USERS = {
    "policy_owner": {"role": ROLE_OWNER, "display_name": "Policy Owner"},
    "support_agent": {"role": ROLE_AGENT, "display_name": "Support Agent"},
    "support_lead": {"role": ROLE_LEAD, "display_name": "Support Lead"},
    "general_manager": {"role": ROLE_GM, "display_name": "General Manager"},
}

SIMULATION_LABEL = "Prototype role simulation — not production authentication"
PROTOTYPE_WARNING = (
    "Prototype only: this app uses sample data and simulated role-based access. "
    "It does not connect to customer messages, orders, refunds, warehouse systems, "
    "courier systems, CRM systems, or AI tools."
)

PERMISSIONS = {
    "browse_library": {ROLE_AGENT, ROLE_OWNER, ROLE_LEAD},
    "record_check": {ROLE_AGENT},
    "report_issue": {ROLE_AGENT},
    "manage_policies": {ROLE_OWNER},
    "view_dashboard": {ROLE_LEAD, ROLE_OWNER, ROLE_GM},
    "view_gm_summary": {ROLE_GM},
}


def init_session() -> None:
    st.session_state.setdefault(SESSION_ROLE, ROLE_AGENT)
    st.session_state.setdefault(SESSION_USER, DEFAULT_USER)
    st.session_state.setdefault(SESSION_LOGIN_NAME, "")
    st.session_state.setdefault(SESSION_AUTHENTICATED, False)
    if st.session_state[SESSION_ROLE] not in ROLES:
        st.session_state[SESSION_ROLE] = ROLE_AGENT


def validate_login(username: str, password: str) -> bool:
    cleaned_name = (username or "").strip().lower()
    if not cleaned_name or not password:
        return False
    profile = LOGIN_USERS.get(cleaned_name)
    if profile is None:
        return False
    return password == LOGIN_PASSWORD


def login(username: str, password: str) -> bool:
    cleaned_name = (username or "").strip().lower()
    if not validate_login(cleaned_name, password):
        return False
    profile = LOGIN_USERS[cleaned_name]
    st.session_state[SESSION_AUTHENTICATED] = True
    st.session_state[SESSION_LOGIN_NAME] = cleaned_name
    st.session_state[SESSION_ROLE] = profile["role"]
    st.session_state[SESSION_USER] = profile["display_name"]
    return True


def logout() -> None:
    st.session_state[SESSION_AUTHENTICATED] = False
    st.session_state[SESSION_LOGIN_NAME] = ""
    st.session_state[SESSION_ROLE] = ROLE_AGENT
    st.session_state[SESSION_USER] = DEFAULT_USER


def is_logged_in() -> bool:
    init_session()
    return bool(st.session_state.get(SESSION_AUTHENTICATED, False))


def get_role() -> str:
    init_session()
    return st.session_state[SESSION_ROLE]


def get_user() -> str:
    init_session()
    return st.session_state[SESSION_USER]


def can(action: str) -> bool:
    return get_role() in PERMISSIONS.get(action, set())


def require_access(action: str, denied_message: str) -> None:
    """Stop the page with an access-denied message if the role lacks permission."""
    if not is_logged_in():
        st.error("Please log in to access this application.")
        st.stop()
    if not can(action):
        st.error(denied_message)
        st.caption(f"Current role: {get_role()}.")
        st.stop()


def render_login_form() -> None:
    st.markdown("## Login required")
    st.caption(
        "Use one of the hardcoded usernames and the shared password to access your dashboard."
    )
    st.caption(
        "Valid usernames: policy_owner, support_agent, support_lead, general_manager"
    )
    with st.form("login_form"):
        username = st.text_input("Username", placeholder="policy_owner")
        password = st.text_input("Password", type="password", placeholder="Jirani123")
        submitted = st.form_submit_button("Log in")

    if submitted:
        if login(username, password):
            st.success(f"Welcome, {get_user()}.")
            st.rerun()
        else:
            st.error("Invalid username or password.")
    st.stop()


_CSS = """
<style>
.jh-header {background: linear-gradient(90deg, #0B3C49, #145A6B); color: #FFFFFF;
            padding: 18px 24px; border-radius: 10px; margin-bottom: 1rem;}
.jh-header h1 {color: #FFFFFF !important; margin: 0; padding: 0; font-size: 1.9rem;}
.jh-header p {color: #D5E8EC; margin: 0.3rem 0 0 0; font-size: 1rem;}
.jh-badge {display: inline-block; padding: 2px 10px; border-radius: 12px;
           font-size: 0.8rem; font-weight: 600; margin-right: 6px;}
.jh-green {background: #DDF3E4; color: #14632B; border: 1px solid #14632B55;}
.jh-red {background: #FADBD8; color: #8E1B1B; border: 1px solid #8E1B1B55;}
.jh-amber {background: #FFE8B3; color: #7A4B00; border: 1px solid #7A4B0055;}
.jh-teal {background: #D6EEF2; color: #0B3C49; border: 1px solid #0B3C4955;}
.jh-grey {background: #E6E9EB; color: #37474F; border: 1px solid #37474F55;}
.jh-banner-red {background: #B71C1C; color: #FFFFFF; padding: 14px 18px; border-radius: 8px;
                font-weight: 700; font-size: 1.05rem; margin: 0.5rem 0 1rem 0;}
</style>
"""


def apply_styles() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    sub = f"<p>{html.escape(subtitle)}</p>" if subtitle else ""
    st.markdown(
        f'<div class="jh-header"><h1>{html.escape(title)}</h1>{sub}</div>',
        unsafe_allow_html=True,
    )


def badge(text: str, kind: str = "grey") -> str:
    """Return badge HTML. The text is escaped so user input is never executed."""
    return f'<span class="jh-badge jh-{kind}">{html.escape(str(text))}</span>'


_BADGE_KIND = {
    dm.STATUS_CURRENT: "green",
    dm.STATUS_SUPERSEDED: "red",
    dm.STATUS_OUTDATED: "red",
    dm.STATUS_ARCHIVE_ONLY: "grey",
    dm.STATUS_DUPLICATE: "grey",
    dm.STATUS_CLARIFY: "amber",
    dm.ISSUE_OPEN: "teal",
    dm.ISSUE_IN_REVIEW: "amber",
    dm.ISSUE_RESOLVED: "green",
}


def status_badge(status: str) -> str:
    return badge(status, _BADGE_KIND.get(status, "grey"))


def superseded_banner() -> None:
    st.markdown(
        f'<div class="jh-banner-red">{html.escape(dm.SUPERSEDED_WARNING)}</div>',
        unsafe_allow_html=True,
    )


def render_sidebar() -> None:
    init_session()
    with st.sidebar:
        st.markdown("## Jirani Home")
        st.markdown("**Controlled Policy Library (prototype)**")
        st.caption(f"Logged in as **{get_user()}** — {get_role()}")

        if st.button("Log out"):
            logout()
            st.rerun()

        st.divider()
        st.markdown("**Navigation guidance**")
        st.caption(
            "Use the page list above to open a screen. Support Agents use the Library and "
            "Report Policy Issue pages. Policy Owners use Policy Owner Admin. The Support Lead "
            "and General Manager use the dashboard pages. A page your role cannot use shows an "
            "access-denied message."
        )

        st.divider()
        st.markdown("**Status summary**")
        counts = dm.get_summary_counts()
        show = lambda v: "n/a" if v is None else v  # noqa: E731
        st.markdown(
            f"- Current policies: **{show(counts['current'])}**\n"
            f"- Superseded policies: **{show(counts['superseded'])}**\n"
            f"- Open policy issues: **{show(counts['open_issues'])}**"
        )


def setup_page(page_title: str) -> None:
    """First call on every page: page config, styles and the shared sidebar."""
    st.set_page_config(
        page_title=f"{page_title} | Jirani Home Policy Library",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_styles()

    public_pages = {"Home", "Support Agent Library", "Report Policy Issue"}
    if page_title in public_pages:
        render_sidebar()
        return

    if not is_logged_in():
        render_login_form()
        return
    render_sidebar()
