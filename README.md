# Document Classifier - Tier 1 Development

## Overview

This project is evolving from a single-provider workflow into a general document intake and routing platform: **source-neutral ingestion + destination-neutral routing + local classification**. The current implementation still uses local NAS and the Google Drive backend as concrete examples, but the long-term architecture is intentionally pluggable so we can support multiple inputs and destinations without redesigning the classifier.

## Development Status

- ✅ **Release 2.0.0:** Storage backend support, private-retention cleanup, and dedicated configuration UI are complete
- ✅ **Phase 1:** Documentation complete (SYSTEM_SPECIFICATION.md, WORKFLOW_TESTING_DEBUGGING.md, DEPLOYMENT_MANAGEMENT_MANUAL.md, AGENTS.md)
- ✅ **Phase 2:** n8n ingestion boundary and local classified-output architecture defined
- ✅ **Phase 3:** GitHub workflow mandate + 10-cycle code review integrated
- ✅ **Phase 4:** Google Drive hardening and env-gated smoke validation are complete
- ✅ **Native web interface and local classification workflow:** completed for the current release
- ✅ **Storage backend health validation slice:** backend registry metadata and validation helpers are in place for source/destination health checks
- 🔜 **Strategic sprint:** source/destination abstraction and the next 10 workflow slices continue to be prioritized over provider-specific deepening

## Project Structure

```
.
├── src/
│   └── storage/
│       ├── __init__.py              # StorageBackend ABC
│       ├── google_drive.py           # GoogleDriveBackend implementation
│       └── local_nas.py              # LocalNASBackend implementation
├── tests/
│   └── unit/
│       └── test_storage_backends.py  # 18 unit tests
├── frontend/
│   ├── index.html                    # Native browser interface
│   ├── config.js                     # Container path defaults
│   ├── app.js                        # Dependency-free UI behavior
│   └── styles.css                    # Static styling
├── Dockerfile                        # Static frontend image
├── docs/
│   ├── specs/
│   │   └── SYSTEM_SPECIFICATION.md
│   └── guides/
│       ├── WORKFLOW_TESTING_DEBUGGING.md
│       └── DEPLOYMENT_MANAGEMENT_MANUAL.md
├── AGENTS.md                         # Agent guidelines + CAVEMAN manifesto
├── pyproject.toml                    # Project configuration & dependencies
└── README.md                         # This file
```
## Background notification fallback behavior

Classifier exposes a native in-app fallback for browsers that cannot support background push delivery. The frontend checks the wrapper capability contract first when it is available, then falls back to the browser's native Notification and Push APIs without crashing.

- Unsupported browsers keep the inbox and review workflow fully usable.
- Denied notification permission keeps the app functional while showing a banner explaining that in-app alerts remain available.
- The notification toggle is disabled in degraded states instead of throwing or leaving the page in an inconsistent state.

This keeps the review flow usable even when the browser cannot maintain background delivery or when the user has blocked notification permission.
## Getting Started

### 1. Install Dependencies

```bash
# Install core dependencies
pip install -e .

# Install the optional Google Drive backend support
pip install -e ".[google-drive]"

# Install development dependencies
pip install -e ".[dev]"
```

### 2. Run the Native Frontend in Docker

The current web interface is a static browser application. The Dockerfile uses Python's standard-library HTTP server, so the frontend image requires no Node.js, npm, or frontend package installation.

```bash
docker build -t classifier-web .
docker run --rm -p 3000:3000 classifier-web
```

Open `http://localhost:3000`.

The application expects a writable inbox and a writable destination root, but it does not depend on a particular NAS or SMB share. In production, you can mount the container to any folder that your infrastructure provides, including a remote share, a mounted NAS path, or any other directory that your workflow exposes. The critical requirement is that the container sees a readable source inbox and a writable destination root.

A typical setup is:

```bash
docker run --rm \
  -p 3000:3000 \
  -v /path/to/inbox:/data/source \
  -v /path/to/output:/data/destination \
  classifier-web
```

The default behavior stays valid as `/data/source` and `/data/destination`, but the application is intentionally mount-driven rather than locked to a specific storage topology.

### 3. Ingestion pattern

