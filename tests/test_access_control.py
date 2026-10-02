import importlib
import sys
import types
import unittest

streamlit_stub = types.ModuleType("streamlit")
streamlit_stub.session_state = {}
streamlit_stub.error = lambda *args, **kwargs: None
streamlit_stub.caption = lambda *args, **kwargs: None
streamlit_stub.stop = lambda *args, **kwargs: None
streamlit_stub.rerun = lambda *args, **kwargs: None
streamlit_stub.success = lambda *args, **kwargs: None
streamlit_stub.markdown = lambda *args, **kwargs: None
streamlit_stub.form = lambda *args, **kwargs: None
streamlit_stub.text_input = lambda *args, **kwargs: ""
streamlit_stub.button = lambda *args, **kwargs: False
streamlit_stub.divider = lambda *args, **kwargs: None
streamlit_stub.sidebar = types.SimpleNamespace(
    __enter__=lambda *args, **kwargs: None,
    __exit__=lambda *args, **kwargs: None,
)
streamlit_stub.set_page_config = lambda *args, **kwargs: None
streamlit_stub.columns = lambda *args, **kwargs: [None, None]
sys.modules.setdefault("streamlit", streamlit_stub)

pandas_stub = types.ModuleType("pandas")
pandas_stub.DataFrame = object
pandas_stub.Series = object
pandas_stub.isna = lambda *args, **kwargs: False
pandas_stub.to_datetime = lambda *args, **kwargs: None
pandas_stub.errors = types.SimpleNamespace(
    ParserError=Exception, EmptyDataError=Exception
)
sys.modules.setdefault("pandas", pandas_stub)

sys.path.insert(0, "/home/Student/jirani_policy_library")
access_control = importlib.import_module("utils.access_control")


class AccessControlLoginTest(unittest.TestCase):
    def setUp(self):
        streamlit_stub.session_state.clear()

    def test_valid_credentials_for_specific_roles(self):
        self.assertTrue(access_control.validate_login("policy_owner", "Jirani123"))
        self.assertTrue(access_control.validate_login("support_lead", "Jirani123"))
        self.assertTrue(access_control.validate_login("general_manager", "Jirani123"))
        self.assertFalse(access_control.validate_login("general_manager", "wrongpass"))

    def test_login_sets_role_and_authenticated_state(self):
        self.assertTrue(access_control.login("support_lead", "Jirani123"))
        self.assertTrue(streamlit_stub.session_state["authenticated"])
        self.assertEqual(streamlit_stub.session_state["role"], access_control.ROLE_LEAD)
        self.assertEqual(streamlit_stub.session_state["user_name"], "Support Lead")

    def test_invalid_user_has_no_access(self):
        self.assertFalse(access_control.validate_login("unknown_user", "Jirani123"))


if __name__ == "__main__":
    unittest.main()
