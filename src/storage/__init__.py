"""
Storage Backend Abstraction Layer

Provides abstract base class and concrete implementations for different storage
providers (Google Drive, Local NAS, SharePoint, Dropbox, etc.).

The StorageBackend ABC defines a unified interface for all storage operations:
- Authentication
- Folder/file listing
- Upload/download
- Deletion
- Storage information retrieval

This design allows users to switch storage backends via web UI configuration
without code changes, following the CAVEMAN principle of Minimize (minimize
code changes) and Agility (easy to adapt to new backends).
"""

from abc import ABC, abstractmethod
from typing import BinaryIO, List, Dict, Optional, Type, Any
from datetime import datetime

import httpx


class StorageBackend(ABC):
    """
    Abstract Base Class for storage backend implementations.
    
    All storage providers (Google Drive, Local NAS, SharePoint, Dropbox, S3, etc.)
    MUST implement this interface to ensure consistent behavior and compatibility
    with the document processing pipeline.
    
    CAVEMAN Alignment:
    - Clarity: Single interface for all backends
    - Avoid: Don't add backend-specific methods; use generic interface only
    - Value: Users can switch backends without retraining
    - Agility: New backends implement this interface, no changes to core code
    - Minimize: Minimal API surface (7 methods)
    """
    
    @abstractmethod
    async def authenticate(self, credentials: Dict[str, str]) -> bool:
        """
        Authenticate with the backend using provided credentials.
        
        Args:
            credentials: Backend-specific credential dictionary
                Google Drive: {"type": "service_account", "project_id": "...", ...}
                Local NAS: {"path": "/volume1/", "username": "...", ...}
        
        Returns:
            True if authentication succeeded, False otherwise
        
        Raises:
            ValueError: If credentials format is invalid
            ConnectionError: If backend is unreachable
        """
        pass
    
    @abstractmethod
    async def list_folders(self) -> List[Dict[str, str]]:
        """
        List all accessible folders in the backend.
        
        Returns:
            List of dicts with structure: [
                {"id": "folder_id_123", "name": "Document Inbox", "path": "..."},
                {"id": "folder_id_456", "name": "Archive", "path": "..."},
                ...
            ]
        
        Raises:
            ConnectionError: If backend is unreachable
            PermissionError: If user lacks list permissions
        """
        pass
    
    @abstractmethod
    async def upload_file(
        self,
        folder_id: str,
        filename: str,
        file: BinaryIO
    ) -> str:
        """
        Upload a file to the specified folder.
        
        Args:
            folder_id: Target folder identifier (backend-specific)
            filename: Name for the file in backend (e.g., "document_2026-08-17.pdf")
            file: Binary file stream to upload
        
        Returns:
            file_id: Unique identifier assigned by backend
        
        Raises:
            FileNotFoundError: If folder_id doesn't exist
            PermissionError: If user lacks write permissions
            ValueError: If filename invalid or file stream empty
            IOError: If upload fails mid-transfer
        """
        pass
    
    @abstractmethod
    async def download_file(self, file_id: str) -> BinaryIO:
        """
        Download a file from the backend by its ID.
        
        Args:
            file_id: Unique file identifier (from upload_file or list_files)
        
        Returns:
            BinaryIO: File stream ready for reading
        
        Raises:
            FileNotFoundError: If file_id doesn't exist
            PermissionError: If user lacks read permissions
            IOError: If download fails
        """
        pass
    
    @abstractmethod
    async def list_files(
        self,
        folder_id: str,
        pattern: str = "*.pdf"
    ) -> List[Dict[str, str]]:
        """
        List files in a folder, optionally filtered by pattern.
        
        Args:
            folder_id: Target folder identifier
            pattern: File name pattern (e.g., "*.pdf", "invoice_*.pdf")
        
        Returns:
            List of file dicts: [
                {
                    "id": "file_id_123",
                    "name": "document.pdf",
                    "size": 1024000,
                    "modified": "2026-08-17T14:35:00Z"
                },
                ...
            ]
        
        Raises:
            FileNotFoundError: If folder_id doesn't exist
            PermissionError: If user lacks list permissions
        """
        pass
    
    @abstractmethod
    async def delete_file(self, file_id: str) -> bool:
        """
        Delete a file from the backend.
        
        Args:
            file_id: Unique file identifier to delete
        
        Returns:
            True if deletion succeeded
        
        Raises:
            FileNotFoundError: If file_id doesn't exist
            PermissionError: If user lacks delete permissions
        """
        pass
    
    @abstractmethod
    async def get_storage_info(self) -> Dict[str, str]:
        """
        Retrieve storage account information and usage statistics.
        
        Returns:
            Dict with: {
                "account": "user@example.com",
                "used_bytes": 5368709120,
                "total_bytes": 107374182400,
                "backend_type": "google_drive"
            }
        
        Raises:
            ConnectionError: If backend is unreachable
        """
        pass


class StorageBackendManager:
    """Simple registry for pluggable storage providers and local fallback."""

    _registry: Dict[str, Type[StorageBackend]] = {}

    def __init__(self) -> None:
        self.register_backend("local_nas", self._resolve_backend("local_nas"))
        self.register_backend("google_drive", self._resolve_backend("google_drive"))

    @staticmethod
    def _resolve_backend(name: str) -> Type[StorageBackend]:
        normalized = name.lower()
        if normalized == "local_nas":
            from src.storage.local_nas import LocalNASBackend

            return LocalNASBackend
        if normalized == "google_drive":
            from src.storage.google_drive import GoogleDriveBackend

            return GoogleDriveBackend
        raise ValueError(f"Unsupported storage backend: {name}")

    @classmethod
    def register_backend(cls, name: str, backend_cls: Type[StorageBackend]) -> None:
        cls._registry[name.lower()] = backend_cls

    def get_backend(self, name: str) -> StorageBackend:
        normalized = name.lower()
        if normalized not in self._registry:
            self.register_backend(normalized, self._resolve_backend(normalized))
        return self._registry[normalized]()


class WebhookExportClient:
    """Send structured payloads to downstream automation systems."""

    def __init__(self, url: str, timeout: float = 5.0, headers: Optional[Dict[str, str]] = None) -> None:
        self.url = url
        self.timeout = timeout
        self.headers = headers or {"Content-Type": "application/json"}

    async def send(self, payload: Dict[str, Any], timeout: Optional[float] = None) -> bool:
        if not self.url:
            return False
        try:
            async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
                response = await client.post(self.url, json=payload, headers=self.headers)
                if hasattr(response, "raise_for_status"):
                    response.raise_for_status()
                elif getattr(response, "status_code", 200) >= 400:
                    return False
            return True
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            return False


__all__ = ["StorageBackend", "StorageBackendManager", "WebhookExportClient"]
