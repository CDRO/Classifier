"""
Unit Tests for Storage Backends

Tests the StorageBackend ABC interface and concrete implementations
(GoogleDriveBackend, LocalNASBackend).

Tests validate:
1. Interface contract (all methods implemented)
2. Authentication (valid/invalid credentials)
3. Folder/file operations (create, read, delete)
4. Error handling (boundary conditions, edge cases)
5. Security (path escape prevention, permission checks)

Test Coverage: 18 test cases (11 unit + 7 integration - this file covers unit tests)

Running tests:
  pytest tests/unit/test_storage_backends.py -v
  pytest tests/unit/test_storage_backends.py -v --cov=src/storage --cov-report=html
"""

import pytest
from pathlib import Path
from io import BytesIO
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import tempfile
import os
from datetime import datetime

# Import backends
from src.storage import StorageBackend, StorageBackendManager, WebhookExportClient
from src.storage.google_drive import GoogleDriveBackend
from src.storage.local_nas import LocalNASBackend


# ============================================================================
# Fixtures (shared test setup)
# ============================================================================

@pytest.fixture
def google_drive_backend():
    """Create a GoogleDriveBackend instance for testing."""
    return GoogleDriveBackend()


@pytest.fixture
def local_nas_backend():
    """Create a LocalNASBackend instance for testing."""
    return LocalNASBackend()


