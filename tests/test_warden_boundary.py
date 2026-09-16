import json
from dataclasses import asdict
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from warden.kernel import WardenKernel, WardenRequest


def request(request_id="req_test12345678", key="idem-test-001", value="online"):
    return WardenRequest(
        request_id=request_id,
        idempotency_key=key,
        principal={"subject": "human:test", "source": "human"},
        action="state.set",
        target="state:system_status",
        proposed_change={"value": value},
        created_at="2026-09-16T20:20:31.482Z",
    )


class WardenBoundaryTests(unittest.TestCase):
    def test_proposal_does_not_mutate_canonical_state(self):
        kernel = WardenKernel()
        kernel.submit(request())
        self.assertEqual(dict(kernel.snapshot()), {})

    def test_only_authorized_commit_changes_state(self):
        kernel = WardenKernel()
        req = request()
        kernel.submit(req)
        receipt = kernel.authorize_and_commit(req.request_id)
        self.assertEqual(receipt.decision, "ACCEPTED")
        self.assertEqual(dict(kernel.snapshot()), {"system_status": "online"})

    def test_rejected_request_cannot_mutate_state(self):
        def deny(_request):
            return False, "policy-denied"

        kernel = WardenKernel(policy=deny)
        req = request(value="must-not-appear")
        kernel.submit(req)
        receipt = kernel.authorize_and_commit(req.request_id)
        self.assertEqual(receipt.decision, "REJECTED")
        self.assertEqual(dict(kernel.snapshot()), {})

    def test_read_snapshot_cannot_be_used_to_mutate_warden(self):
        kernel = WardenKernel()
        view = kernel.snapshot()
        with self.assertRaises(TypeError):
            view["system_status"] = "tampered"
        self.assertEqual(dict(kernel.snapshot()), {})

    def test_idempotency_prevents_duplicate_proposals_and_commits(self):
        kernel = WardenKernel()
        first = request(request_id="req_first12345678", key="idem-same-001")
        second = request(request_id="req_second1234567", key="idem-same-001", value="different")
        self.assertEqual(kernel.submit(first), first.request_id)
        self.assertEqual(kernel.submit(second), first.request_id)
        receipt = kernel.authorize_and_commit(first.request_id)
        self.assertEqual(receipt.decision, "ACCEPTED")
        self.assertEqual(dict(kernel.snapshot()), {"system_status": "online"})

    def test_receipt_contains_verifiable_state_hashes(self):
        kernel = WardenKernel()
        req = request()
        kernel.submit(req)
        receipt = kernel.authorize_and_commit(req.request_id)
        self.assertEqual(len(receipt.before_state_hash), 64)
        self.assertEqual(len(receipt.after_state_hash), 64)
        self.assertEqual(len(receipt.event_hash), 64)
        self.assertTrue(receipt.event_id.startswith("evt_"))

    def test_api_module_has_no_canonical_state_store(self):
        api_source = Path(__file__).parents[1].joinpath("warden", "api.py").read_text()
        self.assertNotIn("self._state", api_source)
        self.assertNotIn("self._receipts", api_source)
        self.assertNotIn("self._requests", api_source)

    def test_request_shape_is_json_serializable(self):
        payload = asdict(request())
        encoded = json.dumps(payload)
        self.assertEqual(json.loads(encoded)["action"], "state.set")


if __name__ == "__main__":
    unittest.main()
