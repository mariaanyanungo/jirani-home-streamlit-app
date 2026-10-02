import importlib
import sys
import types
import unittest

requests_stub = types.ModuleType("requests")
requests_stub.exceptions = types.SimpleNamespace(
    Timeout=TimeoutError,
    ConnectionError=ConnectionError,
    RequestException=Exception,
)
requests_stub.post = lambda *args, **kwargs: None
sys.modules.setdefault("requests", requests_stub)

dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", dotenv_stub)

streamlit_stub = types.ModuleType("streamlit")
streamlit_stub.error = lambda *args, **kwargs: None
streamlit_stub.info = lambda *args, **kwargs: None
sys.modules.setdefault("streamlit", streamlit_stub)

pandas_stub = types.ModuleType("pandas")
pandas_stub.DataFrame = object
pandas_stub.read_csv = lambda *args, **kwargs: None
pandas_stub.errors = types.SimpleNamespace(
    ParserError=Exception,
    EmptyDataError=Exception,
)
pandas_stub.to_datetime = lambda *args, **kwargs: None
pandas_stub.isna = lambda *args, **kwargs: False
pandas_stub.Series = list
sys.modules.setdefault("pandas", pandas_stub)

sys.path.insert(0, "/home/Student/jirani_policy_library")

make_integration = importlib.import_module("utils.make_integration")


class MakeIntegrationPayloadTest(unittest.TestCase):
    def test_build_payload_includes_audit_summary(self):
        payload = make_integration.build_policy_issue_payload(
            {
                "issue_id": "ISS-20241001-ABC123",
                "policy_id": "P001",
                "issue_type": "Missing policy",
                "ticket_reference": "CASE-1042",
                "description": "The policy is missing.",
                "reported_by": "Alice",
                "reported_date": "2024-10-01",
                "assigned_to": "Relevant Policy Owner",
            },
            audit_events=[
                {
                    "timestamp": "2024-10-01 10:00:00",
                    "action": "Policy issue saved locally",
                    "details": "Issue was recorded.",
                },
                {
                    "timestamp": "2024-10-01 10:05:00",
                    "action": "Policy issue sent to Make workflow",
                    "details": "Webhook accepted.",
                },
            ],
        )

        self.assertEqual(payload["issue_id"], "ISS-20241001-ABC123")
        self.assertEqual(payload["audit_summary"]["event_count"], 2)
        self.assertEqual(
            payload["audit_events"][0]["action"], "Policy issue saved locally"
        )


if __name__ == "__main__":
    unittest.main()
