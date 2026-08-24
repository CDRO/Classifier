# Document Classifier - Tier 1 Development

## Overview

This is the initial implementation of the document processing pipeline: **n8n ingestion + local NAS classification + configurable destinees**.

## Development Status

- ✅ **Phase 1:** Documentation complete (SYSTEM_SPECIFICATION.md, WORKFLOW_TESTING_DEBUGGING.md, DEPLOYMENT_MANAGEMENT_MANUAL.md, AGENTS.md)
- ✅ **Phase 2:** n8n ingestion boundary and local classified-output architecture defined
- ✅ **Phase 3:** GitHub workflow mandate + 10-cycle code review integrated
- 🔄 **Tier 1 (In Progress):** Native web interface and local classification workflow

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

## Getting Started

### 1. Install Dependencies

```bash
# Install development dependencies
pip install -e ".[dev]"

# Or just install core dependencies
pip install -e .
```

### 2. Run the Native Frontend in Docker

The current web interface is a static browser application. The Dockerfile uses Python's standard-library HTTP server, so the frontend image requires no Node.js, npm, or frontend package installation.

```bash
docker build -t classifier-web .
docker run --rm -p 3000:3000 classifier-web
```

Open `http://localhost:3000`. The image creates `/data/source` and `/data/destination`; host-specific mounts will be added in `docker-compose.yml`.

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

## Architecture: StorageBackend ABC

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

External source access, including Google Drive or email, is configured in n8n. The classifier receives completed PDFs in `/data/source` and does not store source credentials. Host-specific NAS folders will be mapped to this path by `docker-compose.yml`.

**Setup:** See [DEPLOYMENT_MANAGEMENT_MANUAL.md Section 4.2.1](docs/guides/DEPLOYMENT_MANAGEMENT_MANUAL.md#421-n8n-ingestion-handoff)

### Local Classification Output

**Output root:** `/data/destination/`

**Features:**
- One output folder per configured destinee
- Initial destinees: `Destinee A`, `Destinee B`, `Destinee C`
- Destinees can be edited in the native browser interface

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
- [x] Finalize a reviewed PDF into its configured destinee folder
- [ ] Implement Google Drive API integration (replace TODO placeholders)
- [ ] Run full test suite with real Google Drive API
- [ ] Security audit for credential handling
- [ ] Performance testing (upload/download speed, API rate limits)
- [ ] Documentation for developers adding new backends

### Short-term (Tier 2: API Endpoints + UI)
- [ ] FastAPI endpoints for ingestion status and classification configuration
- [ ] Connect the native JavaScript UI to the classification configuration API
- [ ] Integration tests for all API endpoints
- [ ] E2E tests for full workflow

The frontend is intentionally native HTML, CSS, and browser JavaScript. It has no Node.js, npm, or third-party runtime dependency. Any future third-party browser library must be checked in as compiled JavaScript after review.

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

**Version:** 1.0.0-tier1  
**Last Updated:** 2026-08-17  
**Status:** Development in progress
