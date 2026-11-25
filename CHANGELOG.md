# Changelog

All notable changes to this project are documented here.

## Unreleased

## 5.0.2 - 2026-11-25

### Fixed
- The prewarm pass (at startup, every `BACKGROUND_SCAN_SECONDS`, or after `POST /api/classification/prewarm`) runs in a worker thread. It does OCR and Gemini calls synchronously and used to block the event loop, so the web UI, the API and the container health check got no answer until it finished; on a large inbox behind a network mount that took minutes.

## 5.0.1 - 2026-11-25

### Fixed
- The container image builds again: base image pinned by digest (`python:3.12.16-alpine3.24`) and Python packages pinned exactly (PyMuPDF 1.28.2, the newest with a musllinux wheel; unpinned, pip picked PyMuPDF 2.1 and tried to compile it). The `v5.0.0` tag never produced an image; use 5.0.1.

## 5.0.0 - 2026-11-25

### ⚠️ Upgrade note: background scanning is off by default
- **`BACKGROUND_SCAN_SECONDS` defaults to `0`**: the classifier no longer scans its inbox every 30 seconds. New PDFs are picked up at startup and when `POST /api/classification/prewarm` is called (e.g. by n8n after it drops a file). To keep the old behavior, set `BACKGROUND_SCAN_SECONDS=30`. See README "Upgrading".

### Added
- On-demand mode for hosts that let the classifier sleep when idle (#53): with `BACKGROUND_SCAN_SECONDS=0` (now the default), one prewarm pass runs at startup and after that only on request (`POST /api/classification/prewarm`).
- `GET /api/activity` reports busy and idle state and the next private deletion, so a host can stop the app safely and wake it in time. Polling it does not count as activity.
- A "Waking up the classifier…" notice while a request takes longer than 1.5 s.
- Container images are published to `ghcr.io/cdro/classifier` on every `v*` tag (`.github/workflows/release.yml`).

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
