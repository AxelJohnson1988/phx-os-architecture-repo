# phx-os-architecture-repo

Model-driven architecture for the Phoenix/Warden/Akashic/MINDPRINT stack. Implements a 4D Sierpiński tetrahedral memory lattice for local-first, zero-trust AI sovereignty.

## Phoenix Constitutional Boundary

Phoenix treats the presentation layer as untrusted. **Models may propose. Interfaces may request. Only Warden may authorize and commit canonical Phoenix state. Reality changes only through an authorized, receipted transition.**

Core implementation and contracts:

- [`docs/PHOENIX_CONSTITUTION.md`](docs/PHOENIX_CONSTITUTION.md) — trust boundaries, constitutional invariants, and governance rules
- [`docs/warden-api.md`](docs/warden-api.md) — Warden API boundary and endpoint contract
- [`schemas/warden-request.schema.json`](schemas/warden-request.schema.json) — strict request/proposal contract
- [`schemas/warden-receipt.schema.json`](schemas/warden-receipt.schema.json) — Warden receipt contract
- [`warden/kernel.py`](warden/kernel.py) — dependency-free reference implementation of Warden-only state transitions
- [`warden/api.py`](warden/api.py) — dependency-free HTTP boundary reference
- [`tests/test_warden_boundary.py`](tests/test_warden_boundary.py) — tests enforcing no direct mutation outside Warden

### Trust flow

```text
Vercel / Cockpit
      │
      ▼
Phoenix API Boundary
      │
      ▼
Warden / Kernel ──────► GPAM / Provenance
      │
      ▼
LiteLLM
   ┌──┴──┐
   ▼     ▼
vLLM  Ollama
```

Vercel, the API adapter, LiteLLM, inference engines, agents, and external services are not canonical state authorities.

## Capability Modules and Prompt Router

The repository now includes a capability-module routing layer at [`warden/capabilities.py`](warden/capabilities.py):

- **Single module contract** for integrations (`CapabilityModuleContract`) with standardized input/output, auth, risk, cost, and audit metadata.
- **Capability catalog** (`CapabilityCatalog`) that registers each integration module with domains, actions, permissions, compliance sensitivity, and aliases.
- **Prompt router** (`CapabilityRouter`) that parses prompt intent, scores candidate modules, returns primary and fallback matches, and supports explicit `no-safe-match`.
- **Warden policy enforcement** by treating route decisions as proposals (`action=capability.route`) that must pass a policy check before execution.
- **Append-only evidence ledger** (`EvidenceLedger`) with hash-chained records for routing, policy outcomes, confidence, and execution state.
- **Tiered entitlements** (`PlanTier` + `TieredEntitlementPolicy`) for free/pro/enterprise access control, including enterprise-grade high-risk routing with confirmation.

### Minimal usage

```python
from warden.capabilities import CapabilityRouter, PlanTier, build_default_catalog
from warden.kernel import WardenKernel

catalog = build_default_catalog()
kernel = WardenKernel(policy=...)  # provide capability.route policy
router = CapabilityRouter(catalog, policy_check=kernel.authorize_proposal)

decision = router.route(
    prompt="Search MDN browser compatibility for fetch",
    principal={"subject": "human:alice", "source": "human"},
    plan_tier=PlanTier.FREE,
)
```

## Colab MCP Phase 1

This repository defines Colab MCP as an external remote compute adapter for isolated Phase 1 validation, not as part of the Warden/Kernel trust base.

Artifacts added for this capability:

- [`docs/colab-mcp-phase1.md`](docs/colab-mcp-phase1.md) — architecture boundary, role model, Phase 1 data flow, acceptance criteria, and failure rules
- [`schemas/colab-phase1-job.schema.json`](schemas/colab-phase1-job.schema.json) — narrow single-job authorization contract
- [`examples/colab-phase1-job.example.json`](examples/colab-phase1-job.example.json) — example single-job authorization payload
- [`schemas/colab-phase1-receipt.schema.json`](schemas/colab-phase1-receipt.schema.json) — append-only provenance receipt contract
- [`examples/colab-phase1-receipt.example.json`](examples/colab-phase1-receipt.example.json) — example validated receipt
