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

import asyncio
import re
from abc import ABC, abstractmethod
from pathlib import Path
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
    _catalog: Dict[str, Dict[str, Any]] = {
        "local_nas": {
            "name": "local_nas",
            "category": "source",
            "description": "Local NAS or mounted directory source/destination for in-house document workflows.",
            "aliases": ["local-nas", "local nas", "localnas"],
        },
        "google_drive": {
            "name": "google_drive",
            "category": "destination",
            "description": "Google Drive destination backend for cloud-based document exports.",
            "aliases": ["google-drive", "google drive", "googledrive"],
        },
    }

    @staticmethod
    def normalize_backend_name(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Storage backend name must be a non-empty string")
        normalized = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
        if not normalized:
            raise ValueError("Storage backend name must be a non-empty string")
        return normalized

    def __init__(self) -> None:
        self.register_backend("local_nas", self._resolve_backend("local_nas"))
        self.register_backend("google_drive", self._resolve_backend("google_drive"))

    @staticmethod
    def _resolve_backend(name: str) -> Type[StorageBackend]:
        normalized = StorageBackendManager.normalize_backend_name(name)
        if normalized in {"local_nas", "localnas"}:
            from src.storage.local_nas import LocalNASBackend

            return LocalNASBackend
        if normalized in {"google_drive", "googledrive"}:
            from src.storage.google_drive import GoogleDriveBackend

            return GoogleDriveBackend
        raise ValueError(f"Unsupported storage backend: {name}")

    @classmethod
    def register_backend(cls, name: str, backend_cls: Type[StorageBackend]) -> None:
        normalized = cls.normalize_backend_name(name)
        if not isinstance(backend_cls, type):
            raise TypeError("Storage backend class must be a class object")
        cls._registry[normalized] = backend_cls
        cls._catalog.setdefault(normalized, {"name": normalized, "category": "source", "description": "Registered custom storage backend."})

    @classmethod
    def backend_catalog(cls) -> List[Dict[str, Any]]:
        catalog: List[Dict[str, Any]] = []
        for name in sorted(cls._registry):
            metadata = cls._catalog.get(name, {"name": name, "category": "source", "description": "Registered storage backend."})
            catalog.append({
                "name": metadata.get("name", name),
                "category": metadata.get("category", "source"),
                "description": metadata.get("description", "Registered storage backend."),
                "aliases": metadata.get("aliases", []),
            })
        return catalog

    @classmethod
    def validate_backend(cls, name: str, credentials: Optional[Dict[str, Any]] = None, category: Optional[str] = None) -> Dict[str, Any]:
        normalized = cls.normalize_backend_name(name)
        if normalized not in cls._registry:
            cls.register_backend(normalized, cls._resolve_backend(normalized))
        backend_cls = cls._registry[normalized]
        backend = backend_cls()
        effective_credentials = dict(credentials or {})
        effective_category = (category or cls._catalog.get(normalized, {}).get("category") or "source").strip().lower()
        if effective_category not in {"source", "destination"}:
            effective_category = "source"

        try:
            auth_result = backend.authenticate(effective_credentials)
            if hasattr(auth_result, "__await__"):
                auth_result = asyncio.run(auth_result)
            if not auth_result:
                return {"status": "error", "backend": normalized, "category": effective_category, "message": "Authentication failed", "path": None}
            base_path = getattr(backend, "base_path", None)
            raw_path = effective_credentials.get("path")
            if base_path is not None:
                resolved_path = str(Path(str(base_path)).resolve())
            elif raw_path is not None:
                resolved_path = str(Path(str(raw_path)).expanduser().resolve())
            else:
                resolved_path = None
            return {
                "status": "ok",
                "backend": normalized,
                "category": effective_category,
                "message": "Authentication successful",
                "path": resolved_path,
            }
        except Exception as exc:  # pragma: no cover - defensive validation path
            return {
                "status": "error",
                "backend": normalized,
                "category": effective_category,
                "message": str(exc),
                "path": effective_credentials.get("path"),
            }

    def get_backend(self, name: str) -> StorageBackend:
        normalized = self.normalize_backend_name(name)
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
