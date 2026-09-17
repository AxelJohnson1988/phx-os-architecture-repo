import json
from pathlib import Path
import unittest


REGISTRY_PATH = Path(__file__).resolve().parents[1] / "warden-mcp-registry.json"
SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"


class WardenMCPRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(REGISTRY_PATH.read_text())
        cls.circuit_breaker_schema = json.loads(
            (SCHEMAS_DIR / "warden-circuit-breaker-config.schema.json").read_text()
        )
        cls.audit_event_schema = json.loads(
            (SCHEMAS_DIR / "warden-execution-audit-event.schema.json").read_text()
        )

    def test_registry_is_phase2_with_human_gate(self):
        self.assertEqual(self.registry["spec_version"], "UFS-MANIFEST-v0.2")
        self.assertEqual(self.registry["governance_pipeline"]["phase"], 2)
        self.assertEqual(self.registry["governance_pipeline"]["execution_gate"], "human_authorization_required")
        self.assertEqual(
            self.registry["governance_pipeline"]["circuit_breaker_schema"],
            "schemas/warden-circuit-breaker-config.schema.json",
        )
        self.assertEqual(
            self.registry["governance_pipeline"]["audit_event_schema"],
            "schemas/warden-execution-audit-event.schema.json",
        )

    def test_kernel_routes_authority_through_warden(self):
        kernel = self.registry["kernel"]
        self.assertEqual(kernel["mode"], "Zero-Standing-Privileges")
        self.assertEqual(kernel["arbitrator"], "warden.authorize_proposal")
        self.assertEqual(kernel["ledger"], "warden.append_ledger")

    def test_external_namespaces_remain_read_only(self):
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

    def test_local_sandbox_namespace_is_hardened_and_receipted(self):
        local_sandbox = {entry["provider"]: entry for entry in self.registry["namespaces"]}["local_sandbox"]
        self.assertEqual(local_sandbox["access_level"], "Write-Execution")
        self.assertEqual(local_sandbox["runtime_isolation"], "kata-microvm")
        self.assertFalse(local_sandbox["security_profile"]["run_as_root"])
        self.assertEqual(local_sandbox["security_profile"]["cap_drop"], ["ALL"])
        self.assertTrue(local_sandbox["security_profile"]["read_only_rootfs"])
        self.assertTrue(local_sandbox["security_profile"]["no_new_privileges"])
        self.assertEqual(local_sandbox["approval_gate"], "human_authorization_required")
        self.assertEqual(local_sandbox["audit_event_stream"]["format"], "ECES")
        self.assertTrue(local_sandbox["audit_event_stream"]["append_only"])
        self.assertTrue(local_sandbox["audit_event_stream"]["signed"])

    def test_circuit_breaker_schema_is_fail_closed_capable(self):
        self.assertEqual(self.circuit_breaker_schema["title"], "WardenCircuitBreakerConfig")
        self.assertEqual(
            self.circuit_breaker_schema["required"],
            ["eval_timing", "default_state", "failure_thresholds", "recovery_policy"],
        )
        self.assertIn(
            "fail_closed",
            self.circuit_breaker_schema["properties"]["default_state"]["enum"],
        )
        self.assertIn(
            "arbitrator_unreachable",
            self.circuit_breaker_schema["properties"]["monitored_signals"]["items"]["enum"],
        )

    def test_audit_event_schema_enforces_deny_side_null_effect(self):
        self.assertEqual(self.audit_event_schema["title"], "WardenExecutionAuditEvent")
        self.assertEqual(
            self.audit_event_schema["properties"]["delta_hash"]["type"],
            ["string", "null"],
        )
        deny_rule = self.audit_event_schema["allOf"][0]
        self.assertEqual(deny_rule["if"]["properties"]["decision"]["const"], "deny")
        self.assertEqual(deny_rule["then"]["properties"]["delta_hash"]["type"], "null")
        self.assertEqual(deny_rule["else"]["properties"]["delta_hash"]["type"], "string")


if __name__ == "__main__":
    unittest.main()
