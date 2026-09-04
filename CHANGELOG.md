# Changelog

All notable changes to this project are documented here.

## Unreleased

## 4.0.0 - 2026-09-04

### Added
- Added source-aware notification subscriptions so users can subscribe globally or only for a selected source.
- Added browser notification fallback messaging and in-app status handling for unsupported or denied browsers.
- Added notification cleanup for expired or invalid subscription records.

### Changed
- Kept browser delivery opt-in and graceful in-app fallback behavior when background notifications are unavailable.
- Updated the notification status banner to reflect browser capability and permission state without blocking the review workflow.

### Fixed
- Fixed the notification subscription validation path so source-scoped subscriptions reject missing source identifiers cleanly.
- Preserved the wrapper-based capability contract before falling back to direct browser API checks.

## 3.0.0 - 2026-09-02

### Added
- Added opt-in browser notifications for newly ready inbox documents, with notification clicks opening the classifier main page.

### Added
- Added storage backend catalog metadata for the runtime registry, including backend names, categories, and descriptions.
- Added backend validation helpers to confirm backend health and resolve the path used for a configured storage endpoint.
- Added regression tests covering backend registration metadata and local NAS validation behavior.

### Changed
- Kept the canonical local NAS default behavior intact while exposing registry metadata needed for source/destination health checks.
- Documented the backend health validation slice in the project roadmap and development notes.

### Fixed
- Added the missing backend manager contract for `backend_catalog()` and `validate_backend()` to the storage abstraction layer.
