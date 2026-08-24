# Development & Quality Assurance Workflow

**Version:** 1.0  
**Date:** 2026-08-17  
**Scope:** Complete testing, fuzzing, debugging, and CI/CD pipeline for Document Processing Pipeline

---

## Executive Summary

This document defines a comprehensive workflow for testing, fuzzing, bug detection, and fixing across all layers of the document processing application. The approach combines unit testing, integration testing, property-based testing, fuzzing, and systematic debugging to ensure robustness, security, and maintainability.

---

## 1. Testing Strategy

### 1.1 Testing Pyramid

```
         ╱╲
        ╱  ╲  E2E Tests (5-10%)
       ╱────╲
      ╱      ╲  Integration Tests (20-30%)
     ╱────────╲
    ╱          ╲ Unit Tests (60-75%)
   ╱────────────╲
```

### 1.2 Test Categories & Coverage Goals

| Test Type | Coverage Goal | Tools | Execution Time |
|-----------|---------------|-------|-----------------|
| Unit Tests | 85%+ | pytest, unittest | <30s |
| Integration Tests | 70%+ | pytest + fixtures | <5m |
| API Contract Tests | 95%+ | httpx, pydantic validators | <2m |
| Fuzzing Tests | Continuous | Hypothesis, atheris | <10m per run |
| Security Tests | Critical paths | bandit, safety | <1m |
| E2E Tests | Happy path + errors | Playwright, pytest | <2m |

---

## 2. Unit Testing Framework

### 2.1 Backend Unit Tests (Python)

**File Structure:**
```
tests/
├── unit/
│   ├── test_pdf_processor.py          # PyMuPDF wrapper
│   ├── test_ai_classifier.py          # Gemini/Claude integration
│   ├── test_metadata_validator.py     # Pydantic models
│   ├── test_file_router.py            # Export destination logic
│   ├── test_ocr_fallback.py           # Tesseract integration
│   └── test_utils.py                  # Helper functions
├── integration/
│   ├── test_api_endpoints.py
│   ├── test_storage_workflow.py
│   ├── test_ai_pipeline.py
│   └── test_export_destinations.py
├── e2e/
│   ├── test_user_workflow.py
│   └── test_batch_processing.py
├── fuzzing/
│   ├── fuzz_pdf_parser.py
│   ├── fuzz_metadata_extraction.py
│   └── fuzz_api_payloads.py
└── fixtures/
    ├── sample_pdfs/                   # Test documents
    ├── mock_responses.py              # Mock API responses
    └── conftest.py                    # Pytest configuration
```

### 2.2 Example Unit Test: PDF Processor

```python
# tests/unit/test_pdf_processor.py
import pytest
from pathlib import Path
from src.pdf_processor import PDFProcessor, PDFExtractionError

class TestPDFProcessor:
    
    @pytest.fixture
    def processor(self):
        return PDFProcessor()
    
    @pytest.fixture
    def sample_pdf(self, tmp_path):
        """Create a minimal valid PDF for testing."""
        # Use sample_pdfs/valid_3page.pdf from fixtures
        return Path(__file__).parent / "fixtures" / "sample_pdfs" / "valid_3page.pdf"
    
    def test_extract_page_count_valid_pdf(self, processor, sample_pdf):
        """✓ Extract page count from valid PDF."""
        count = processor.get_page_count(sample_pdf)
        assert count == 3
        assert isinstance(count, int)
    
    def test_extract_page_count_corrupted_pdf(self, processor, tmp_path):
        """✓ Handle corrupted PDF gracefully."""
        corrupted = tmp_path / "corrupted.pdf"
        corrupted.write_bytes(b"Not a real PDF\x00\xff\xfe")
        
        with pytest.raises(PDFExtractionError) as exc_info:
            processor.get_page_count(corrupted)
        
        assert "Invalid PDF" in str(exc_info.value)
    
    def test_extract_text_vector_pdf(self, processor, sample_pdf):
        """✓ Extract text from vector PDF."""
        text = processor.extract_text(sample_pdf, page_num=0)
        assert isinstance(text, str)
        assert len(text) > 0
    
    def test_render_page_as_image(self, processor, sample_pdf, tmp_path):
        """✓ Render page to JPEG with correct dimensions."""
        output = tmp_path / "page.jpg"
        processor.render_page(sample_pdf, page_num=0, output_path=output, dpi=150)
        
        assert output.exists()
        assert output.stat().st_size > 1000  # JPEG should be >1KB
    
    def test_rotate_page_90_degrees(self, processor, sample_pdf, tmp_path):
        """✓ Apply 90° rotation without corruption."""
        rotated = tmp_path / "rotated.pdf"
        processor.rotate_pages(sample_pdf, rotated, {0: 90})
        
        assert rotated.exists()
        processor.extract_text(rotated, page_num=0)  # Should not raise
    
    def test_split_pdf_at_boundaries(self, processor, sample_pdf, tmp_path):
        """✓ Split PDF at specified page boundaries."""
        splits = processor.split_at_pages(sample_pdf, split_indices=[1, 2])
        
        assert len(splits) == 3
        assert processor.get_page_count(splits[0]) == 1
        assert processor.get_page_count(splits[1]) == 1
        assert processor.get_page_count(splits[2]) == 1
    
    def test_process_empty_pdf(self, processor, tmp_path):
        """✓ Reject empty PDF (0 pages)."""
        # Note: Most PDF libraries cannot create 0-page PDFs
        # This test validates the validation logic
        with pytest.raises(PDFExtractionError):
            processor.get_page_count(None)
    
    @pytest.mark.parametrize("dpi,expected_size", [
        (150, (1200, 1550)),
        (300, (2400, 3100)),
    ])
    def test_render_respects_dpi(self, processor, sample_pdf, tmp_path, dpi, expected_size):
        """✓ Rendered image size scales with DPI."""
        output = tmp_path / f"page_{dpi}dpi.jpg"
        processor.render_page(sample_pdf, page_num=0, output_path=output, dpi=dpi)
        
        from PIL import Image
        img = Image.open(output)
        assert img.size[0] >= expected_size[0] * 0.95  # Allow 5% variance

### 2.2.2 Storage Backend Unit Tests

```python
# tests/unit/test_storage_backends.py
import pytest
from src.storage.backends import GoogleDriveBackend, LocalNASBackend, StorageBackend
from src.storage.exceptions import StorageAuthenticationError, StorageOperationError

