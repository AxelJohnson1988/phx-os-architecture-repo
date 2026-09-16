"""Capability modules, catalog, routing, and audit logging for integration selection.

This module keeps integration connectors behind a common contract and treats routing
as a proposal that must pass Warden policy checks before execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Any, Callable, Mapping, Protocol
import uuid

from .kernel import WardenRequest


_WORD = re.compile(r"[a-zA-Z0-9_]+")


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CostLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlanTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class RouteStatus(str, Enum):
    MATCHED = "matched"
    NO_SAFE_MATCH = "no-safe-match"
    POLICY_DENIED = "policy-denied"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _normalize(value: str) -> str:
    return " ".join(_WORD.findall(value.lower()))


def _tokenize(value: str) -> tuple[str, ...]:
    return tuple(_WORD.findall(value.lower()))


def _tier_rank(plan_tier: PlanTier) -> int:
    ranks = {
        PlanTier.FREE: 0,
        PlanTier.PRO: 1,
        PlanTier.ENTERPRISE: 2,
    }
    return ranks[plan_tier]


def _risk_rank(risk_level: RiskLevel) -> int:
    ranks = {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
    }
    return ranks[risk_level]


@dataclass(frozen=True)
class CapabilityModuleContract:
    module_id: str
    display_name: str
    domains: tuple[str, ...]
    actions: tuple[str, ...]
    required_permissions: tuple[str, ...]
    auth_requirements: tuple[str, ...]
    risk_level: RiskLevel
    cost_level: CostLevel
    expected_latency_ms: int
    compliance_sensitivity: tuple[str, ...]
    audit_fields: tuple[str, ...]
    aliases: tuple[str, ...]
    minimum_tier: PlanTier = PlanTier.FREE


class CapabilityModule(Protocol):
    @property
    def contract(self) -> CapabilityModuleContract:
        ...

    def execute(self, prompt: str, context: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class StaticCapabilityModule:
    """Simple module adapter used for routing and policy validation."""

    contract: CapabilityModuleContract

    def execute(self, prompt: str, context: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "module_id": self.contract.module_id,
            "status": "simulated",
            "summary": f"Module '{self.contract.display_name}' selected for prompt routing.",
            "prompt": prompt,
            "context": dict(context),
        }


@dataclass(frozen=True)
class PlanEntitlement:
    tier: PlanTier
    max_risk: RiskLevel
    max_monthly_calls: int
    audit_export: bool


@dataclass(frozen=True)
class RouteDecision:
    status: RouteStatus
    prompt: str
    plan_tier: PlanTier
    selected_module_id: str | None
    fallback_module_id: str | None
    confidence: float
    intent: str
    entities: tuple[str, ...]
    policy_allowed: bool
    policy_reason: str
    rationale: tuple[str, ...]
    execution_state: str


@dataclass(frozen=True)
class CapabilityAuditRecord:
    record_id: str
    recorded_at: str
    status: RouteStatus
    prompt: str
    plan_tier: PlanTier
    selected_module_id: str | None
    fallback_module_id: str | None
    confidence: float
    policy_allowed: bool
    policy_reason: str
    rationale: tuple[str, ...]
    execution_state: str
    principal: Mapping[str, str]
    data_scope: str
    previous_hash: str | None
    record_hash: str


class EvidenceLedger:
    """Append-only, hash-chained audit ledger for capability routing decisions."""

    def __init__(self) -> None:
        self._records: list[CapabilityAuditRecord] = []

    def append(
        self,
        *,
        status: RouteStatus,
        prompt: str,
        plan_tier: PlanTier,
        selected_module_id: str | None,
        fallback_module_id: str | None,
        confidence: float,
        policy_allowed: bool,
        policy_reason: str,
        rationale: tuple[str, ...],
        execution_state: str,
        principal: Mapping[str, str],
        data_scope: str,
    ) -> CapabilityAuditRecord:
        record_id = "audit_" + uuid.uuid4().hex
        previous_hash = self._records[-1].record_hash if self._records else None
        payload = {
            "record_id": record_id,
            "recorded_at": _now(),
            "status": status.value,
            "prompt": prompt,
            "plan_tier": plan_tier.value,
            "selected_module_id": selected_module_id,
            "fallback_module_id": fallback_module_id,
            "confidence": confidence,
            "policy_allowed": policy_allowed,
            "policy_reason": policy_reason,
            "rationale": list(rationale),
            "execution_state": execution_state,
            "principal": dict(principal),
            "data_scope": data_scope,
            "previous_hash": previous_hash,
        }
        record_hash = _hash(payload)
        record = CapabilityAuditRecord(
            record_id=payload["record_id"],
            recorded_at=payload["recorded_at"],
            status=status,
            prompt=prompt,
            plan_tier=plan_tier,
            selected_module_id=selected_module_id,
            fallback_module_id=fallback_module_id,
            confidence=confidence,
            policy_allowed=policy_allowed,
            policy_reason=policy_reason,
            rationale=rationale,
            execution_state=execution_state,
            principal=dict(principal),
            data_scope=data_scope,
            previous_hash=previous_hash,
            record_hash=record_hash,
        )
        self._records.append(record)
        return record

    def records(self) -> tuple[CapabilityAuditRecord, ...]:
        return tuple(self._records)


class TieredEntitlementPolicy:
    def __init__(self) -> None:
        self._entitlements = {
            PlanTier.FREE: PlanEntitlement(PlanTier.FREE, RiskLevel.LOW, 1000, False),
            PlanTier.PRO: PlanEntitlement(PlanTier.PRO, RiskLevel.MEDIUM, 15000, False),
            PlanTier.ENTERPRISE: PlanEntitlement(PlanTier.ENTERPRISE, RiskLevel.HIGH, 1_000_000, True),
        }

    def entitlement(self, plan_tier: PlanTier) -> PlanEntitlement:
        return self._entitlements[plan_tier]

    def allows(self, contract: CapabilityModuleContract, plan_tier: PlanTier) -> tuple[bool, str]:
        ent = self.entitlement(plan_tier)
        if _tier_rank(plan_tier) < _tier_rank(contract.minimum_tier):
            return False, "tier-below-module-minimum"
        if _risk_rank(contract.risk_level) > _risk_rank(ent.max_risk):
            return False, "tier-risk-limit-exceeded"
        return True, "tier-allowed"


class CapabilityCatalog:
    def __init__(self) -> None:
        self._modules: dict[str, CapabilityModule] = {}
        self._alias_to_ids: dict[str, set[str]] = {}

    def register(self, module: CapabilityModule) -> None:
        module_id = module.contract.module_id
        if module_id in self._modules:
            raise ValueError(f"module-already-registered:{module_id}")
        self._modules[module_id] = module

        aliases = set(module.contract.aliases)
        aliases.add(module.contract.display_name)
        aliases.add(module_id)
        for alias in aliases:
            norm = _normalize(alias)
            if norm:
                self._alias_to_ids.setdefault(norm, set()).add(module_id)

    def modules(self) -> tuple[CapabilityModule, ...]:
        return tuple(self._modules.values())

    def get(self, module_id: str) -> CapabilityModule:
        return self._modules[module_id]

    def alias_matches(self, prompt: str) -> set[str]:
        normalized_prompt = _normalize(prompt)
        matched: set[str] = set()
        for alias, module_ids in self._alias_to_ids.items():
            if alias and alias in normalized_prompt:
                matched.update(module_ids)
        return matched


PolicyCheck = Callable[[WardenRequest], tuple[bool, str]]


class CapabilityRouter:
    """Routes a prompt to the best module candidate with policy and tier gating."""

    def __init__(
        self,
        catalog: CapabilityCatalog,
        *,
        policy_check: PolicyCheck,
        entitlement_policy: TieredEntitlementPolicy | None = None,
        evidence_ledger: EvidenceLedger | None = None,
    ) -> None:
        self._catalog = catalog
        self._policy_check = policy_check
        self._entitlements = entitlement_policy or TieredEntitlementPolicy()
        self._ledger = evidence_ledger or EvidenceLedger()

    @property
    def ledger(self) -> EvidenceLedger:
        return self._ledger

    def route(
        self,
        *,
        prompt: str,
        principal: Mapping[str, str],
        plan_tier: PlanTier,
        data_scope: str = "general",
        context: Mapping[str, Any] | None = None,
        confirm_high_risk: bool = False,
    ) -> RouteDecision:
        context = context or {}
        intent = self._infer_intent(prompt)
        entities = self._extract_entities(prompt)
        ranked = self._rank(prompt, intent=intent, plan_tier=plan_tier)

        if not ranked:
            decision = RouteDecision(
                status=RouteStatus.NO_SAFE_MATCH,
                prompt=prompt,
                plan_tier=plan_tier,
                selected_module_id=None,
                fallback_module_id=None,
                confidence=0.0,
                intent=intent,
                entities=entities,
                policy_allowed=False,
                policy_reason="no-eligible-module",
                rationale=("No module matched prompt intent and tier constraints.",),
                execution_state="not-run",
            )
            self._append_audit(decision, principal=principal, data_scope=data_scope)
            return decision

        primary_id, primary_score, primary_notes = ranked[0]
        fallback_id = ranked[1][0] if len(ranked) > 1 else None
        module = self._catalog.get(primary_id)

        policy_request = WardenRequest(
            request_id="req_route_" + uuid.uuid4().hex,
            idempotency_key="idem_route_" + uuid.uuid4().hex,
            principal=principal,
            action="capability.route",
            target=f"capability:{primary_id}",
            proposed_change={
                "prompt": prompt,
                "selected_module_id": primary_id,
                "fallback_module_id": fallback_id,
                "intent": intent,
                "risk_level": module.contract.risk_level.value,
                "data_scope": data_scope,
                "confirmed_high_risk": confirm_high_risk,
                "confidence": round(primary_score, 4),
            },
            created_at=_now(),
        )

        allowed, policy_reason = self._policy_check(policy_request)
        if not allowed:
            decision = RouteDecision(
                status=RouteStatus.POLICY_DENIED,
                prompt=prompt,
                plan_tier=plan_tier,
                selected_module_id=primary_id,
                fallback_module_id=fallback_id,
                confidence=round(primary_score, 4),
                intent=intent,
                entities=entities,
                policy_allowed=False,
                policy_reason=policy_reason,
                rationale=tuple(primary_notes),
                execution_state="not-run",
            )
            self._append_audit(decision, principal=principal, data_scope=data_scope)
            return decision

        execution_state = "completed"
        try:
            module.execute(prompt, context)
        except Exception:
            execution_state = "failed"

        decision = RouteDecision(
            status=RouteStatus.MATCHED,
            prompt=prompt,
            plan_tier=plan_tier,
            selected_module_id=primary_id,
            fallback_module_id=fallback_id,
            confidence=round(primary_score, 4),
            intent=intent,
            entities=entities,
            policy_allowed=True,
            policy_reason=policy_reason,
            rationale=tuple(primary_notes),
            execution_state=execution_state,
        )
        self._append_audit(decision, principal=principal, data_scope=data_scope)
        return decision

    def _append_audit(self, decision: RouteDecision, *, principal: Mapping[str, str], data_scope: str) -> CapabilityAuditRecord:
        return self._ledger.append(
            status=decision.status,
            prompt=decision.prompt,
            plan_tier=decision.plan_tier,
            selected_module_id=decision.selected_module_id,
            fallback_module_id=decision.fallback_module_id,
            confidence=decision.confidence,
            policy_allowed=decision.policy_allowed,
            policy_reason=decision.policy_reason,
            rationale=decision.rationale,
            execution_state=decision.execution_state,
            principal=principal,
            data_scope=data_scope,
        )

    def _rank(self, prompt: str, *, intent: str, plan_tier: PlanTier) -> list[tuple[str, float, list[str]]]:
        prompt_tokens = set(_tokenize(prompt))
        alias_matched = self._catalog.alias_matches(prompt)
        ranked: list[tuple[str, float, list[str]]] = []

        for module in self._catalog.modules():
            allowed, tier_reason = self._entitlements.allows(module.contract, plan_tier)
            if not allowed:
                continue

            score = 0.0
            notes: list[str] = [f"Tier check: {tier_reason}."]

            module_id = module.contract.module_id
            if module_id in alias_matched:
                score += 0.55
                notes.append("Prompt matched module alias or name.")

            domain_hits = prompt_tokens.intersection({token for d in module.contract.domains for token in _tokenize(d)})
            if domain_hits:
                score += min(0.25, 0.08 * len(domain_hits))
                notes.append(f"Domain overlap: {', '.join(sorted(domain_hits))}.")

            action_hits = prompt_tokens.intersection({token for a in module.contract.actions for token in _tokenize(a)})
            if action_hits:
                score += min(0.2, 0.1 * len(action_hits))
                notes.append(f"Action overlap: {', '.join(sorted(action_hits))}.")

            if intent and intent in module.contract.actions:
                score += 0.15
                notes.append(f"Inferred intent '{intent}' matches module action.")

            if score > 0.3:
                ranked.append((module_id, min(score, 1.0), notes))

        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked

    @staticmethod
    def _infer_intent(prompt: str) -> str:
        tokens = set(_tokenize(prompt))
        intent_map = {
            "search": {"search", "find", "lookup", "query"},
            "analyze": {"analyze", "analysis", "audit", "review"},
            "manage": {"manage", "update", "track", "monitor"},
            "deploy": {"deploy", "ship", "release", "publish"},
            "automate": {"automate", "trigger", "run", "orchestrate"},
        }
        for intent, words in intent_map.items():
            if tokens.intersection(words):
                return intent
        return "general"

    @staticmethod
    def _extract_entities(prompt: str) -> tuple[str, ...]:
        tokens = _tokenize(prompt)
        entities = [tok for tok in tokens if len(tok) > 4]
        unique_entities = list(dict.fromkeys(entities))
        return tuple(unique_entities[:8])


def build_default_catalog() -> CapabilityCatalog:
    """Create a staged catalog with representative integrations for rollout."""
    catalog = CapabilityCatalog()

    modules = (
        StaticCapabilityModule(
            CapabilityModuleContract(
                module_id="mdn_docs",
                display_name="MDN",
                domains=("developer", "web", "documentation"),
                actions=("search", "analyze"),
                required_permissions=("docs.read",),
                auth_requirements=("api_key",),
                risk_level=RiskLevel.LOW,
                cost_level=CostLevel.LOW,
                expected_latency_ms=700,
                compliance_sensitivity=("none",),
                audit_fields=("prompt", "decision", "module_id", "confidence"),
                aliases=("mdn", "mozilla docs", "browser compatibility"),
                minimum_tier=PlanTier.FREE,
            )
        ),
        StaticCapabilityModule(
            CapabilityModuleContract(
                module_id="process_street",
                display_name="Process Street",
                domains=("operations", "workflow", "compliance"),
                actions=("manage", "automate", "search"),
                required_permissions=("workflow.read", "workflow.write"),
                auth_requirements=("oauth",),
                risk_level=RiskLevel.MEDIUM,
                cost_level=CostLevel.MEDIUM,
                expected_latency_ms=1100,
                compliance_sensitivity=("business",),
                audit_fields=("prompt", "decision", "policy", "execution_state", "receipt"),
                aliases=("process street", "sop", "checklist"),
                minimum_tier=PlanTier.PRO,
            )
        ),
        StaticCapabilityModule(
            CapabilityModuleContract(
                module_id="devrev",
                display_name="DevRev",
                domains=("crm", "knowledge", "support"),
                actions=("search", "manage", "analyze"),
                required_permissions=("crm.read", "crm.write"),
                auth_requirements=("oauth", "scoped_token"),
                risk_level=RiskLevel.MEDIUM,
                cost_level=CostLevel.MEDIUM,
                expected_latency_ms=1200,
                compliance_sensitivity=("customer_data",),
                audit_fields=("prompt", "decision", "module_id", "principal", "execution_state"),
                aliases=("devrev", "knowledge graph", "tickets"),
                minimum_tier=PlanTier.PRO,
            )
        ),
        StaticCapabilityModule(
            CapabilityModuleContract(
                module_id="atlar_treasury",
                display_name="Atlar",
                domains=("finance", "treasury", "payments"),
                actions=("analyze", "manage", "search"),
                required_permissions=("treasury.read", "treasury.approve"),
                auth_requirements=("oauth", "mfa"),
                risk_level=RiskLevel.HIGH,
                cost_level=CostLevel.HIGH,
                expected_latency_ms=1700,
                compliance_sensitivity=("regulated", "financial"),
                audit_fields=("prompt", "decision", "policy", "receipt", "artifact_hash"),
                aliases=("atlar", "treasury", "cash management"),
                minimum_tier=PlanTier.ENTERPRISE,
            )
        ),
        StaticCapabilityModule(
            CapabilityModuleContract(
                module_id="harness",
                display_name="Harness",
                domains=("developer", "infrastructure", "deployment", "security"),
                actions=("deploy", "monitor", "manage"),
                required_permissions=("pipeline.read", "pipeline.execute"),
                auth_requirements=("oauth",),
                risk_level=RiskLevel.HIGH,
                cost_level=CostLevel.HIGH,
                expected_latency_ms=1400,
                compliance_sensitivity=("security",),
                audit_fields=("prompt", "decision", "policy", "execution_state", "receipt"),
                aliases=("harness", "ci cd", "pipeline"),
                minimum_tier=PlanTier.ENTERPRISE,
            )
        ),
    )

    for module in modules:
        catalog.register(module)
    return catalog


def capability_route_policy(request: WardenRequest) -> tuple[bool, str]:
    """Reference policy for routing proposals with high-risk confirmation guard."""
    if request.action != "capability.route":
        return False, "unsupported-action"
    if not request.target.startswith("capability:"):
        return False, "target-outside-capability-namespace"

    risk = str(request.proposed_change.get("risk_level", "")).lower()
    confirmed = bool(request.proposed_change.get("confirmed_high_risk"))
    if risk == RiskLevel.HIGH.value and not confirmed:
        return False, "confirmation-required"
    return True, "authorized"
