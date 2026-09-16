# Phoenix Constitution

## Purpose

Define the Phoenix trust boundaries and the authoritative dependencies between Warden, provenance, inference gateways, models, external capabilities, and presentation clients.

## Constitutional Invariant

> **Models may propose. Interfaces may request. Only Warden may authorize and commit canonical Phoenix state. Reality changes only through an authorized, receipted transition.**

No presentation layer, model, agent, gateway, external service, or transport adapter may directly mutate canonical Phoenix state.

All canonical state mutation MUST pass through Warden.

## Trust Domains

| Layer | Role | Canonical state mutation |
|---|---|---:|
| Vercel / Phoenix Cockpit | Presentation, visualization, interaction | No |
| Phoenix API Boundary | Authentication, validation, transport, anti-replay | No |
| LLMs / Agents | Reasoning and proposals | No |
| LiteLLM | Model gateway, routing, fallback, logging | No |
| vLLM / Ollama | Model inference | No |
| External capabilities | Delegated execution | No |
| Warden / Kernel | Identity, policy, authorization, state transitions | **Yes** |
| GPAM / Provenance | Append-only evidence and receipts | Append-only |

## Vercel Boundary

Vercel is an untrusted presentation/client layer. It may display state, collect user intent, submit authenticated requests, and visualize receipts. It MUST NOT be treated as Phoenix authority or system of record.

The Phoenix API Boundary is a security and transport boundary, not a constitutional authority. Authentication establishes who presented a request; Warden determines whether that principal is authorized to perform a particular transition under current policy.

Warden internals MUST NOT be exposed directly to the public web surface.

## Request Lifecycle

```text
Observe
  -> Interpret
  -> Propose
  -> Request
  -> Authenticate
  -> Validate
  -> Warden Authorization
  -> State Transition
  -> Receipt
  -> Provenance Record
```

A rejected proposal or request MUST NOT mutate canonical state.

## Warden Rules

1. Warden is the sole authority for canonical Phoenix state transitions.
2. A model output is a proposal, never an authorization.
3. A valid API credential is not sufficient authorization for a state transition.
4. External execution results are untrusted until locally validated.
5. Every accepted transition MUST produce a verifiable receipt.
6. Failed validation MUST produce rejection rather than partial acceptance.
7. Request identifiers and idempotency keys MUST prevent accidental duplicate commits.
8. Unknown fields in constitutional request/receipt contracts MUST fail closed where strict schema validation is enabled.

## Provenance

A receipt proves that Warden recorded a transition with a particular payload at a particular time. Cryptographic integrity and timestamping do not, by themselves, establish that an external claim is true.

The provenance layer therefore records facts such as request identity, decision, state hashes, artifact hashes, and validation results without granting those records authority over policy.

## API Boundary

The minimum external API is:

- `POST /v1/warden/requests` — submit a proposal/request; no state mutation is implied.
- `GET /v1/warden/requests/{request_id}` — retrieve request status.
- `POST /v1/warden/receipts` — submit an execution receipt for Warden validation.
- `GET /v1/warden/state` — read a sanitized canonical state snapshot.

Only Warden-owned code may invoke the commit operation. The API layer may never write canonical state directly.

## Non-Goals

- Making Vercel a system of record
- Making LiteLLM a policy engine
- Making vLLM or Ollama an identity or truth authority
- Allowing agents to self-authorize actions
- Treating remote execution as trusted merely because it returned a result
