"""Small, dependency-free reference implementation of the Phoenix trust boundary.

This is intentionally not a production auth system. It demonstrates the invariant:
models/interfaces submit proposals; only Warden commits canonical state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from types import MappingProxyType
from typing import Any, Callable, Mapping
import uuid


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class WardenRequest:
    request_id: str
    idempotency_key: str
    principal: Mapping[str, str]
    action: str
    target: str
    proposed_change: Mapping[str, Any]
    created_at: str


@dataclass(frozen=True)
class WardenReceipt:
    event_id: str
    request_id: str
    decision: str
    recorded_at: str
    before_state_hash: str
    after_state_hash: str
    event_hash: str
    reason: str | None = None
    state_delta: Mapping[str, Any] | None = None


Policy = Callable[[WardenRequest], tuple[bool, str]]


class WardenKernel:
    """The sole owner of canonical state mutation."""

    def __init__(self, policy: Policy | None = None) -> None:
        self._state: dict[str, Any] = {}
        self._requests: dict[str, WardenRequest] = {}
        self._receipts: dict[str, WardenReceipt] = {}
        self._idempotency: dict[str, str] = {}
        self._policy = policy or self._default_policy

    @staticmethod
    def _default_policy(request: WardenRequest) -> tuple[bool, str]:
        if request.action != "state.set":
            return False, "action-not-permitted"
        if not request.target.startswith("state:"):
            return False, "target-outside-state-namespace"
        if "value" not in request.proposed_change:
            return False, "missing-proposed-value"
        return True, "authorized"

    def submit(self, request: WardenRequest) -> str:
        """Register a proposal. This method NEVER mutates canonical state."""
        if request.idempotency_key in self._idempotency:
            return self._idempotency[request.idempotency_key]
        if request.request_id in self._requests:
            raise ValueError("request-id-already-exists")
        self._requests[request.request_id] = request
        self._idempotency[request.idempotency_key] = request.request_id
        return request.request_id

    def authorize_proposal(self, request: WardenRequest) -> tuple[bool, str]:
        """Evaluate policy for a proposal without mutating canonical state."""
        return self._policy(request)

    def authorize_and_commit(self, request_id: str) -> WardenReceipt:
        """Authorize and commit one previously submitted proposal."""
        request = self._requests[request_id]
        existing = next((r for r in self._receipts.values() if r.request_id == request_id), None)
        if existing:
            return existing

        before = dict(self._state)
        allowed, reason = self._policy(request)
        if not allowed:
            return self._record_rejection(request, before, reason)

        key = request.target.removeprefix("state:")
        self._state[key] = request.proposed_change["value"]
        after = dict(self._state)
        return self._record_acceptance(request, before, after, key)

    def snapshot(self) -> Mapping[str, Any]:
        """Return a read-only view; callers cannot mutate Warden's state through it."""
        return MappingProxyType(dict(self._state))

    def get_request(self, request_id: str) -> WardenRequest:
        return self._requests[request_id]

    def get_receipt(self, request_id: str) -> WardenReceipt | None:
        return next((r for r in self._receipts.values() if r.request_id == request_id), None)

    def _record_rejection(self, request: WardenRequest, before: dict[str, Any], reason: str) -> WardenReceipt:
        event_id = "evt_" + uuid.uuid4().hex
        after_hash = _hash(before)
        body = {
            "event_id": event_id,
            "request_id": request.request_id,
            "decision": "REJECTED",
            "recorded_at": _now(),
            "before_state_hash": _hash(before),
            "after_state_hash": after_hash,
            "reason": reason,
        }
        receipt = WardenReceipt(**body, event_hash=_hash(body))
        self._receipts[event_id] = receipt
        return receipt

    def _record_acceptance(self, request: WardenRequest, before: dict[str, Any], after: dict[str, Any], key: str) -> WardenReceipt:
        event_id = "evt_" + uuid.uuid4().hex
        body = {
            "event_id": event_id,
            "request_id": request.request_id,
            "decision": "ACCEPTED",
            "recorded_at": _now(),
            "before_state_hash": _hash(before),
            "after_state_hash": _hash(after),
            "state_delta": {key: after[key]},
        }
        receipt = WardenReceipt(**body, event_hash=_hash(body))
        self._receipts[event_id] = receipt
        return receipt