class TestStorageBackendInterface:
    """Test that all backends implement the StorageBackend contract."""
    
    @pytest.fixture
    def google_drive_backend(self):
        return GoogleDriveBackend(service_account_path="/config/gd-sa.json")
    
    @pytest.fixture
    def local_nas_backend(self):
        return LocalNASBackend(base_path="/volume1/Archive")
    
    def test_google_drive_authenticate_valid_credentials(self, google_drive_backend, mocker):
        """✓ Google Drive authentication succeeds with valid service account."""
        mocker.patch.object(google_drive_backend, '_get_service', return_value=MagicMock())
        
        result = google_drive_backend.authenticate({
            "type": "service_account",
            "project_id": "test-project"
        })
        
        assert result is True
    
    def test_google_drive_authenticate_invalid_credentials(self, google_drive_backend, mocker):
        """✓ Google Drive authentication fails with invalid credentials."""
        mocker.patch.object(google_drive_backend, '_get_service', side_effect=Exception("Invalid key"))
        
        with pytest.raises(StorageAuthenticationError):
            google_drive_backend.authenticate({"invalid": "creds"})
    
    def test_local_nas_authenticate_path_exists(self):
        """✓ Local NAS backend authenticates if path is readable."""
        backend = LocalNASBackend(base_path="/volume1/Archive")
        result = backend.authenticate({})
        assert result is True
    
    def test_local_nas_authenticate_path_not_exists(self, tmp_path):
        """✓ Local NAS backend fails if path is not accessible."""
        backend = LocalNASBackend(base_path="/nonexistent/path")
        
        with pytest.raises(StorageAuthenticationError):
            backend.authenticate({})
    
    def test_list_folders_google_drive(self, google_drive_backend, mocker):
        """✓ Google Drive lists folders in account."""
        mock_service = MagicMock()
        mock_service.files().list().execute.return_value = {
            "files": [
                {"id": "folder1", "name": "Document Inbox", "mimeType": "application/vnd.google-apps.folder"},
                {"id": "folder2", "name": "Archive", "mimeType": "application/vnd.google-apps.folder"}
            ]
        }
        mocker.patch.object(google_drive_backend, '_get_service', return_value=mock_service)
        
        folders = google_drive_backend.list_folders()
        
        assert len(folders) == 2
        assert folders[0]["name"] == "Document Inbox"
    
    def test_upload_file_google_drive(self, google_drive_backend, mocker, tmp_path):
        """✓ Google Drive upload succeeds and returns file_id."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"PDF content")
        
        mock_service = MagicMock()
        mock_service.files().create().execute.return_value = {"id": "file_123"}
        mocker.patch.object(google_drive_backend, '_get_service', return_value=mock_service)
        
        file_id = google_drive_backend.upload_file("folder_id", "test.pdf", open(test_file, "rb"))
        
        assert file_id == "file_123"
    
    def test_download_file_google_drive(self, google_drive_backend, mocker):
        """✓ Google Drive download returns file stream."""
        mock_service = MagicMock()
        mock_request = MagicMock()
        mock_request.getbytes.return_value = b"PDF content"
        mock_service.files().get_media.return_value = mock_request
        mocker.patch.object(google_drive_backend, '_get_service', return_value=mock_service)
        
        file_stream = google_drive_backend.download_file("file_123")
        
        assert file_stream.read() == b"PDF content"
    
    def test_local_nas_upload_creates_file(self, tmp_path):
        """✓ Local NAS upload writes file to disk."""
        backend = LocalNASBackend(base_path=str(tmp_path))
        test_content = b"PDF content"
        from io import BytesIO
        
        file_id = backend.upload_file(str(tmp_path), "test.pdf", BytesIO(test_content))
        
        uploaded_file = tmp_path / "test.pdf"
        assert uploaded_file.exists()
        assert uploaded_file.read_bytes() == test_content
    
    def test_local_nas_delete_file(self, tmp_path):
        """✓ Local NAS delete removes file."""
        backend = LocalNASBackend(base_path=str(tmp_path))
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"content")
        
        success = backend.delete_file(str(test_file))
        
        assert success is True
        assert not test_file.exists()
    
    def test_storage_config_validation(self):
        """✓ Storage configuration validates backend types."""
        from src.storage.config import StorageConfig
        
        # Valid config
        config = StorageConfig({
            "source": {"type": "google_drive", "folder_id": "123"},
            "classification": {
                "output_root": "/data/destination/",
                "destinees": ["Destinee A", "Destinee B"]
            }
        })
        assert config.is_valid() is True
        
        # Invalid backend type
        config = StorageConfig({
            "source": {"type": "invalid_backend", "path": "/"}
        })
        assert config.is_valid() is False
```

### 2.3 Unit Test Execution

```bash
# Run all unit tests with coverage report
pytest tests/unit/ -v --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_pdf_processor.py -v

# Run tests matching pattern
pytest tests/unit/ -k "pdf and rotation" -v

# Run with detailed output on failure
pytest tests/unit/ -vv --tb=long
```

---

## 3. Integration Testing

### 3.1 API Endpoint Integration Tests

```python
# tests/integration/test_api_endpoints.py
import pytest
from fastapi.testclient import TestClient
from src.main import app
import json

@pytest.fixture
def client():
    return TestClient(app)

class TestUploadEndpoint:
    
    def test_upload_valid_pdf(self, client, tmp_path):
        """✓ Upload valid PDF and receive document ID."""
        pdf_path = Path(__file__).parent / "fixtures" / "sample_pdfs" / "valid_3page.pdf"
        
        with open(pdf_path, "rb") as f:
            response = client.post(
                "/api/upload",
                files={"file": ("test.pdf", f, "application/pdf")}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "doc_id" in data
        assert "upload_timestamp" in data
    
    def test_upload_non_pdf_rejected(self, client):
        """✓ Reject non-PDF file uploads."""
        response = client.post(
            "/api/upload",
            files={"file": ("test.txt", b"Not a PDF", "text/plain")}
        )
        
        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]
    
    def test_upload_oversized_pdf_rejected(self, client, tmp_path):
        """✓ Reject PDFs exceeding size limit (500MB)."""
        large_file = tmp_path / "large.pdf"
        large_file.write_bytes(b"x" * (501 * 1024 * 1024))  # 501MB
        
        with open(large_file, "rb") as f:
            response = client.post(
                "/api/upload",
                files={"file": ("large.pdf", f, "application/pdf")}
            )
        
        assert response.status_code == 413
        assert "File too large" in response.json()["detail"]

class TestAnalysisEndpoint:
    
    def test_analyze_triggers_ai_classification(self, client, uploaded_doc_id, mocker):
        """✓ Analysis request calls Gemini API and returns suggestions."""
        # Mock Gemini API response
        mock_response = {
            "document_type": "Invoice",
            "split_points": [1, 15, 32],
            "confidence": 0.95
        }
        mocker.patch("src.ai_classifier.call_gemini", return_value=mock_response)
        
        response = client.post(f"/api/analyze", json={"doc_id": uploaded_doc_id})
        
        assert response.status_code == 202  # Accepted (async)
        assert "task_id" in response.json()
    
    def test_analysis_status_polling(self, client, analysis_task_id):
        """✓ Poll analysis task status until completion."""
        for _ in range(30):
            response = client.get(f"/api/status/{analysis_task_id}")
            assert response.status_code == 200
            
            data = response.json()
            if data["status"] == "completed":
                assert "result" in data
                break
            
            time.sleep(0.5)
        
        assert data["status"] == "completed"

class TestIngestionAndClassificationEndpoints:
    
    def test_get_ingestion_status(self, client):
        """✓ Report n8n handoff and fixed input path."""
        response = client.get("/api/ingestion/status")
        
        assert response.status_code == 200
        status = response.json()
        assert status["provider"] == "n8n"
        assert status["input_path"] == "/data/source"
    
    def test_get_classification_config(self, client):
        """✓ Retrieve fixed paths and configured destinees."""
        response = client.get("/api/classification/config")
        
        assert response.status_code == 200
        config = response.json()
        assert config["output_root"] == "/data/destination/"
        assert config["destinees"] == ["Destinee A", "Destinee B"]
    
    def test_update_classification_config(self, client):
        """✓ Update destinees without changing the n8n source."""
        response = client.post("/api/classification/config", json={
            "destinees": ["Destinee A", "Destinee B", "Shared"]
        })
        
        assert response.status_code == 200
        config = response.json()
        assert config["destinees"][-1] == "Shared"
        assert config["output_root"] == "/data/destination/"
    
    def test_update_classification_config_rejects_duplicates(self, client):
        """✓ Reject duplicate destinee names."""
        response = client.post("/api/classification/config", json={
            "destinees": ["Destinee A", "destinee a"]
        })
        
        assert response.status_code == 400
        assert "unique" in response.json()["detail"].lower()

---

## 4. Property-Based Testing & Fuzzing

### 4.1 Hypothesis Property-Based Tests

```python
# tests/fuzzing/test_metadata_properties.py
from hypothesis import given, strategies as st, settings, HealthCheck
import pytest
from src.models import DocumentMetadata, SplitPoint

class TestMetadataProperties:
    
    @given(
        page_count=st.integers(min_value=1, max_value=10000),
        split_indices=st.lists(st.integers(min_value=1, max_value=9999), unique=True)
    )
    @settings(max_examples=1000, suppress_health_check=[HealthCheck.too_slow])
    def test_split_indices_always_valid(self, page_count, split_indices):
        """✓ Split indices remain valid regardless of input."""
        sorted_splits = sorted(split_indices)
        
        # Property: All split indices must be < total pages
        for idx in sorted_splits:
            assert idx < page_count, f"Split index {idx} >= page count {page_count}"
        
        # Property: No duplicate split indices
        assert len(sorted_splits) == len(set(sorted_splits))
    
    @given(
        filename=st.text(alphabet="abcdefghijklmnopqrstuvwxyz_.-", min_size=1, max_size=255),
        doc_type=st.sampled_from(["Invoice", "Receipt", "Contract", "Other"]),
        date_str=st.dates().map(str)
    )
    def test_filename_generation_never_crashes(self, filename, doc_type, date_str):
        """✓ Filename generation handles any reasonable input."""
        from src.naming import generate_filename
        
        result = generate_filename(doc_type, filename, date_str)
        
        # Properties:
        assert isinstance(result, str)
        assert len(result) > 0
        assert len(result) < 255
        assert not any(c in result for c in '\\/:*?"<>|')  # No invalid chars
    
    @given(
        json_data=st.fixed_dictionaries({
            "document_type": st.text(),
            "vendor": st.text(),
            "split_points": st.lists(st.integers())
        })
    )
    def test_metadata_validation_never_crashes(self, json_data):
        """✓ Metadata validator doesn't crash on any JSON."""
        try:
            DocumentMetadata.parse_obj(json_data)
        except ValueError as e:
            # Should raise validation error, not crash
            assert "validation error" in str(e).lower()