The classifier is designed to receive documents from an external workflow, not to own the complete file transport layer.

Recommended pattern:

1. Build an n8n workflow or similar automation that watches a remote inbox, folder, email attachment source, or API feed.
2. Move or copy completed PDFs into the classifier inbox, typically mounted at `/data/source`.
3. Let the app classify and review the PDFs in the browser.
4. Use n8n or another automation layer to move classified files away from the final destination directory when needed, depending on your own operational rules.

The classifier therefore treats the source and destination as configured filesystem roots, not as a hardcoded vendor-specific implementation. It is the automation layer around the container that decides where the files originate and where they move after classification.

### 3. Run Tests

Run the Docker-backed integration test from PowerShell:

```powershell
.\tests\docker\Test-Docker.ps1
```

The test builds the image, allocates an isolated temporary source and destination, starts a uniquely named container on a free port, exercises the API, and removes the container and temporary directories in a `finally` block. It does not stop or replace the normal development container.

```bash
# Run all storage backend tests
pytest tests/unit/test_storage_backends.py -v

# Run with coverage report
pytest tests/unit/test_storage_backends.py -v --cov=src/storage

# Generate HTML coverage report
pytest tests/unit/test_storage_backends.py --cov=src/storage --cov-report=html
# Open htmlcov/index.html in browser
```

### 4. Code Quality Checks

```bash
# Type checking
mypy src/

# Linting
flake8 src/ tests/

# Security scanning
bandit -r src/

# Code formatting (check)
black --check src/ tests/

# Code formatting (apply)
black src/ tests/
```

## Architecture: Source and Destination Abstraction

The `StorageBackend` abstract base class remains the core contract for storage providers, but in the next roadmap we treat it as the foundation for a broader pipeline model:

- Source backends: local folders, NAS shares, Google Drive, SMB, email inboxes, and webhook/APIs
- Destination backends: local folders, NAS folders, Google Drive, SharePoint, email targets, and archive stores
- Shared lifecycle: ingest → classify → review → route → archive → cleanup

This keeps the classifier independent from a single storage destination or provider. The architecture is intentionally backend-neutral so the business logic does not have to be reworked every time a new data source or output target is added.

The `StorageBackend` abstract base class defines a unified interface for all storage providers:

```python
class StorageBackend(ABC):
    async def authenticate(self, credentials: Dict[str, str]) -> bool
    async def list_folders(self) -> List[Dict[str, str]]
    async def upload_file(self, folder_id: str, filename: str, file: BinaryIO) -> str
    async def download_file(self, file_id: str) -> BinaryIO
    async def list_files(self, folder_id: str, pattern: str = "*.pdf") -> List[Dict]
    async def delete_file(self, file_id: str) -> bool
    async def get_storage_info(self) -> Dict[str, str]
```

### n8n Ingestion

The recommended integration pattern is to use n8n or a similar workflow tool to place completed PDFs in the classifier inbox. The container itself should not be treated as the only source of truth for document movement. The app receives PDFs through the configured source root, which can be a mounted local folder or any remote directory exposed to the container.

This means the source root is operationally owned by the surrounding automation, not by the classifier itself. The app simply processes what the inbox contains.

