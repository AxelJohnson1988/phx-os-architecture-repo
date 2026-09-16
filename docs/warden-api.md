# Phoenix Warden API Boundary

This is the HTTP contract for the public-facing Phoenix cockpit. The API boundary is a transport/security adapter, not a state authority.

## Endpoints

### `POST /v1/warden/requests`

Submit a proposal/request. Expected response: `202 Accepted`.

The endpoint MUST NOT commit canonical state.

```json
{
  "request_id": "req_demo12345678",
  "idempotency_key": "idem-demo-001",
  "principal": {"subject": "human:demo", "source": "human"},
  "action": "state.set",
  "target": "state:system_status",
  "proposed_change": {"value": "online"},
  "created_at": "2026-09-16T20:20:31.482Z"
}
```

Response:

```json
{"request_id":"req_demo12345678","state":"PENDING"}
```

### `GET /v1/warden/requests/{request_id}`

Returns the request status and, once committed, its Warden receipt.

### `GET /v1/warden/state`

Returns a sanitized read-only canonical state snapshot.

### Receipt submission

Remote/external execution receipts may be accepted through a dedicated receipt-validation endpoint in the production implementation. Receipt validation MUST remain under Warden policy and MUST NOT be interpreted as automatic authorization to mutate canonical state.

## Production Requirements

The reference server binds to `127.0.0.1` and intentionally omits production authentication, TLS termination, durable storage, and distributed replay protection. Those belong in the deployment layer without changing the constitutional boundary.

For a public deployment, place a hardened gateway in front of Warden and require:

- TLS
- authenticated principals
- request-size limits
- strict JSON/schema validation
- idempotency/replay controls
- audit logging
- least-privilege service credentials
- network isolation from Warden internals

**Authentication is not authorization.** Only Warden policy may authorize a canonical state transition.