```

### 4.2 Fuzzing with Atheris (Binary Protocol Fuzzing)

```python
# tests/fuzzing/fuzz_pdf_parser.py
import atheris
import sys
from src.pdf_processor import PDFProcessor

@atheris.instrument_func
def fuzz_pdf_parsing(data: bytes):
    """Fuzz test PDF parser with random binary data."""
    processor = PDFProcessor()
    
    try:
        # Try to parse as PDF
        processor.validate_pdf(data)
    except Exception as e:
        # Acceptable: parser rejects invalid input
        pass

def main():
    atheris.Setup(sys.argv, fuzz_pdf_parsing)
    atheris.Fuzz()

if __name__ == "__main__":
    main()

# Run:
# python -m atheris -i tests/fuzzing/pdf_corpus/ -timeout=5 tests/fuzzing/fuzz_pdf_parser.py
```

### 4.3 Fuzzing Command Execution

```bash
# Install fuzzing tools
pip install hypothesis atheris

# Run property-based tests
pytest tests/fuzzing/test_metadata_properties.py -v --hypothesis-seed=0

# Run atheris fuzzer (requires libFuzzer via bazel/cmake)
# python -m atheris -max_len=1000000 -max_total_time=60 fuzz_pdf_parser.py

# Continuous fuzzing with coverage tracking
pytest tests/fuzzing/ --cov=src --cov-report=html --maxfail=1 -n auto
```

---

## 5. Security Testing

### 5.1 Static Analysis: Bandit

```bash
# Scan Python code for common security issues
bandit -r src/ -f json -o bandit-report.json

