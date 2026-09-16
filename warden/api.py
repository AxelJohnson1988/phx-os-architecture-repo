"""Dependency-free HTTP reference for the Phoenix API boundary.

The HTTP layer can submit/read requests, but it has no canonical-state writer.
Authorization/commit remains a WardenKernel operation behind the boundary.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import urlparse

from .kernel import WardenKernel, WardenRequest


class WardenAPIHandler(BaseHTTPRequestHandler):
    kernel: WardenKernel

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/v1/warden/requests":
            self._json(404, {"error": "not-found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        try:
            raw = json.loads(self.rfile.read(length))
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
    """Start the reference API. Bind locally by default; put a hardened gateway in front in production."""
    handler = type("BoundWardenAPIHandler", (WardenAPIHandler,), {"kernel": kernel})
    server = ThreadingHTTPServer((host, port), handler)
    return server
