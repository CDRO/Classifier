# Next 10 Milestones for Source and Destination Expansion

**Version:** 1.0  
**Date:** 2026-08-25  
**Status:** Proposed roadmap for the next implementation cycle

---

## Goal

Move the project from a provider-specific implementation toward a backend-neutral intake and routing platform. The classifier must continue to own document review and classification logic, while the storage layer becomes interchangeable and easy to extend.

---

## Milestone 1 — Multi-source root configuration

**Problem:** The current pipeline assumes a single source root and a local folder layout.  
**Change:** Add configuration for multiple source roots and an explicit source label per folder.  
**Acceptance criteria:**
- backend config exposes source roots as a list
- each source can be named and validated
- review UI shows which source the document came from
- no behavior change for the default local path

**Suggested tests:**
- config loads list of source roots
- empty or invalid source roots are rejected
- default local source remains active when no overrides are supplied

---

## Milestone 2 — Multi-destination routing configuration

**Problem:** Destinees are treated as a single local output group.  
**Change:** Allow separate configurable destinations and route metadata for each route.  
**Acceptance criteria:**
- destination config supports multiple active targets
- each route has a visible label and path
- route metadata is persisted with classification actions
- UI remains compatible with the current single-root default

**Suggested tests:**
- multiple destination definitions are saved and restored
- invalid route names or paths are rejected
- finalization writes to the correct active destination

---

## Milestone 3 — Local NAS and SMB source adapter

**Problem:** Production environments often rely on network shares rather than a single mounted local folder.  
**Change:** Add source adapters for local NAS and SMB/Network share directories.  
**Acceptance criteria:**
- adapter validates path permissions and accessibility
- file listing works for mounted or UNC based shares
- metadata includes source type, root path, and provider
- failures are explicit and logged without leaking credentials

**Suggested tests:**
- valid local share is accepted
- invalid or unreachable share is rejected cleanly
- file listing returns PDFs only

---

## Milestone 4 — Destinee-aware export planner

**Problem:** Finalization logic currently writes directly to a configured folder without a route planner.  
**Change:** Introduce a route planner that resolves the final output target from the document, route config, and destination backend.  
**Acceptance criteria:**
- each export chooses a valid destination target
- planner handles missing or invalid route names safely
- export logs contain clear route reasons
- manual overrides still work in the review flow

**Suggested tests:**
- route planner resolves valid destinee
- invalid destinee raises clear error
- manual override takes priority

---

## Milestone 5 — Source/destination backend registry and config schema

**Problem:** Backends exist but are not yet described as a formal source/destination registry.  
**Change:** Add backend registry entries for source and destination categories with validation and schema metadata.  
**Acceptance criteria:**
- each backend declares type: source or destination
- registry enforces unique backend names
- config schema exposes required env vars and defaults
- unsupported backends fail fast with clear message

**Suggested tests:**
- registry rejects duplicates
- registry includes known local and Google backends
- unknown backend raises a validation error

---

## Milestone 6 — Storage health checks and validation UI

**Problem:** Backends are assumed valid until runtime failure.  
**Change:** Add connectivity and permission checks to the backend lifecycle and show health in the config UI.  
**Acceptance criteria:**
- backend health endpoint reports status per configured source/destination
- UI shows ok / warning / error states
- validation runs before the app finalizes a route
- errors are surfaced without returning secret material

**Suggested tests:**
- healthy backend reports success
- invalid path or permissions report clear failure
- validation output does not include secrets

---

## Milestone 7 — Archive policy enforcement for source and destination backends

**Problem:** Archive behavior is modeled around local files only.  
**Change:** Extend archive policy to cover source and destination records for each backend.  
**Acceptance criteria:**
- processed documents are archived according to the active backend rules
- source cleanup deletes only matching documents for the current source
- destination cleanup remains consistent with private retention rules
- archive metadata records the provider and original path

**Suggested tests:**
- archive path is recorded for a routed document
- cleanup deletes matching remote and local copies safely
- retention state remains consistent after restart

---

## Milestone 8 — Email inbox ingestion adapter

**Problem:** The system currently assumes a file system handoff rather than message-driven intake.  
**Change:** Add a monitored email inbox adapter for PDF attachments or submitted files.  
**Acceptance criteria:**
- adapter lists or polls configured mailboxes
- attachments are normalized into the internal document model
- source metadata includes mailbox, sender, and message id
- invalid attachments are skipped with a clear record

**Suggested tests:**
- valid PDF attachment is accepted
- non-PDF attachment is skipped
- metadata normalization is stable

---

## Milestone 9 — Microsoft 365 / SharePoint adapter

**Problem:** Many real deployments live in Microsoft-centric environments.  
**Change:** Add a SharePoint or OneDrive adapter behind the same storage contract.  
**Acceptance criteria:**
- backend authenticates with the configured Microsoft identity or app registration
- files can be listed and uploaded to a target library/folder
- metadata is normalized to the internal route model
- auth failures are explicit and non-leaky

**Suggested tests:**
- invalid credentials fail fast
- valid folder listing returns PDFs only
- destination routing works to a SharePoint folder

---

## Milestone 10 — Webhook/API ingestion and outbound routing

**Problem:** Some business flows do not use a human or folder handoff.  
**Change:** Add API-driven document intake and route dispatch as a first-class source/destination option.  
**Acceptance criteria:**
- inbound API accepts multipart or JSON metadata with file payloads
- documents are classified and routed without filesystem assumptions
- output route can target a backend or folder based on classification result
- API validator rejects malformed payloads with explicit status/errors

**Suggested tests:**
- valid API upload succeeds
- malformed payload returns 400 with clear error
- route dispatch uses destination backend configuration

---

## Suggested execution order

The practical order is:

1. Milestone 1 and 2 first (configuration layer)
2. Milestone 3 next (source support for real deployments)
3. Milestone 4 and 5 next (planner and registry)
4. Milestone 6 and 7 after validation (health and archive)
5. Milestone 8, 9, and 10 as optional provider expansions

This preserves the product value while keeping the architecture stable.

---

## Why this roadmap is better than more Google work

The current Google work is valuable, but it is still a provider-specific optimization. The real product leverage comes from making the classifier independent of the source and destination. Once the source/destination boundary is clean, Google Drive, NAS, SharePoint, email, and API-based intake become straightforward additions instead of custom rewrites.