# High-severity findings only
bandit -r src/ -ll

# Focus on specific categories
bandit -r src/ -t B303,B304,B305  # pickle, marshal, tempfile issues
```

**Bandit Configuration (.bandit):**
```yaml
exclude_dirs:
  - tests
  - .venv

skips:
  - B101  # assert_used (acceptable in tests)
  - B601  # paramiko_calls (if using SSH)

tests:
  - B303  # Pickle usage
  - B304  # Pickle with protocol
  - B305  # Shelve usage
  - B306  # Temp file usage
  - B307  # Eval usage
  - B308  # Mark-safe usage
  - B309  # HTTPSConnection usage
  - B310  # URL open usage
  - B311  # Random usage
  - B312  # Telnet usage
  - B313  # XML usage
  - B314  # XML usage
  - B315  # XML usage
  - B316  # XML usage
  - B317  # XML usage
  - B318  # XML usage
  - B319  # XML usage
  - B320  # XML usage
  - B321  # FTP usage
  - B322  # Unverified SSL
  - B323  # Unverified SSL
  - B324  # Hashlib usage
  - B325  # Temp file usage
```

### 5.2 Dependency Vulnerability Scanning: Safety

```bash
# Check Python dependencies for known vulnerabilities
pip install safety
safety check --file requirements.txt --json > safety-report.json

# Check with bare database (includes unofficial packages)
safety check --db https://safetydatabase.dev.safetycli.com
```

### 5.3 API Security Tests

```python
# tests/security/test_api_security.py
import pytest
from fastapi.testclient import TestClient
from src.main import app