**Setup:** See [DEPLOYMENT_MANAGEMENT_MANUAL.md Section 4.2.1](docs/guides/DEPLOYMENT_MANAGEMENT_MANUAL.md#421-n8n-ingestion-handoff)

### Local Classification Output

**Output root:** `/data/destination/`

After successful finalization, the source PDF is moved from `/data/source` to `/data/archive` so the inbox contains only unprocessed documents. The destination folders remain under the configured route root, and the surrounding workflow can move classified files onward when needed.
The temporary `/data/temp/processing/<processing_id>/` workspace is removed after the durable classified and archive copies succeed.

**Features:**
- One output folder per configured destinee
- No destinees are preconfigured; administrators add them in the web interface.
- Destinees can be edited in the native browser interface
- The destination directory is a mounted or managed folder and does not require a built-in NAS or SMB implementation

### Strategic Roadmap: v3.0.0 and beyond

The next release is intentionally narrow and focused on queueing and the user-facing review flow. This keeps the project practical without forcing a provider-specific implementation path.

#### v3.0.0: Queuing and UI updates
1. Background prewarm queue for pending PDFs
2. Readiness state in the review UI (queued, preparing, ready, failed)
3. Suggested filename and metadata visibility before full review clicks
4. UI refinements that keep the default source path stable and make the active route explicit without broad multi-source expansion

#### Later, if needed
1. Storage health checks and validation UI
2. More advanced source/destination adapters
3. Archive policy enforcement or retention automation
4. Email inbox ingestion adapter
5. Microsoft 365 / SharePoint adapter
6. Webhook/API ingestion and outbound routing

The current project stance is intentionally simple: expose the source and destination as mounted folders, let n8n or another automation tool handle document transport, and keep the classifier focused on the review and classification workflow.

## Private Retention Guarantee

Private documents are not only marked; they are enforced by a persisted expiry timestamp and a background cleanup loop.

### How it works

1. A document is marked private through `POST /api/documents/{filename}/private`.
2. The app stores the following state in `documents.json`:
   - `private: true`
   - `private_at`
   - `delete_after`
   - the source and destination paths that were observed at the time of marking
3. The app starts a background task on startup that calls `cleanup_private_documents()` every 60 seconds.
4. `cleanup_private_documents()` compares the current UTC timestamp with the stored `delete_after` value.
5. When the current time is past the deadline, it deletes the file from the source directory and any matching destination copies, then removes the matching log/job/audit entries.
6. The same cleanup is also triggered during `scan_input_directory()`, so resumed scans do not leave expired private files behind.

### Why this guarantees the one-hour window

The decisive requirement is the persisted `delete_after` time. It is not just a UI flag or a transient variable. If the app is still running, the 60-second worker enforces it automatically. If the app restarts, the timestamp remains in the persisted state and the next startup worker continues enforcing it. The deletion is therefore tied to the actual deadline, not to a page refresh or a single request.

### Operational safety

- Files are deleted from both source and destination copies when they match the private record.
- Matching job records and audit entries are removed to prevent stale references.
- Cleanup is best-effort while the app is running, but the persisted deadline remains the source of truth and is rechecked by the worker loop.

## Testing

### Unit Tests (18 tests total)

**Google Drive Backend (9 tests):**
- ✓ Authenticate with valid credentials
- ✓ Authenticate with missing type field (fails)
- ✓ Authenticate with wrong type (fails)
- ✓ List folders before auth (fails)
- ✓ List folders after auth (succeeds)
- ✓ Upload with empty filename (fails)
- ✓ Upload with empty folder_id (fails)
- ✓ Download with empty file_id (fails)
- ✓ Delete with empty file_id (fails)

**Local NAS Backend (9 tests):**
- ✓ Authenticate with valid path
- ✓ Authenticate with nonexistent path (fails)
- ✓ Authenticate with empty path (fails)
- ✓ Authenticate with file path instead of directory (fails)
- ✓ List folders before auth (fails)
- ✓ List folders after auth (succeeds)
- ✓ Upload file to NAS
- ✓ Download file from NAS
- ✓ Delete file from NAS

**Interface Compliance (Tests for both):**
- ✓ Backend implements StorageBackend interface
- ✓ All required methods are implemented

### Running Tests

```bash
# Run all tests
pytest tests/unit/test_storage_backends.py -v

# Run specific test class
pytest tests/unit/test_storage_backends.py::TestGoogleDriveBackend -v

# Run specific test
pytest tests/unit/test_storage_backends.py::TestLocalNASBackend::test_upload_file_to_nas -v

# Run with output capture
pytest tests/unit/test_storage_backends.py -v -s
```

## GitHub Workflow (MANDATORY)

All development follows this process:

1. **Create GitHub Issue** describing the work
2. **Create GitHub Milestone** (e.g., `v1.0.0-tier1`)
3. **Create GitHub PR** linked to Issue + Milestone
4. **Implement in feature branch** (`feature/storage-backend-abc`)
5. **Submit to 10-cycle code review** (reviewer + fixer subagents)
6. **Merge after 10 cycles pass** all quality criteria

See [AGENTS.md Section 2.0](AGENTS.md#20-github-workflow-mandate-before-starting-any-task) for details.

## Next Steps

### Immediate (Tier 1 Completion)
- [x] Scan n8n input and inspect individual documents through the API
- [x] Run document-inbox and inspection checks in a disposable Docker container
- [x] Prepare selected PDFs and display review metadata in the native UI
- [x] Analyze PDF text locally and suggest a descriptive output filename
- [x] Use Tesseract OCR for image-only pages
- [x] Improve OCR input with grayscale rendering and automatic page segmentation
- [x] Detect basic document language and expose local classification signals
- [x] Extract local dates, amounts, and reference numbers
- [x] Add layout-aware page analysis signals
- [x] Detect duplicate PDF redelivery with SHA-256 content identity
- [x] Dismiss inbox PDFs into a separate archive without processing
- [x] Rotate prepared PDF pages from the review interface
- [x] Create split PDF parts from user-selected page boundaries
- [x] Finalize split parts with independent filenames and destinees
- [x] Display prepared-page thumbnails in the review interface
- [x] Ask Gemini to suggest filenames using the document's language
- [x] Add optional Gemini enrichment with local fallback
- [x] Show Gemini configuration and actual analysis provider in the review UI
- [x] Show Gemini quota/outage warnings and clear them after recovery
- [x] Show the running Docker image version in the interface
- [x] Require explicit user-selected destinee routing without AI proposals
- [x] Verify Gemini 3.6 Flash analysis with the configured server key
- [x] Finalize a reviewed PDF into its configured destinee folder
- [x] Rename the classified output while preserving the original archive filename
- [x] Persist document lifecycle states from receipt through classification
- [x] Display processing history across container restarts
- [x] Implement Google Drive API integration (replace TODO placeholders)
- [ ] Run full test suite with real Google Drive API
- [x] Security audit for credential handling
- [ ] Performance testing (upload/download speed, API rate limits)
- [ ] Documentation for developers adding new backends

### Credential handling guarantee

The project treats Google Drive service-account keys and other secrets as sensitive data. Any validation failure or backend error logs now pass through a sanitization step so raw private-key blocks, API keys, and tokens are replaced with `[REDACTED]` before they reach application logs or traces. This keeps misconfiguration failures visible without exposing the secret material itself.

### Next (Tier 1.5: Local Fallback and Document Handling)

1. **OCR fallback for scanned PDFs**
    - Detect pages with little or no extractable text.
    - Render those pages with PyMuPDF and run local Tesseract OCR.
    - Add German and English language data first.
    - Store OCR output only in the temporary processing workspace.

2. **Image preprocessing for OCR**
    - Grayscale, upscale, contrast enhancement, deskew, denoise, and orientation handling.

3. **Language-aware local analysis**
    - Detect the document language.
    - Select matching OCR and keyword rules.
    - Analyze each page separately and aggregate the result.

4. **Richer local classification**
    - Expand categories for invoices, receipts, medical documents, insurance, tax, banking, contracts, government letters, school documents, and utility bills.
    - Extract dates, sender/vendor, recipient, reference numbers, amounts, and currencies.
    - Return classification signals and confidence explanations.

5. **Document identity and duplicate detection**
    - Calculate a SHA-256 hash for each source PDF.
    - Track status by stable document identity rather than filename alone.
    - Detect duplicates when n8n changes a filename or redelivers a file.
    - Expose the matching classified filename as `duplicate_of`, including when older history lacks a stored hash.

6. **Page rotation**
    - Show page orientation in the review UI.
    - Allow 90, 180, and 270 degree rotation per page.
    - Apply rotation to the prepared PDF only.
    - Verify that the rotated result remains a valid PDF.

7. **Document splitting**
    - Show page thumbnails and page boundaries.
    - Allow users to add, remove, and move split points.
    - Support multiple output documents from one source PDF.
    - Preserve page order and validate that every page belongs to exactly one output.
    - Reordering pages via drag-and-drop persists to the working copy before the split/finalize flow is executed.

8. **Review and finalization integration**
    - Display OCR text, analysis signals, rotations, and split groups together.
    - Keep analysis text collapsed by default for a compact review flow, with each page expandable on demand.
    - Let the user correct the category, filename, and destinee.
    - Finalize all split outputs safely and archive the original once.

9. **Local fallback tests and performance checks**
    - Add OCR fixtures for German and English scanned pages.
    - Add rotation and split regression tests.
    - Add malformed-PDF, boundary, duplicate, and path-traversal tests.
    - Measure OCR and 50-page processing against NAS targets.

### Routing benchmark baseline (Issue #5)

The classifier now keeps a routing profile for each path so the decision thresholds are explicit and reviewable:

| Route | Provider | Median latency target | Estimated cost | Routing rule |
|---|---|---:|---:|---|
| readable local PDF | local | ~180 ms | $0.00 | native text is present and not noisy |
| scanned / blank PDF | tesseract | ~2300 ms | $0.00 | no readable text; OCR fallback is required |
| low-quality readable text | gemini | ~1800 ms | ~$0.00015 per request | local text is weak or noisy; AI enrichment is cheaper than manual correction |

This profile is surfaced through the `processing_profile` metadata returned by the prepare API and used as the default threshold matrix for the local-vs-AI routing engine. The benchmark values are intentionally conservative baselines for the classifier logic; they should be re-measured against production PDFs and the NAS hardware profile before release tuning.

### Short-term (Tier 2: API Endpoints + UI)
- [ ] FastAPI endpoints for ingestion status and classification configuration
- [ ] Connect the native JavaScript UI to the classification configuration API
- [ ] Integration tests for all API endpoints
- [ ] E2E tests for full workflow

The frontend is intentionally native HTML, CSS, and browser JavaScript. It has no Node.js, npm, or third-party runtime dependency. Any future third-party browser library must be checked in as compiled JavaScript after review.

OCR defaults to English and German. Override the server setting with `OCR_LANGUAGES` (for example `eng+deu`) when adding compatible Tesseract language data to the image.
OCR pages are rendered in grayscale at a configurable scale (`OCR_RENDER_SCALE`, default `2`) and passed through Tesseract's automatic page segmentation.

### Medium-term (Tier 3: Additional Backends)
- [ ] SharePoint backend implementation
- [ ] Dropbox backend implementation
- [ ] S3/AWS backend implementation
- [ ] Azure Blob Storage backend implementation

## Code Quality Standards

All code MUST meet:
- ✅ Type checking (mypy --strict)
- ✅ Linting (flake8)
- ✅ Security scanning (bandit)
- ✅ Test coverage (≥85%)
- ✅ Code formatting (black)
- ✅ All 10-cycle review criteria

See [AGENTS.md Section 2.5](AGENTS.md#25-code-quality-criteria-checked-each-cycle) for details.

## CAVEMAN Principles

This project adheres to the **CAVEMAN Manifesto**:

- **C**larity: Variable names unambiguous, complex logic explained
- **A**void Over-Engineering: Build what's needed now, not future speculation
- **V**alue: Every line contributes to measurable user value
- **E**agerness: Deploy working code quickly, iterate based on feedback
- **M**inimize: Dependencies, complexity, API surface, configuration
- **A**gility: Adapt to feedback without lengthy planning cycles
- **N**udge: Improve incrementally, favor small PRs over big rewrites
- **M**indfulness: Document trade-offs explicitly

See [AGENTS.md Preamble](AGENTS.md#preamble-the-caveman-manifesto) for full details.

## Questions or Issues?

1. Check [SYSTEM_SPECIFICATION.md](docs/specs/SYSTEM_SPECIFICATION.md) for architecture
2. Check [WORKFLOW_TESTING_DEBUGGING.md](docs/guides/WORKFLOW_TESTING_DEBUGGING.md) for testing
3. Check [DEPLOYMENT_MANAGEMENT_MANUAL.md](docs/guides/DEPLOYMENT_MANAGEMENT_MANUAL.md) for operations
4. Check [AGENTS.md](AGENTS.md) for development process
5. Create a GitHub Issue for bugs or feature requests

---

**Version:** 2.0.0  
**Last Updated:** 2026-08-17  
**Status:** Development in progress