@pytest.fixture
def temp_nas_path():
    """Create temporary directory simulating NAS /volume1/."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create sample folder structure
        inbox = Path(tmpdir) / "Inbox"
        archive = Path(tmpdir) / "Archive"
        inbox.mkdir()
        archive.mkdir()
        yield tmpdir


@pytest.fixture
def sample_pdf_file():
    """Create a mock PDF file (BytesIO stream)."""
    content = b"%PDF-1.4\n%fake pdf content"
    return BytesIO(content)


@pytest.fixture
def valid_google_drive_credentials():
    """Valid Google Drive service account credentials format."""
    return {
        "type": "service_account",
        "project_id": "test-project-123",
        "private_key_id": "key-id-123",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEvQIBADANBg...",
        "client_email": "classifier@test-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/..."
    }


@pytest.fixture
def valid_nas_credentials(temp_nas_path):
    """Valid Local NAS credentials format."""
    return {
        "path": temp_nas_path,
        "username": "admin",
        "check_permissions": False
    }


# ============================================================================
# Google Drive Backend Tests
# ============================================================================

class TestGoogleDriveBackend:
    """Test Google Drive backend implementation."""
    
    @pytest.mark.asyncio
    async def test_authenticate_with_valid_credentials(
        self,
        google_drive_backend,
        valid_google_drive_credentials
    ):
        """✓ Google Drive authentication succeeds with valid service account JSON."""
        result = await google_drive_backend.authenticate(valid_google_drive_credentials)
        
        assert result is True
        assert google_drive_backend.credentials == valid_google_drive_credentials
        assert google_drive_backend.account_email == "classifier@test-project.iam.gserviceaccount.com"
    
    @pytest.mark.asyncio
    async def test_authenticate_with_missing_type_field(
        self,
        google_drive_backend,
        valid_google_drive_credentials
    ):
        """✓ Google Drive authentication fails if 'type' field missing."""
        invalid_creds = {**valid_google_drive_credentials}
        del invalid_creds["type"]
        
        with pytest.raises(ValueError, match="Missing required credential field: type"):
            await google_drive_backend.authenticate(invalid_creds)
    
    @pytest.mark.asyncio
    async def test_authenticate_with_wrong_type_field(
        self,
        google_drive_backend,
        valid_google_drive_credentials
    ):
        """✓ Google Drive authentication fails if type != 'service_account'."""
        invalid_creds = {**valid_google_drive_credentials}
        invalid_creds["type"] = "oauth2"
        
        with pytest.raises(ValueError, match="Expected type='service_account'"):
            await google_drive_backend.authenticate(invalid_creds)
    
    @pytest.mark.asyncio
    async def test_list_folders_before_auth_fails(self, google_drive_backend):
        """✓ Listing folders without authentication raises error."""
        with pytest.raises(ConnectionError, match="Not authenticated"):
            await google_drive_backend.list_folders()
    
    @pytest.mark.asyncio
    async def test_list_folders_after_auth_succeeds(
        self,
        google_drive_backend,
        valid_google_drive_credentials
    ):
        """✓ Listing folders after authentication returns folder list."""
        await google_drive_backend.authenticate(valid_google_drive_credentials)
        folders = await google_drive_backend.list_folders()
        
        assert isinstance(folders, list)
        assert len(folders) > 0
        assert all("id" in f and "name" in f for f in folders)
    
    @pytest.mark.asyncio
    async def test_upload_file_with_empty_filename(
        self,
        google_drive_backend,
        valid_google_drive_credentials,
        sample_pdf_file
    ):
        """✓ Upload fails with empty filename."""
        await google_drive_backend.authenticate(valid_google_drive_credentials)
        
        with pytest.raises(ValueError, match="filename cannot be empty"):
            await google_drive_backend.upload_file("folder_id", "", sample_pdf_file)
    
    @pytest.mark.asyncio
    async def test_upload_file_with_empty_folder_id(
        self,
        google_drive_backend,
        valid_google_drive_credentials,
        sample_pdf_file
    ):
        """✓ Upload fails with empty folder_id."""
        await google_drive_backend.authenticate(valid_google_drive_credentials)
        
        with pytest.raises(ValueError, match="folder_id cannot be empty"):
            await google_drive_backend.upload_file("", "document.pdf", sample_pdf_file)
    
    @pytest.mark.asyncio
    async def test_download_file_with_empty_file_id(
        self,
        google_drive_backend,
        valid_google_drive_credentials
    ):
        """✓ Download fails with empty file_id."""
        await google_drive_backend.authenticate(valid_google_drive_credentials)
        
        with pytest.raises(ValueError, match="file_id cannot be empty"):
            await google_drive_backend.download_file("")
    
    @pytest.mark.asyncio
    async def test_delete_file_with_empty_file_id(
        self,
        google_drive_backend,
        valid_google_drive_credentials
    ):
        """✓ Delete fails with empty file_id."""
        await google_drive_backend.authenticate(valid_google_drive_credentials)
        
        with pytest.raises(ValueError, match="file_id cannot be empty"):
            await google_drive_backend.delete_file("")

    @pytest.mark.asyncio
    async def test_google_drive_success_paths(
        self,
        google_drive_backend,
        valid_google_drive_credentials,
        sample_pdf_file
    ):
        """✓ Google Drive happy-path flows cover upload/list/download/delete/storage info."""
        await google_drive_backend.authenticate(valid_google_drive_credentials)

        folders = await google_drive_backend.list_folders()
        assert folders

        uploaded = await google_drive_backend.upload_file("folder_123", "report.pdf", sample_pdf_file)
        assert uploaded == "gd_file_folder_123_report_pdf"

        listed = await google_drive_backend.list_files("folder_123", "*.pdf")
        assert len(listed) >= 2

        downloaded = await google_drive_backend.download_file(uploaded)
        assert downloaded.read() == b"placeholder_file_content"

        removed = await google_drive_backend.delete_file(uploaded)
        assert removed is True

        info = await google_drive_backend.get_storage_info()
        assert info["backend_type"] == "google_drive"

    @pytest.mark.asyncio
    async def test_google_drive_authenticate_builds_real_service_when_available(self, monkeypatch):
        """✓ The backend should build a real Google Drive service when the optional SDK is installed."""
        backend = GoogleDriveBackend()
        credentials = {
            "type": "service_account",
            "project_id": "real-project",
            "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
            "client_email": "classifier@real-project.iam.gserviceaccount.com",
        }
        fake_service = object()

        monkeypatch.setattr("src.storage.google_drive._build_service", lambda service_account_config: fake_service)

        result = await backend.authenticate(credentials)

        assert result is True
        assert backend.service is fake_service
        assert backend.account_email == credentials["client_email"]


# ============================================================================
# Local NAS Backend Tests
# ============================================================================

class TestLocalNASBackend:
    """Test Local NAS backend implementation."""
    
    @pytest.mark.asyncio
    async def test_authenticate_with_valid_path(
        self,
        local_nas_backend,
        valid_nas_credentials
    ):
        """✓ Local NAS authentication succeeds with valid path."""
        result = await local_nas_backend.authenticate(valid_nas_credentials)
        
        assert result is True
        assert local_nas_backend.base_path == Path(valid_nas_credentials["path"]).resolve()
        assert local_nas_backend.credentials == valid_nas_credentials
    
    @pytest.mark.asyncio
    async def test_authenticate_with_nonexistent_path(self, local_nas_backend):
        """✓ Local NAS authentication fails if path doesn't exist."""
        invalid_creds = {
            "path": "/nonexistent/path/that/does/not/exist",
            "username": "admin"
        }
        
        with pytest.raises(FileNotFoundError, match="NAS path does not exist"):
            await local_nas_backend.authenticate(invalid_creds)
    
    @pytest.mark.asyncio
    async def test_authenticate_with_empty_path(self, local_nas_backend):
        """✓ Local NAS authentication fails with empty path."""
        invalid_creds = {"path": "", "username": "admin"}
        
        with pytest.raises(ValueError, match="credentials\\['path'\\] cannot be empty"):
            await local_nas_backend.authenticate(invalid_creds)
    
    @pytest.mark.asyncio
    async def test_authenticate_with_file_path(self, local_nas_backend, temp_nas_path):
        """✓ Local NAS authentication fails if path is a file, not directory."""
        # Create a file
        file_path = Path(temp_nas_path) / "test.txt"
        file_path.write_text("test")
        
        invalid_creds = {"path": str(file_path), "username": "admin"}
        
        with pytest.raises(ValueError, match="Path is not a directory"):
            await local_nas_backend.authenticate(invalid_creds)
    
    @pytest.mark.asyncio
    async def test_list_folders_before_auth_fails(self, local_nas_backend):
        """✓ Listing folders without authentication raises error."""
        with pytest.raises(ConnectionError, match="Not authenticated"):
            await local_nas_backend.list_folders()
    
    @pytest.mark.asyncio
    async def test_list_folders_after_auth_succeeds(
        self,
        local_nas_backend,
        valid_nas_credentials
    ):
        """✓ Listing folders after authentication returns folder list."""
        await local_nas_backend.authenticate(valid_nas_credentials)
        folders = await local_nas_backend.list_folders()
        
        assert isinstance(folders, list)
        assert len(folders) == 2  # "Inbox" and "Archive" from fixture
        assert any(f["name"] == "Inbox" for f in folders)
        assert any(f["name"] == "Archive" for f in folders)
    
    @pytest.mark.asyncio
    async def test_upload_file_to_nas(
        self,
        local_nas_backend,
        valid_nas_credentials,
        sample_pdf_file
    ):
        """✓ Upload file to NAS succeeds and returns file_id (path)."""
        await local_nas_backend.authenticate(valid_nas_credentials)
        
        folder_id = str(Path(valid_nas_credentials["path"]) / "Inbox")
        file_id = await local_nas_backend.upload_file(folder_id, "test.pdf", sample_pdf_file)
        
        assert file_id is not None
        assert "test.pdf" in file_id
        assert Path(file_id).exists()
    
    @pytest.mark.asyncio
    async def test_upload_file_with_empty_filename(
        self,
        local_nas_backend,
        valid_nas_credentials,
        sample_pdf_file
    ):
        """✓ Upload fails with empty filename."""
        await local_nas_backend.authenticate(valid_nas_credentials)
        
        folder_id = str(Path(valid_nas_credentials["path"]) / "Inbox")
        
        with pytest.raises(ValueError, match="filename cannot be empty"):
            await local_nas_backend.upload_file(folder_id, "", sample_pdf_file)
    
    @pytest.mark.asyncio
    async def test_download_file_from_nas(
        self,
        local_nas_backend,
        valid_nas_credentials,
        sample_pdf_file
    ):
        """✓ Download file from NAS succeeds and returns file stream."""
        await local_nas_backend.authenticate(valid_nas_credentials)
        
        # First upload a file
        folder_id = str(Path(valid_nas_credentials["path"]) / "Inbox")
        file_id = await local_nas_backend.upload_file(folder_id, "test.pdf", sample_pdf_file)
        
        # Then download it
        downloaded = await local_nas_backend.download_file(file_id)
        
        assert isinstance(downloaded, BytesIO)
        downloaded_content = downloaded.read()
        assert len(downloaded_content) > 0
    
    @pytest.mark.asyncio
    async def test_delete_file_from_nas(
        self,
        local_nas_backend,
        valid_nas_credentials,
        sample_pdf_file
    ):
        """✓ Delete file from NAS succeeds."""
        await local_nas_backend.authenticate(valid_nas_credentials)
        
        # First upload a file
        folder_id = str(Path(valid_nas_credentials["path"]) / "Inbox")
        file_id = await local_nas_backend.upload_file(folder_id, "test.pdf", sample_pdf_file)
        
        # Then delete it
        result = await local_nas_backend.delete_file(file_id)
        
        assert result is True
        assert not Path(file_id).exists()
    
    @pytest.mark.asyncio
    async def test_list_files_in_nas_folder(
        self,
        local_nas_backend,
        valid_nas_credentials,
        sample_pdf_file
    ):
        """✓ Listing files in NAS folder returns file list."""
        await local_nas_backend.authenticate(valid_nas_credentials)
        
        # Upload a file first
        folder_id = str(Path(valid_nas_credentials["path"]) / "Inbox")
        await local_nas_backend.upload_file(folder_id, "test.pdf", sample_pdf_file)
        
        # List files
        files = await local_nas_backend.list_files(folder_id, "*.pdf")
        
        assert isinstance(files, list)
        assert len(files) >= 1
        assert any(f["name"] == "test.pdf" for f in files)
        assert all("id" in f and "name" in f and "size" in f for f in files)
    
    @pytest.mark.asyncio
    async def test_get_storage_info_nas(
        self,
        local_nas_backend,
        valid_nas_credentials
    ):
        """✓ Getting NAS storage info returns quota and usage."""
        await local_nas_backend.authenticate(valid_nas_credentials)
        info = await local_nas_backend.get_storage_info()
        
        assert "account" in info
        assert "used_bytes" in info
        assert "total_bytes" in info
        assert "backend_type" in info
        assert info["backend_type"] == "local_nas"
        assert int(info["used_bytes"]) >= 0
        assert int(info["total_bytes"]) > 0

    @pytest.mark.asyncio
    async def test_upload_rejects_path_escape_for_nas(
        self,
        local_nas_backend,
        valid_nas_credentials,
        sample_pdf_file
    ):
        """✓ NAS upload rejects path traversal attempts."""
        await local_nas_backend.authenticate(valid_nas_credentials)

        escape_target = str(Path(valid_nas_credentials["path"]).parent)
        with pytest.raises(PermissionError, match="Path escape detected"):
            await local_nas_backend.upload_file(escape_target, "danger.pdf", sample_pdf_file)

    @pytest.mark.asyncio
    async def test_download_and_delete_validate_missing_or_escape_paths(
        self,
        local_nas_backend,
        valid_nas_credentials,
        sample_pdf_file
    ):
        """✓ NAS download/delete checks missing files and escape attempts."""
        await local_nas_backend.authenticate(valid_nas_credentials)

        missing_path = str(Path(valid_nas_credentials["path"]) / "Inbox" / "missing.pdf")
        with pytest.raises(FileNotFoundError):
            await local_nas_backend.download_file(missing_path)

        escape_target = str(Path(valid_nas_credentials["path"]).parent)
        with pytest.raises(PermissionError, match="Path escape detected"):
            await local_nas_backend.delete_file(str(Path(escape_target) / "danger.pdf"))

        folder_id = str(Path(valid_nas_credentials["path"]) / "Inbox")
        file_id = await local_nas_backend.upload_file(folder_id, "audit.pdf", sample_pdf_file)
        assert await local_nas_backend.delete_file(file_id) is True

    @pytest.mark.asyncio
    async def test_nas_auth_and_listing_cover_permission_and_errors(
        self,
        local_nas_backend,
        temp_nas_path,
        monkeypatch
    ):
        """✓ NAS auth and folder listing exercise permission and exception branches."""
        missing = {"path": str(Path(temp_nas_path) / "missing"), "check_permissions": True}
        with pytest.raises(FileNotFoundError):
            await local_nas_backend.authenticate(missing)

        valid = {"path": temp_nas_path, "username": "admin", "check_permissions": True}
        monkeypatch.setattr("src.storage.local_nas.os.access", lambda *_args, **_kwargs: False)
        with pytest.raises(PermissionError, match="No read permission"):
            await local_nas_backend.authenticate(valid)

        monkeypatch.setattr("src.storage.local_nas.os.access", lambda *_args, **_kwargs: True)
        await local_nas_backend.authenticate(valid)

        class BrokenPath:
            def __iterdir__(self):
                raise OSError("broken listing")

        monkeypatch.setattr(local_nas_backend, "base_path", BrokenPath(), raising=False)
        with pytest.raises(ConnectionError, match="Failed to list NAS folders"):
            await local_nas_backend.list_folders()

    @pytest.mark.asyncio
    async def test_list_files_and_storage_info_cover_failure_paths(
        self,
        local_nas_backend,
        valid_nas_credentials,
        sample_pdf_file,
        monkeypatch
    ):
        """✓ NAS listing and stats cover missing folders and exception handling."""
        await local_nas_backend.authenticate(valid_nas_credentials)

        folder_id = str(Path(valid_nas_credentials["path"]) / "Inbox")
        with pytest.raises(FileNotFoundError):
            await local_nas_backend.list_files(str(Path(valid_nas_credentials["path"]) / "Missing"), "*.pdf")

        with pytest.raises(PermissionError, match="Path escape detected"):
            await local_nas_backend.list_files(str(Path(valid_nas_credentials["path"]).parent), "*.pdf")

        file_path = await local_nas_backend.upload_file(folder_id, "stats.pdf", sample_pdf_file)
        info = await local_nas_backend.get_storage_info()
        assert info["backend_type"] == "local_nas"
        assert Path(file_path).exists()

        def boom(*_args, **_kwargs):
            raise OSError("stats failed")

        monkeypatch.setattr("shutil.disk_usage", boom)
        with pytest.raises(OSError, match="stats failed"):
            await local_nas_backend.get_storage_info()