class TestAPISecurityHeaders:
    
    def test_hsts_header_present(self):
        """✓ HSTS header enforces HTTPS."""
        client = TestClient(app)
        response = client.get("/api/health")
        
        assert "strict-transport-security" in response.headers
        assert "max-age=" in response.headers["strict-transport-security"]
    
    def test_no_server_version_leaked(self):
        """✓ Server header doesn't reveal version."""
        client = TestClient(app)
        response = client.get("/api/health")
        
        server = response.headers.get("server", "")
        assert not any(v in server for v in ["FastAPI", "Starlette"])

class TestAuthenticationBypass:
    
    def test_api_key_required_for_upload(self, client):
        """✓ Upload endpoint requires valid API key."""
        response = client.post("/api/upload", headers={})
        assert response.status_code == 401
        
        response = client.post("/api/upload", headers={"Authorization": "Bearer invalid"})
        assert response.status_code == 403
    
    def test_cannot_access_other_users_documents(self, client, user1_token, user2_doc_id):
        """✓ Cross-user document access denied."""
        response = client.get(
            f"/api/document/{user2_doc_id}",
            headers={"Authorization": f"Bearer {user1_token}"}
        )
        assert response.status_code == 403
```

---

## 6. Bug Detection & Logging

### 6.1 Structured Logging Framework

```python
# src/logging_config.py
import logging
from pythonjsonlogger import jsonlogger

def setup_logging():
    logger = logging.getLogger()
    
    # JSON formatter for structured logs
    logHandler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter()
    logHandler.setFormatter(formatter)
    logger.addHandler(logHandler)
    
    return logger

# Usage in app
logger = setup_logging()

logger.info(
    "PDF processed",
    extra={
        "doc_id": doc_id,
        "page_count": 50,
        "processing_time_ms": 1234,
        "ai_provider": "gemini"
    }
)
```

### 6.2 Error Tracking with Sentry

```python
# src/error_tracking.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

def init_sentry():
    sentry_sdk.init(
        dsn="https://your-sentry-dsn@sentry.io/project-id",
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,  # 10% of transactions
        environment="production"
    )

# In FastAPI exception handler
from fastapi import HTTPException

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    sentry_sdk.capture_exception(exc)
    return {"detail": "Internal server error"}
```

### 6.3 Health Check & Metrics

```python
# src/health_check.py
from datetime import datetime
from src.pdf_processor import PDFProcessor
from src.ai_classifier import AIClassifier

@app.get("/health")
async def health_check():
    """Comprehensive health check."""
    health_report = {
        "timestamp": datetime.utcnow().isoformat(),
        "status": "healthy",
        "checks": {}
    }
    
    # Check PDF processor
    try:
        processor = PDFProcessor()
        processor.get_page_count(dummy_pdf)
        health_report["checks"]["pdf_engine"] = "ok"
    except Exception as e:
        health_report["checks"]["pdf_engine"] = f"error: {e}"
        health_report["status"] = "degraded"
    
    # Check AI API connectivity
    try:
        classifier = AIClassifier()
        classifier.test_connection()
        health_report["checks"]["ai_api"] = "ok"
    except Exception as e:
        health_report["checks"]["ai_api"] = f"error: {e}"
        health_report["status"] = "degraded"
    
    # Check storage
    try:
        archive_path = Path("/volume1/Archive/")
        archive_path.stat()
        health_report["checks"]["storage"] = "ok"
    except Exception as e:
        health_report["checks"]["storage"] = f"error: {e}"
        health_report["status"] = "unhealthy"
    
    status_code = 200 if health_report["status"] == "healthy" else (503 if health_report["status"] == "unhealthy" else 200)
    return {"status_code": status_code, **health_report}
```

---

## 7. Debugging Methodology

### 7.1 Debug Levels & Verbosity

```python
# src/debug.py
import os
from enum import Enum

class DebugLevel(Enum):
    PRODUCTION = 0      # No debug output
    INFO = 1           # Basic logging
    DEBUG = 2          # Detailed logging + stack traces
    VERBOSE = 3        # All function calls + variable states
    TRACE = 4          # Binary-level operation tracing

DEBUG_LEVEL = DebugLevel(int(os.getenv("DEBUG_LEVEL", "0")))

def debug_log(message: str, level: DebugLevel = DebugLevel.DEBUG, **kwargs):
    """Log only if debug level permits."""
    if DEBUG_LEVEL.value >= level.value:
        print(f"[{level.name}] {message}", kwargs)

# Usage
debug_log("Processing PDF", DebugLevel.INFO, doc_id=doc_id)
debug_log("Page rotation angle: 90°", DebugLevel.VERBOSE, page_num=5)
```

### 7.2 Interactive Debugging with PDB

```python
# Insert breakpoint in code
from src.pdf_processor import process_pdf

def test_pdf_processing_debug():
    processor = PDFProcessor()
    pdf_path = "test.pdf"
    
    breakpoint()  # Stops execution here
    result = processor.process(pdf_path)
    
    # Debug commands:
    # (Pdb) p result                     # Print result
    # (Pdb) h                            # Help
    # (Pdb) c                            # Continue
    # (Pdb) n                            # Next line
    # (Pdb) s                            # Step into function
    # (Pdb) l                            # List code
```

### 7.3 Reproduce Bug: Minimal Test Case

```python
# tests/debugging/test_bug_split_boundary_off_by_one.py
"""
Bug Report: Split at page 15 causes 14 pages in first doc (should be 15)
Regression test for: https://github.com/project/issues/42
"""
import pytest
from src.pdf_processor import PDFProcessor

