from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from warden.capabilities import (
    CapabilityRouter,
    PlanTier,
    RouteStatus,
    build_default_catalog,
    capability_route_policy,
)
from warden.kernel import WardenKernel, WardenRequest


def combined_policy(request: WardenRequest) -> tuple[bool, str]:
    if request.action == "capability.route":
        return capability_route_policy(request)
    return WardenKernel._default_policy(request)


class CapabilityRouterTests(unittest.TestCase):
    def test_default_catalog_modules_share_contract_shape(self):
        catalog = build_default_catalog()
        self.assertGreaterEqual(len(catalog.modules()), 5)
        for module in catalog.modules():
            contract = module.contract
            self.assertTrue(contract.module_id)
            self.assertTrue(contract.display_name)
            self.assertTrue(contract.domains)
            self.assertTrue(contract.actions)
            self.assertTrue(contract.required_permissions)
            self.assertTrue(contract.auth_requirements)
            self.assertTrue(contract.audit_fields)

    def test_router_selects_low_risk_module_for_free_tier(self):
        catalog = build_default_catalog()
        kernel = WardenKernel(policy=combined_policy)
        router = CapabilityRouter(catalog, policy_check=kernel.authorize_proposal)

        decision = router.route(
            prompt="Search MDN browser compatibility for fetch API",
            principal={"subject": "human:test", "source": "human"},
            plan_tier=PlanTier.FREE,
        )

        self.assertEqual(decision.status, RouteStatus.MATCHED)
        self.assertEqual(decision.selected_module_id, "mdn_docs")
        self.assertTrue(decision.policy_allowed)
        self.assertEqual(dict(kernel.snapshot()), {})

    def test_router_returns_no_safe_match_when_tier_disallows_modules(self):
        catalog = build_default_catalog()
        kernel = WardenKernel(policy=combined_policy)
        router = CapabilityRouter(catalog, policy_check=kernel.authorize_proposal)

        decision = router.route(
            prompt="Analyze treasury cash balances and payment exposure",
            principal={"subject": "human:test", "source": "human"},
            plan_tier=PlanTier.FREE,
        )

        self.assertEqual(decision.status, RouteStatus.NO_SAFE_MATCH)
        self.assertIsNone(decision.selected_module_id)
        self.assertFalse(decision.policy_allowed)

    def test_high_risk_routes_require_confirmation(self):
        catalog = build_default_catalog()
        kernel = WardenKernel(policy=combined_policy)
        router = CapabilityRouter(catalog, policy_check=kernel.authorize_proposal)

        denied = router.route(
            prompt="Deploy production pipeline with Harness",
            principal={"subject": "human:test", "source": "human"},
            plan_tier=PlanTier.ENTERPRISE,
            confirm_high_risk=False,
        )
        allowed = router.route(
            prompt="Deploy production pipeline with Harness",
            principal={"subject": "human:test", "source": "human"},
            plan_tier=PlanTier.ENTERPRISE,
            confirm_high_risk=True,
        )

        self.assertEqual(denied.status, RouteStatus.POLICY_DENIED)
        self.assertEqual(denied.policy_reason, "confirmation-required")
        self.assertEqual(allowed.status, RouteStatus.MATCHED)
        self.assertEqual(allowed.policy_reason, "authorized")

    def test_router_provides_fallback_for_multi_match_prompt(self):
        catalog = build_default_catalog()
        kernel = WardenKernel(policy=combined_policy)
        router = CapabilityRouter(catalog, policy_check=kernel.authorize_proposal)

        decision = router.route(
            prompt="Search and manage support tickets in DevRev knowledge graph",
            principal={"subject": "human:test", "source": "human"},
            plan_tier=PlanTier.PRO,
        )

        self.assertEqual(decision.status, RouteStatus.MATCHED)
        self.assertEqual(decision.selected_module_id, "devrev")
        self.assertIsNotNone(decision.fallback_module_id)

    def test_audit_ledger_is_hash_chained(self):
        catalog = build_default_catalog()
        kernel = WardenKernel(policy=combined_policy)
        router = CapabilityRouter(catalog, policy_check=kernel.authorize_proposal)

        router.route(
            prompt="Search MDN for CSS Grid docs",
            principal={"subject": "human:test", "source": "human"},
            plan_tier=PlanTier.FREE,
        )
        router.route(
            prompt="Search MDN for WebAuthn examples",
            principal={"subject": "human:test", "source": "human"},
            plan_tier=PlanTier.FREE,
        )

        records = router.ledger.records()
        self.assertEqual(len(records), 2)
        self.assertIsNone(records[0].previous_hash)
        self.assertEqual(records[1].previous_hash, records[0].record_hash)


if __name__ == "__main__":
    unittest.main()