# ============================================================================
# Backend Interface Compliance Tests
# ============================================================================

class TestStorageBackendInterface:
    """Test that all backends properly implement StorageBackend interface."""
    
    def test_google_drive_implements_storage_backend(self, google_drive_backend):
        """✓ GoogleDriveBackend is a subclass of StorageBackend."""
        assert isinstance(google_drive_backend, StorageBackend)
    
    def test_local_nas_implements_storage_backend(self, local_nas_backend):
        """✓ LocalNASBackend is a subclass of StorageBackend."""
        assert isinstance(local_nas_backend, StorageBackend)
    
    def test_google_drive_has_all_required_methods(self, google_drive_backend):
        """✓ GoogleDriveBackend implements all abstract methods."""
        required_methods = [
            "authenticate",
            "list_folders",
            "upload_file",
            "download_file",
            "list_files",
            "delete_file",
            "get_storage_info"
        ]
        for method in required_methods:
            assert hasattr(google_drive_backend, method)
            assert callable(getattr(google_drive_backend, method))
    
    def test_local_nas_has_all_required_methods(self, local_nas_backend):
        """✓ LocalNASBackend implements all abstract methods."""
        required_methods = [
            "authenticate",
            "list_folders",
            "upload_file",
            "download_file",
            "list_files",
            "delete_file",
            "get_storage_info"
        ]
        for method in required_methods:
            assert hasattr(local_nas_backend, method)
            assert callable(getattr(local_nas_backend, method))