def test_split_at_page_15_includes_page_15(tmp_path):
    """Regression test: Verify split_at_pages includes boundary page in first doc."""
    processor = PDFProcessor()
    
    # Reproduce the bug with 50-page PDF
    pdf_path = Path(__file__).parent / "fixtures" / "50page.pdf"
    
    # Split at page 15 (should create: pages 1-14 in doc1, page 15+ in doc2)
    # BUT BUG: Was creating pages 1-13 in doc1, page 14+ in doc2
    splits = processor.split_at_pages(pdf_path, split_indices=[15])
    
    # Verify fix
    doc1_pages = processor.get_page_count(splits[0])
    doc2_pages = processor.get_page_count(splits[1])
    
    assert doc1_pages == 14, f"Expected 14 pages in doc1, got {doc1_pages}"
    assert doc2_pages == 36, f"Expected 36 pages in doc2, got {doc2_pages}"
```

---

## 8. Continuous Integration (CI/CD) Pipeline

### 8.1 GitHub Actions Workflow

```yaml
# .github/workflows/ci-pipeline.yml
name: CI/CD Pipeline
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.9", "3.10", "3.11"]
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      
      - name: Lint with flake8
        run: flake8 src/ --max-line-length=100
      
      - name: Type check with mypy
        run: mypy src/ --ignore-missing-imports
      
      - name: Security scan with bandit
        run: bandit -r src/ -ll
      
      - name: Unit & Integration Tests
        run: pytest tests/ -v --cov=src --cov-report=xml
      
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
      
      - name: Property-based testing (Hypothesis)
        run: pytest tests/fuzzing/ -v --hypothesis-seed=0
  
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Dependency vulnerability check
        run: |
          pip install safety
          safety check --json > safety-report.json
      
      - name: Upload security report
        uses: actions/upload-artifact@v3
        with:
          name: safety-report
          path: safety-report.json
  
  deploy:
    needs: [test, security]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - name: Build Docker image
        run: docker build -t classifier:${{ github.sha }} .
      
      - name: Deploy to Synology NAS
        env:
          NAS_HOST: ${{ secrets.NAS_HOST }}
          NAS_USER: ${{ secrets.NAS_USER }}
          NAS_PASSWORD: ${{ secrets.NAS_PASSWORD }}
        run: |
          docker save classifier:${{ github.sha }} | \
          ssh user@$NAS_HOST docker load
          ssh user@$NAS_HOST docker-compose -f /docker/classifier/docker-compose.yml restart
```

---

## 9. Bug Lifecycle & Resolution

### 9.1 Bug Report Template

```markdown
## Bug Report

**Title:** [Brief description]

**Environment:**
- OS: [Windows/Linux/macOS]
- Python Version: 3.9.x
- Application Version: v1.2.3
- Docker: yes/no

**Steps to Reproduce:**
1. Upload PDF: [filename or type]
2. Trigger analysis
3. Observe error

**Expected Behavior:**
[What should happen]

**Actual Behavior:**
[What actually happens]

**Error Message:**
\`\`\`
[Full error traceback]
\`\`\`

**Logs:**
\`\`\`json
[Relevant structured logs from Sentry/logs]
\`\`\`

**Severity:** [Critical/High/Medium/Low]
```

### 9.2 Bug Resolution Workflow

```
┌─ BUG REPORTED ────────────────────────────────┐
│  • Assigned to developer                      │
│  • Severity assessed                          │
│  • Environment reproduced (if possible)       │
└───────────────┬────────────────────────────────┘
                │
                ▼
┌─ ROOT CAUSE ANALYSIS ─────────────────────────┐
│  • Review logs + stack traces                 │
│  • Reproduce locally (create test case)       │
│  • Identify contributing factors              │
│  • Document findings in regression test       │
└───────────────┬────────────────────────────────┘
                │
                ▼
┌─ IMPLEMENT FIX ───────────────────────────────┐
│  • Write failing test case (TDD)              │
│  • Implement fix                              │
│  • Ensure all tests pass (unit + integration) │
│  • Run security scans                         │
│  • Document changes in commit message         │
└───────────────┬────────────────────────────────┘
                │
                ▼
┌─ CODE REVIEW ─────────────────────────────────┐
│  • Peer review fix                            │
│  • Verify test coverage                       │
│  • Check for edge cases                       │
│  • Approve PR                                 │
└───────────────┬────────────────────────────────┘
                │
                ▼
┌─ DEPLOY TO STAGING ───────────────────────────┐
│  • Run E2E tests                              │
│  • Smoke tests on staging NAS                 │
│  • Performance benchmarks                     │
│  • Verify fix resolves issue                  │
└───────────────┬────────────────────────────────┘
                │
                ▼
┌─ RELEASE TO PRODUCTION ───────────────────────┐
│  • Tag release version                        │
│  • Deploy via blue-green                      │
│  • Monitor health metrics                     │
│  • Update release notes                       │
└───────────────┬────────────────────────────────┘
                │
                ▼
        ┌─ BUG CLOSED ─┐
        │ • Verified   │
        │ • Documented │
        └──────────────┘
```

