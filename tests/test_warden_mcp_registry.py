import json
from pathlib import Path
import unittest


REGISTRY_PATH = Path(__file__).resolve().parents[1] / "warden-mcp-registry.json"


class WardenMCPRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(REGISTRY_PATH.read_text())

    def test_registry_is_phase1_read_only(self):
        self.assertEqual(self.registry["spec_version"], "UFS-MANIFEST-v0.1")
        self.assertEqual(self.registry["governance_pipeline"]["phase"], 1)
        self.assertEqual(self.registry["governance_pipeline"]["execution_gate"], "human_authorization_required")

    def test_kernel_routes_authority_through_warden(self):
        kernel = self.registry["kernel"]
        self.assertEqual(kernel["mode"], "Zero-Standing-Privileges")
        self.assertEqual(kernel["arbitrator"], "warden.authorize_proposal")
        self.assertEqual(kernel["ledger"], "warden.append_ledger")

    def test_external_namespaces_are_read_only(self):
        namespaces = {entry["provider"]: entry for entry in self.registry["namespaces"]}
        self.assertEqual(namespaces["notion"]["access_level"], "Read-Only")
        self.assertEqual(namespaces["github"]["access_level"], "Read-Only")
        self.assertEqual(
            namespaces["github"]["permissions"],
            {
                "contents": "read",
                "metadata": "read",
                "issues": "read",
                "pull_requests": "read",
                "actions": "read",
                "commit_statuses": "read",
            },
        )


if __name__ == "__main__":
    unittest.main()
