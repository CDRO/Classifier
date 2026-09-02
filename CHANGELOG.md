# Changelog

All notable changes to this project are documented here.

## Unreleased

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