---

## 10. Performance Benchmarking

### 10.1 Baseline Performance Metrics

```python
# tests/performance/test_benchmarks.py
import pytest
from time import time
from src.pdf_processor import PDFProcessor

class TestPerformanceBenchmarks:
    
    @pytest.mark.benchmark
    def test_pdf_parsing_performance(self, benchmark, sample_50page_pdf):
        """Benchmark: Parse 50-page PDF should complete in <5 seconds."""
        processor = PDFProcessor()
        
        result = benchmark(processor.get_page_count, sample_50page_pdf)
        
        assert result == 50
        assert benchmark.stats.mean < 5.0  # Mean time < 5 seconds
    
    @pytest.mark.benchmark
    def test_page_rendering_performance(self, benchmark, sample_50page_pdf):
        """Benchmark: Render single page to JPEG should complete in <2 seconds."""
        processor = PDFProcessor()
        
        result = benchmark(
            processor.render_page,
            sample_50page_pdf,
            page_num=0,
            output_path="/tmp/page.jpg",
            dpi=150
        )
        
        assert benchmark.stats.mean < 2.0
    
    @pytest.mark.benchmark
    def test_api_upload_endpoint_performance(self, benchmark, client, sample_pdf):
        """Benchmark: Upload endpoint response time should be <1 second."""
        with open(sample_pdf, "rb") as f:
            result = benchmark(
                client.post,
                "/api/upload",
                files={"file": ("test.pdf", f, "application/pdf")}
            )
        
        assert result.status_code == 200
        assert benchmark.stats.mean < 1.0

# Run benchmarks
# pytest tests/performance/test_benchmarks.py -v --benchmark-only
```

## 10.2 Docker Integration Test Lifecycle

The Docker integration test at `tests/docker/Test-Docker.ps1` validates the built application rather than importing the API directly. It must:

1. Create isolated temporary source, destination, and configuration directories.
2. Add a completed PDF and an incomplete temporary file to the source directory.
3. Build the current `Dockerfile` image.
4. Start one uniquely named container on a dynamically allocated free port.
5. Verify the API, n8n scan behavior, SHA-256 duplicate detection, document metadata inspection, PDF preparation, OCR, local content analysis, language detection, classification signals, filename suggestions, browser file serving, lifecycle transitions, processing history, path traversal protection, safe output renaming, destinee finalization, source removal, archive preservation, temporary-workspace cleanup, configuration update, and mounted destinee-folder creation.
6. Remove the test container and temporary directories in `finally`, whether assertions pass or fail.

Run it from PowerShell:

```powershell
.\tests\docker\Test-Docker.ps1
```

The test must not use the development container name or port and must never leave a test container running after completion.

### 10.3 Local Fallback and Document-Handling Test Plan

The next implementation phase must add focused tests for:

- OCR activation when a page has no extractable text.
- German and English OCR language selection.
- Image preprocessing and orientation handling.
- Page-level text aggregation and classification signals.
- SHA-256 duplicate detection when filenames differ.
- Rotation at 90, 180, and 270 degrees.
- Split boundaries at the first page, last page, and between every page.
- Validation that every source page belongs to exactly one split output.
- Multiple output filenames and one-time source archiving.
- Malformed PDFs, empty documents, and failed OCR recovery.

All integration tests for these features must run in a disposable Docker container and remove the container and temporary mounts in `finally`.

---

## 11. Rollback Procedures

### 11.1 Quick Rollback Strategy

```bash
#!/bin/bash
# scripts/rollback.sh

PREV_VERSION=$1  # e.g., v1.2.2
NAS_HOST="192.168.1.100"

echo "Rolling back to $PREV_VERSION..."

ssh user@$NAS_HOST << 'EOF'
  cd /docker/classifier
  
  # Stop current version
  docker-compose down
  
  # Restore previous version
  docker pull classifier:$PREV_VERSION
  
  # Restore database (if applicable)
  # psql -d classifier < backups/db_$PREV_VERSION.sql
  
  # Start previous version
  docker-compose up -d
  
  # Verify health
  curl -s http://localhost:8000/health | jq .
EOF

echo "Rollback to $PREV_VERSION complete!"
```

---

## 12. Code Review & PR Approval Process

### 12.1 GitHub Workflow Mandate

**All work requires:**
1. GitHub Issue describing the work
2. GitHub Milestone (e.g., "v1.3.0", "Q3-2026 Batch")
3. GitHub PR linked to both Issue and Milestone
4. 10-cycle code review process (see section 12.2)
5. All approval criteria met (see section 12.3)

**Why this matters for QA:**
- Full traceability: Every test change traced to Issue → Milestone → PR → Review cycles
- Quality gates: 10 cycles ensure bugs are caught before merge
- Documentation: All decisions recorded in PR comments
- Accountability: Each reviewer comment gets a corresponding fix commit

### 12.2 The 10-Cycle Review Process

**Exactly 10 review cycles, each cycle consists of:**

1. **Reviewer Subagent posts Comment** (identifying issues):
   - Correctness problems (logic errors, boundary bugs)
   - Linting violations (PEP 8, formatting)
   - Bounds checking (values properly clamped?)
   - Type safety (correct types? implicit conversions?)
   - Test coverage (edge cases covered? adequate coverage?)
   - Code clarity (clear variable names? explanatory comments?)
   - Performance concerns (inefficiencies? memory leaks?)

