# Colab MCP Remote Compute Adapter: Phase 1 Isolated Capability Spec

## Purpose

This document defines a Phase 1 isolated test capability for using Google Colab through Colab MCP without expanding the trust boundary of the Phoenix/Warden system.

## Trust Boundary

Colab MCP is defined as an **external capability adapter**. It is not part of the Warden/Kernel trust base.

The local Warden/Kernel remains the only authority allowed to:

- authorize a remote compute job
- define the approved payload contract
- validate returned receipts and artifact hashes
- accept or reject results for downstream use

Google Colab is treated as disposable remote compute. Returned artifacts are untrusted until the local Warden validates the receipt and artifact manifest.

## Role Model

### 1. Authority: Local Warden / Kernel Host

The governing authority that issues the job authorization, fixes the allowed payload, validates the receipt, and records the acceptance or rejection decision.

### 2. Brain: Inference System / Decision Agent

A proposing component that may request remote execution, but cannot bypass Warden authorization or directly trust remote output.

### 3. Interface: Colab MCP Adapter

A tool-facing adapter that exposes Colab runtime creation and execution as a bounded capability. It forwards approved work to Colab and returns runtime outputs plus execution metadata.

### 4. Worker: Google Colab Runtime

A disposable execution environment that performs the approved workload and emits outputs and runtime facts. It has no authority to self-attest trustworthiness beyond what the local Warden can verify.

### 5. Ledger: Evidence Log

The append-only local record of job authorization, receipt capture, validation result, and artifact manifest. The ledger is the authoritative record of what occurred.

## Allowed Phase 1 Data Flow

1. The local Warden authorizes a single approved job.
2. The Colab MCP adapter provisions a disposable Colab runtime.
3. The runtime executes the approved payload.
4. The runtime returns execution outputs and a receipt payload.
5. The local host computes or verifies artifact hashes.
6. The local Warden validates the receipt and records the outcome in the evidence ledger.
7. Artifacts are retained as opaque outputs only after the receipt and manifest pass validation.

## Phase 1 Scope Constraints

Phase 1 is intentionally narrow:

- one authorized job at a time
- one receipt per execution attempt
- no scheduler or queueing semantics
- no privileged coupling into Phoenix runtime internals
- no trust elevation for Colab MCP or Colab itself
- no downstream use of outputs before local receipt validation

## Phase 1 Workloads

### Workload A: Hardware Attestation Probe

The first workload exists only to verify the remote compute path.

Required properties:

- deterministic and harmless
- starts a disposable Colab session
- queries runtime characteristics such as GPU presence and GPU type
- returns runtime facts suitable for receipt capture

Example runtime facts:

- accelerator available: true/false
- accelerator type string
- CUDA availability check result
- tool output derived from `nvidia-smi` or equivalent runtime inspection

This workload must not invoke broader Phoenix behaviors.

### Workload B: Lightweight Artifact Generation

The second workload exists only to prove artifact return and provenance capture.

Required properties:

- lightweight and reproducible
- writes outputs to an approved target directory
- produces a small artifact manifest suitable for local hash validation
- does not optimize for model quality or long-running training

Examples include a tiny tensor artifact, a deterministic data transformation, or a small `.pt`/`.safetensors` output.

## Governance Rules

- The Warden trusts validated receipts, not the remote runtime.
- Execution outputs and governance evidence must remain separate concerns.
- Artifacts are opaque outputs.
- The receipt and local validation result are the authoritative governance record.
- Any validation failure results in rejection, even if useful artifacts were returned.

## Acceptance Criteria

Phase 1 succeeds only if all of the following are true:

1. Local connection to Colab MCP succeeds.
2. A disposable Colab runtime is created.
3. The hardware probe returns expected runtime evidence.
4. The approved artifact-generation workload writes outputs to the target directory.
5. The local host computes and/or verifies hashes for all declared artifacts.
6. A complete receipt matching the repository schema is persisted.
7. The local Warden records an explicit acceptance decision.

## Failure Handling

The following conditions must produce local rejection and a recorded failed receipt rather than partial success:

- adapter connection failure
- runtime creation failure
- no GPU available when GPU capability is required by the job contract
- missing artifact listed in the manifest
- artifact hash mismatch
- malformed or incomplete receipt
- unauthorized payload drift from the approved job contract
- missing local validation decision

## Integration Gate

No Phoenix integration should occur until the isolated loop is stable.

After Phase 1 validation, Colab MCP may be modeled as one selectable remote compute capability behind the Warden policy layer, using the same receipt contract and with no special trust exemption.