class TestStorageBackendManager:
    """Runtime factory and fallback behavior for pluggable storage providers."""

    def test_manager_returns_registered_backend(self):
        manager = StorageBackendManager()
        backend = manager.get_backend("local_nas")

        assert isinstance(backend, LocalNASBackend)

    def test_manager_supports_external_google_backend(self):
        manager = StorageBackendManager()
        backend = manager.get_backend("google_drive")

        assert isinstance(backend, GoogleDriveBackend)

    def test_manager_normalizes_common_backend_aliases(self):
        manager = StorageBackendManager()

        assert isinstance(manager.get_backend("local-nas"), LocalNASBackend)
        assert isinstance(manager.get_backend("Local NAS"), LocalNASBackend)
        assert isinstance(manager.get_backend("google drive"), GoogleDriveBackend)
        assert isinstance(manager.get_backend("Google_Drive"), GoogleDriveBackend)

    def test_manager_can_register_custom_backend(self):
        class CustomBackend(LocalNASBackend):
            pass

        manager = StorageBackendManager()
        manager.register_backend("custom_nas", CustomBackend)

        assert isinstance(manager.get_backend("custom_nas"), CustomBackend)

    def test_manager_register_backend_normalizes_aliases(self):
        class CustomBackend(LocalNASBackend):
            pass

        manager = StorageBackendManager()
        manager.register_backend("Custom NAS", CustomBackend)

        assert isinstance(manager.get_backend("custom-nas"), CustomBackend)

    def test_manager_rejects_unsupported_backend(self):
        manager = StorageBackendManager()

        with pytest.raises(ValueError, match="Unsupported storage backend"):
            manager._resolve_backend("unsupported_backend")

    def test_manager_rejects_empty_or_invalid_registration(self):
        manager = StorageBackendManager()

        with pytest.raises(ValueError, match="non-empty string"):
            manager.register_backend("", LocalNASBackend)

        with pytest.raises(ValueError, match="non-empty string"):
            manager.get_backend("   ")

        with pytest.raises(TypeError, match="class object"):
            manager.register_backend("dummy", object())

    @pytest.mark.asyncio
    async def test_webhook_export_client_posts_payload_and_falls_back_to_local(self, monkeypatch):
        client = WebhookExportClient(url="https://example.com/webhook")

        class DummyResponse:
            status_code = 200

        async def fake_post(*args, **kwargs):
            return DummyResponse()

        monkeypatch.setattr("src.storage.httpx.AsyncClient.post", fake_post)

        result = await client.send({"status": "classified", "filename": "report.pdf"})
        assert result is True

        fallback = await client.send({"status": "classified"}, timeout=1.0)
        assert fallback is True

    @pytest.mark.asyncio
    async def test_webhook_export_client_handles_empty_url_and_http_failures(self, monkeypatch):
        client = WebhookExportClient(url="")
        assert await client.send({"status": "classified"}) is False

        class FailedResponse:
            status_code = 500

        async def fake_post(*args, **kwargs):
            return FailedResponse()

        monkeypatch.setattr("src.storage.httpx.AsyncClient.post", fake_post)
        failing = WebhookExportClient(url="https://example.com/failed")
        assert await failing.send({"status": "failed"}) is False


if __name__ == "__main__":
    # Run tests with: pytest tests/unit/test_storage_backends.py -v
    pytest.main([__file__, "-v", "--tb=short"])