2. **Fixer Subagent commits Fix** (addressing the comment):
   - One commit per review comment
   - Commit message: `fix(cycle-N): address review comment #N - [brief description]`
   - Push to feature branch (PR auto-updates)
   - Wait for next review cycle

**After Cycle 10:**
- Code is merged if all quality criteria met (section 12.3)
- Fixed number prevents endless iteration
- CAVEMAN principle: "Nudge" - incremental improvements compound

### 12.3 PR Approval Criteria (Mandatory for Merge)

**Code Quality (Automated Checks):**
- ✅ All tests pass (unit, integration, fuzzing)
- ✅ Code coverage doesn't decrease (≥85% minimum)
- ✅ No new linter warnings (flake8 clean)
- ✅ Type checking passes (mypy --strict)
- ✅ Security scan passes (bandit clean)
- ✅ CI/CD pipeline green (all automated checks)

**Code Review (Manual Checks via 10-Cycle Process):**
- ✅ Correctness: No logic errors, boundary bugs, or edge case issues
- ✅ Linting: PEP 8 compliant, consistent formatting
- ✅ Bounds checking: All values properly validated/clamped
- ✅ Type safety: Correct types throughout, no implicit conversions
- ✅ Test coverage: Edge cases tested, coverage adequate (≥85%)
- ✅ Code clarity: Variable names descriptive, comments explain "why"
- ✅ Performance: No obvious inefficiencies or memory leaks

**Documentation:**
- ✅ Inline code comments for complex logic
- ✅ External docs updated (if architecture/behavior changed)
- ✅ Commit messages clear & referential
- ✅ CHANGELOG.md entry added
- ✅ PR description complete and clear

**Alignment:**
- ✅ Changes align with CAVEMAN principles
- ✅ Performance impact documented (if any)
- ✅ No unresolved review comments
- ✅ No breaking changes without deprecation period

### 12.4 Example: Cycle 1 Review Comment

**Reviewer Subagent Posts:**
```markdown
### Cycle 1 Review Comment
**File:** tests/unit/test_pdf_processor.py
**Line:** 87

**Issue:** Test `test_extract_page_count_corrupted_pdf` doesn't validate the error message. 
Multiple error types could be raised; test only checks exception type.

**Why:** If the error handling changes unexpectedly, this test won't catch it. 
Weakens regression coverage.

**Suggested Fix:**
```python
def test_extract_page_count_corrupted_pdf(self, processor, tmp_path):
    corrupted_pdf = tmp_path / "corrupted.pdf"
    corrupted_pdf.write_bytes(b"not a pdf")
    
    with pytest.raises(PDFExtractionError) as exc_info:
        processor.get_page_count(corrupted_pdf)
    
    # Validate specific error message
    assert "PDF signature not found" in str(exc_info.value)
    assert str(corrupted_pdf) in str(exc_info.value)  # Include path in error
```
```

**Fixer Subagent Commits:**
```bash
git add tests/unit/test_pdf_processor.py
git commit -m "fix(cycle-1): add error message validation to corrupted PDF test"
git push origin feature/pdf-processor-tests
```

### 12.5 Preventing Common Review Issues

**To pass the 10-cycle review, avoid:**

| Issue | Impact | Fix |
|-------|--------|-----|
| Hardcoded values in tests | Brittle, fails on data changes | Use fixtures, parameterization |
| Missing docstrings | Unclear test purpose | Add docstring explaining what & why |
| Loose assertions (`assert x`) | Doesn't validate behavior | Use specific assertions (`assert x == 42`) |
| No edge case tests | Gaps in coverage | Test boundaries, nulls, empty inputs |
| Implicit type conversions | Silent bugs | Use type hints, explicit conversions |
| Global test state | Tests interfere with each other | Use fixtures, isolation per test |
| Slow tests (>5s each) | CI takes forever | Mock external APIs, use in-memory fixtures |

---

## Appendix A: Test Execution Checklist

- [ ] Unit tests pass (Python 3.9+)
- [ ] Integration tests pass
- [ ] Security scans (bandit, safety) pass
- [ ] Code coverage >85%
- [ ] Property-based tests converge
- [ ] E2E tests on staging pass
- [ ] Performance benchmarks acceptable
- [ ] No new warnings in logs
- [ ] Sentry error rate normal
- [ ] 10-cycle code review completed
- [ ] All PR approval criteria met (section 12.3)
- [ ] Ready for deployment

---

## Appendix B: Tools & Commands Reference

```bash
# Testing
pytest tests/ -v --cov=src
pytest tests/fuzzing/ --hypothesis-seed=0

# Security
bandit -r src/ -f json
safety check --json

# Linting & Types
flake8 src/ --max-line-length=100
mypy src/ --ignore-missing-imports

# Performance
pytest tests/performance/ --benchmark-only

# CI/CD Local Simulation
act -j test  # Run GitHub Actions locally (requires act CLI)

# Debugging
pytest tests/ -vv --pdb  # Drop into PDB on failure
pytest tests/ --tb=long  # Full traceback

# Coverage Report (HTML)
pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html
```
