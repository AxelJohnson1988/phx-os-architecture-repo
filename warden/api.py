"""Dependency-free HTTP reference for the Phoenix API boundary.

The HTTP layer can submit/read requests and validate external receipts, but it
has no canonical-state writer. Authorization/commit remains a WardenKernel
operation behind the boundary.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from urllib.parse import urlparse

from .kernel import WardenKernel, WardenRequest

_SHA256 = re.compile(r"^[a-f0-9]{64}$")


def validate_receipt_shape(raw: dict) -> tuple[bool, str]:
    """Validate the minimum receipt envelope without accepting it as truth."""
    required = {
        "event_id", "request_id", "decision", "recorded_at",
        "before_state_hash", "after_state_hash", "event_hash",
    }
    missing = sorted(required - raw.keys())
    if missing:
        return False, "missing-fields:" + ",".join(missing)
    if raw["decision"] not in {"ACCEPTED", "REJECTED"}:
        return False, "invalid-decision"
    for field in ("before_state_hash", "after_state_hash", "event_hash"):
        if not isinstance(raw[field], str) or not _SHA256.fullmatch(raw[field]):
            return False, f"invalid-{field}"
    return True, "shape-valid"


class WardenAPIHandler(BaseHTTPRequestHandler):
    kernel: WardenKernel

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length))

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        if path == "/v1/warden/requests":
            try:
                raw = self._body()
                request = WardenRequest(
                    request_id=raw["request_id"],
                    idempotency_key=raw["idempotency_key"],
                    principal=raw["principal"],
                    action=raw["action"],
                    target=raw["target"],
                    proposed_change=raw["proposed_change"],
                    created_at=raw["created_at"],
                )
                request_id = self.kernel.submit(request)
            except (KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
                self._json(400, {"error": "invalid-request", "detail": str(exc)})
                return
            self._json(202, {"request_id": request_id, "state": "PENDING"})
            return

        if path == "/v1/warden/receipts":
            try:
                raw = self._body()
                valid, reason = validate_receipt_shape(raw)
            except (TypeError, json.JSONDecodeError, ValueError) as exc:
                self._json(400, {"error": "invalid-receipt", "detail": str(exc)})
                return
            if not valid:
                self._json(422, {"error": "receipt-rejected", "reason": reason})
                return
            # Validation here is only an intake check. It does not authorize or
            # mutate canonical state; Warden policy must perform that decision.
            self._json(202, {"state": "PENDING_VALIDATION", "validation": reason})
            return

        self._json(404, {"error": "not-found"})

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/v1/warden/state":
            self._json(200, {"state": dict(self.kernel.snapshot())})
            return

        prefix = "/v1/warden/requests/"
        if path.startswith(prefix):
            request_id = path[len(prefix):]
            try:
                request = self.kernel.get_request(request_id)
            except KeyError:
                self._json(404, {"error": "request-not-found"})
                return
            receipt = self.kernel.get_receipt(request_id)
            payload = {"request_id": request.request_id, "status": "COMMITTED" if receipt else "PENDING"}
            if receipt:
                payload["receipt"] = receipt.__dict__
            self._json(200, payload)
            return

        self._json(404, {"error": "not-found"})


def serve(kernel: WardenKernel, host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    """Start the reference API. Bind locally by default; harden before public deployment."""
    handler = type("BoundWardenAPIHandler", (WardenAPIHandler,), {"kernel": kernel})
    return ThreadingHTTPServer((host, port), handler)
